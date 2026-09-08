from contextlib import contextmanager

import database
from ban_manager import BanManager
from database import BlockedIP, Event
from monitor.process_audit import inspect_process


class FakeProc:
    def __init__(self, pid, name, cmdline=None, exe="", user="bob", parent="bash", cwd="/home/bob"):
        self.pid, self._name, self._cmdline, self._exe, self._user, self._parent, self._cwd = pid, name, cmdline or [name], exe, user, parent, cwd

    @contextmanager
    def oneshot(self):
        yield

    def name(self): return self._name
    def cmdline(self): return self._cmdline
    def exe(self): return self._exe
    def username(self): return self._user
    def cwd(self): return self._cwd
    def parent(self):
        class P:
            def name(_): return self._parent
        return P()


def test_tool_match_is_by_name_not_substring():
    assert inspect_process(FakeProc(1, "nmap", exe="/usr/bin/nmap"))["tool"] == "nmap"
    # 명령줄에 'hydra' 가 들어간 파이썬 스크립트는 더 이상 걸리지 않는다
    assert inspect_process(FakeProc(2, "python3", ["python3", "train.py", "--config", "hydra.yaml"], exe="/usr/bin/python3")) is None
    sim = inspect_process(FakeProc(3, "nmap_sim", exe="/data/repo/nmap_sim"))
    assert sim["simulation"] is True and sim["tool"] == "nmap"


def test_exec_from_tmp_indicator_severity_by_user():
    r = inspect_process(FakeProc(4, "kworker", exe="/dev/shm/.x/kworker", user="root"))
    assert r["indicator"] == "exec_from_tmp" and r["severity"] == "CRITICAL"
    r2 = inspect_process(FakeProc(5, "a.out", exe="/tmp/a.out", user="bob"))
    assert r2["severity"] == "WARNING"
    r3 = inspect_process(FakeProc(6, "nginx", exe="/usr/sbin/nginx (deleted)", user="root"))
    assert r3["indicator"] == "exe_deleted" and r3["severity"] == "INFO"


class FakeF2B:
    def __init__(self, available=True, banned=None):
        self._available, self.banned, self.jail, self.last_error = available, list(banned or []), "sshd", ""
        self.ban_calls, self.unban_calls = [], []

    def availability(self):
        return (True, "", "") if self._available else (False, "fail2ban 제어 권한 없음 (sudo 필요)", "hint")

    def ban(self, ip):
        self.ban_calls.append(ip); self.banned.append(ip); return True

    def unban(self, ip):
        self.unban_calls.append(ip); self.banned.remove(ip); return True

    def banned_ips(self):
        return list(self.banned)

    def jail_stats(self):
        return {}


def test_ban_uses_fail2ban_when_available(db):
    f = FakeF2B()
    r = BanManager(db, f).ban_ip("203.0.113.1", "brute force")
    assert r["status"] == "ACTIVE" and f.ban_calls == ["203.0.113.1"]
    row = db.query(BlockedIP).one()
    assert row.status == "ACTIVE" and row.source == "fail2ban"
    assert db.query(Event).filter(Event.event_type == "IP_BLOCKED").count() == 1
    ok, _ = BanManager(db, f).unblock_ip("203.0.113.1")
    assert ok and f.unban_calls == ["203.0.113.1"]
    db.expire_all()
    assert db.query(BlockedIP).one().status == "UNBLOCKED"


def test_ban_without_fail2ban_is_recommended_not_claimed(db):
    f = FakeF2B(available=False)
    r = BanManager(db, f).ban_ip("203.0.113.2", "brute force")
    assert r["status"] == "RECOMMENDED"
    ev = db.query(Event).filter(Event.event_type == "IP_BLOCK_RECOMMENDED").one()
    assert "fail2ban-client set sshd banip 203.0.113.2" in ev.details_dict()["command"]
    assert "차단 권고" in ev.description_ko


def test_sync_from_fail2ban_adds_and_expires(db):
    f = FakeF2B(banned=["203.0.113.5"])
    m = BanManager(db, f)
    assert m.sync_from_fail2ban() == {"banned": 1, "added": 1, "expired": 0}
    f.banned = []
    assert m.sync_from_fail2ban()["expired"] == 1
    db.expire_all()
    assert db.query(BlockedIP).one().status == "EXPIRED"


def test_package_removal_event_carries_admin_context(db):
    from monitor.intrusion import AuthLogWatcher
    from monitor.update import UpdateMonitor
    w = AuthLogWatcher(log_path="/nonexistent")
    w.process_line("Sep  8 18:32:40 host sudo:  kunmyon : TTY=pts/2 ; PWD=/ ; USER=root ; COMMAND=/usr/bin/apt-get autoremove -y")
    u = UpdateMonitor(log_path="/nonexistent", pending_interval=10**9)
    u._process_line("2026-09-08 18:32:42 remove nvidia-firmware-580-580.95.05:amd64 580.95.05-0ubuntu0.24.04.3 <none>")
    ev = db.query(Event).filter(Event.event_type == "SOFTWARE_UPDATE").one()
    ctx = ev.details_dict()["admin_context"]
    assert "apt-get autoremove" in ctx and "kunmyon" in ctx
    assert ev.details_dict()["package"] == "nvidia-firmware-580-580.95.05"


def test_parse_banned_output_and_multi_jail_sync(db):
    from integrations.fail2ban import parse_banned_output
    out = "[{'sshd': ['203.0.113.7', '198.51.100.2']}, {'recidive': ['203.0.113.7']}]"
    assert parse_banned_output(out) == {"sshd": ["203.0.113.7", "198.51.100.2"], "recidive": ["203.0.113.7"]}
    assert parse_banned_output("garbage") == {}
    m = BanManager(db, FakeF2B())
    r = m.sync_from_fail2ban({"203.0.113.7": "recidive", "198.51.100.2": "sshd"})
    assert r["added"] == 2
    rows = {b.ip_address: b.jail for b in db.query(BlockedIP).all()}
    assert rows == {"203.0.113.7": "recidive", "198.51.100.2": "sshd"}
