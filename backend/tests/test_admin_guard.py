"""관리자 자신을 차단하지 않게 하는 장치들."""
import importlib.util
import pathlib
from collections import namedtuple

import pytest
from fastapi.testclient import TestClient

import config
from admin_guard import authenticated_ssh_peers, protection_reason
from ban_manager import BanManager
from database import BlockedIP, Event
from integrations.fail2ban import parse_ignoreip_output
from iplist import find_network, parse_ip_list

Addr = namedtuple("Addr", "ip port")
Conn = namedtuple("Conn", "laddr raddr status pid")

NO_PEERS = dict


# --- 목록 해석 ---------------------------------------------------------------

def test_parse_ip_list_keeps_invalid_entries_visible():
    nets, invalid = parse_ip_list("203.0.113.7, 198.51.100.0/24  10.0.0.5/24 office.example 2001:db8::/32")
    assert [str(n) for n in nets] == ["203.0.113.7/32", "198.51.100.0/24", "10.0.0.0/24", "2001:db8::/32"]
    assert invalid == ["office.example"]


def test_find_network_handles_ipv4_mapped_ipv6():
    nets, _ = parse_ip_list("198.51.100.0/24")
    assert str(find_network("::ffff:198.51.100.9", nets)) == "198.51.100.0/24"
    assert find_network("198.51.101.1", nets) is None
    assert find_network("not-an-ip", nets) is None


def test_parse_fail2ban_ignoreip_output():
    out = "These IP addresses/networks are ignored:\n|- 127.0.0.1/8\n|- ::1\n`- 203.0.113.0/24\n"
    assert parse_ignoreip_output(out) == ["127.0.0.1/8", "::1", "203.0.113.0/24"]
    assert parse_ignoreip_output("No IP address/network is ignored") == []


# --- 인증을 마친 SSH 세션 -------------------------------------------------------

def test_only_authenticated_ssh_sessions_are_protected():
    conns = [
        Conn(Addr("10.0.0.2", 22), Addr("203.0.113.10", 50000), "ESTABLISHED", 101),  # 로그인한 관리자
        Conn(Addr("10.0.0.2", 22), Addr("203.0.113.66", 50001), "ESTABLISHED", 102),  # 비밀번호 찍는 중
        Conn(Addr("10.0.0.2", 22), Addr("::ffff:198.51.100.3", 50002), "ESTABLISHED", 103),  # 9.8+ 이름
        Conn(Addr("10.0.0.2", 443), Addr("192.0.2.1", 50003), "ESTABLISHED", 104),  # SSH 가 아님
        Conn(Addr("10.0.0.2", 22), Addr("192.0.2.2", 50004), "CLOSE_WAIT", 101),
    ]
    names = {101: "sshd: alice@pts/0", 102: "sshd: root [priv]", 103: "sshd-session: carol@notty", 104: "sshd: dave@pts/1"}
    peers = authenticated_ssh_peers(net_connections=lambda: conns, cmdline_of=names.__getitem__)
    assert peers == {"203.0.113.10": "alice", "198.51.100.3": "carol"}


def test_unreadable_connections_mean_no_session_protection():
    import psutil

    def denied():
        raise psutil.AccessDenied()
    assert authenticated_ssh_peers(net_connections=denied) == {}


# --- 보호 판정 --------------------------------------------------------------

class IgnoreClient:
    def __init__(self, items):
        self.items = items

    def ignore_list(self):
        return self.items


def test_protection_sources(monkeypatch):
    monkeypatch.setattr(config, "F2B_IGNOREIP", "198.51.100.0/24")
    assert protection_reason("127.0.0.1", peers_provider=NO_PEERS)["kind"] == "loopback"
    r = protection_reason("198.51.100.20", peers_provider=NO_PEERS)
    assert r["kind"] == "admin_list" and "198.51.100.0/24" in r["text"]
    r = protection_reason("192.0.2.5", client=IgnoreClient(["127.0.0.1/8", "192.0.2.0/28"]), peers_provider=NO_PEERS)
    assert r["kind"] == "fail2ban_ignoreip"
    r = protection_reason("203.0.113.10", peers_provider=lambda: {"203.0.113.10": "alice"})
    assert r["kind"] == "ssh_session" and "alice" in r["text"]
    assert protection_reason("203.0.113.99", client=IgnoreClient(None), peers_provider=NO_PEERS) is None


# --- 차단 관리자 -----------------------------------------------------------

class FakeF2B:
    jail, last_error = "sshd", ""

    def __init__(self):
        self.ban_calls = []

    def availability(self):
        return True, "", ""

    def ban(self, ip):
        self.ban_calls.append(ip)
        return True


def test_ban_manager_refuses_protected_address(db):
    f = FakeF2B()
    guard = lambda ip, client: {"kind": "ssh_session", "text": "지금 이 주소에서 'alice' 계정으로 로그인한 SSH 세션이 열려 있음"}
    r = BanManager(db, f, guard=guard).ban_ip("203.0.113.10", "브루트포스")
    assert r["status"] == "PROTECTED" and r["changed"] is False
    assert f.ban_calls == []
    assert db.query(BlockedIP).count() == 0
    ev = db.query(Event).filter(Event.event_type == "IP_BLOCK_SKIPPED").one()
    assert ev.severity == "WARNING" and "alice" in ev.description_ko


def test_ban_manager_still_bans_unprotected_address(db):
    f = FakeF2B()
    r = BanManager(db, f, guard=lambda ip, client: None).ban_ip("203.0.113.66", "브루트포스")
    assert r["status"] == "ACTIVE" and f.ban_calls == ["203.0.113.66"]


def test_manual_block_api_refuses_admin_address(monkeypatch):
    import app as app_module
    monkeypatch.setattr(config, "F2B_IGNOREIP", "198.51.100.0/24")
    c = TestClient(app_module.app)
    r = c.post("/api/blocked", json={"ip": "198.51.100.5"}, headers={"X-API-Token": "test-token"})
    assert r.status_code == 409 and "SECDASH_F2B_IGNOREIP" in r.json()["detail"]


# --- 공개키 거부는 브루트포스로 세지 않는다 --------------------------------------------

def test_rejected_public_keys_do_not_count_as_brute_force(db):
    from database import Alert
    from monitor.intrusion import AuthLogWatcher

    calls = []

    class Ban:
        def __init__(self, db):
            pass

        def ban_ip(self, ip, reason, is_simulation=False):
            calls.append(ip)
            return {"status": "ACTIVE", "changed": True}

    w = AuthLogWatcher(log_path="/nonexistent/auth.log", ban_manager_factory=Ban)
    w.threshold = 5
    for i in range(12):  # 에이전트의 키 여러 개가 차례로 거부된 줄
        w.process_line(f"Sep  8 14:20:{i:02d} host sshd[1]: Failed publickey for alice from 203.0.113.10 port 5000 ssh2: ED25519 SHA256:k{i}")
    assert db.query(Event).filter(Event.event_type == "AUTH_FAILURE").count() == 12  # 기록은 남는다
    assert db.query(Alert).filter(Alert.rule == "brute_force").count() == 0 and calls == []
    for i in range(5):  # 비밀번호 실패는 여전히 센다
        w.process_line(f"Sep  8 14:21:{i:02d} host sshd[1]: Failed password for alice from 203.0.113.10 port 5000 ssh2")
    assert calls == ["203.0.113.10"]


def test_seeded_history_skips_rejected_public_keys(db):
    import json

    from database import utcnow
    from monitor.intrusion import AuthLogWatcher

    for i in range(6):
        db.add(Event(event_type="AUTH_FAILURE", severity="INFO", source="t", description="x", timestamp=utcnow(),
                     details=json.dumps({"ip": "203.0.113.10", "user": "alice", "method": "publickey"})))
    db.add(Event(event_type="AUTH_FAILURE", severity="INFO", source="t", description="x", timestamp=utcnow(),
                 details=json.dumps({"ip": "203.0.113.10", "user": "alice", "method": "password"})))
    db.commit()
    w = AuthLogWatcher(log_path="/nonexistent/auth.log")
    w._failures.clear()
    w._seed_failures()
    assert len(w._failures["203.0.113.10"]) == 1


# --- fail2ban 설정 만들기 (deploy/fail2ban_ignoreip.py) -------------------------------

def _renderer():
    path = pathlib.Path(__file__).resolve().parents[2] / "deploy" / "fail2ban_ignoreip.py"
    spec = importlib.util.spec_from_file_location("fail2ban_ignoreip", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TEMPLATE = "[DEFAULT]\n# 설명\nignoreip = 127.0.0.1/8 ::1\nbantime.increment = true\n"


def test_render_adds_admin_entries_and_keeps_rest(tmp_path):
    mod = _renderer()
    env = tmp_path / "secdash.env"
    env.write_text('SECDASH_PORT=8000\nSECDASH_F2B_IGNOREIP="203.0.113.7 198.51.100.0/24, 203.0.113.7"\n', encoding="utf-8")
    text, invalid, admin = mod.render(TEMPLATE, mod.read_env_value(str(env)))
    assert invalid == [] and admin == ["203.0.113.7", "198.51.100.0/24"]
    assert "ignoreip = 127.0.0.1/8 ::1 203.0.113.7 198.51.100.0/24\n" in text
    assert "bantime.increment = true" in text and "# 설명" in text


def test_render_refuses_invalid_entries(tmp_path, capsys):
    mod = _renderer()
    tpl = tmp_path / "t.conf"
    tpl.write_text(TEMPLATE, encoding="utf-8")
    env = tmp_path / "secdash.env"
    env.write_text("SECDASH_F2B_IGNOREIP=203.0.113.7 office.example\n", encoding="utf-8")
    assert mod.main([str(tpl), str(env)]) == 2
    out = capsys.readouterr()
    assert out.out == "" and "office.example" in out.err


def test_render_without_env_warns_but_keeps_loopback(tmp_path, capsys):
    mod = _renderer()
    tpl = tmp_path / "t.conf"
    tpl.write_text(TEMPLATE, encoding="utf-8")
    assert mod.main([str(tpl), str(tmp_path / "missing.env"), "--client", "203.0.113.50"]) == 0
    out = capsys.readouterr()
    assert "ignoreip = 127.0.0.1/8 ::1\n" in out.out
    assert "SECDASH_F2B_IGNOREIP=203.0.113.50" in out.err


def test_repo_template_has_exactly_one_ignoreip_line():
    mod = _renderer()
    tpl = (pathlib.Path(__file__).resolve().parents[2] / "deploy" / "fail2ban-secdash.conf").read_text(encoding="utf-8")
    text, _, _ = mod.render(tpl, "203.0.113.7")
    assert text.count("\nignoreip = ") == 1 and "203.0.113.7" in text
