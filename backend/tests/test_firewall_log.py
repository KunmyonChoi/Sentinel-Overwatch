"""FirewallLogWatcher: ufw 차단 기록 파서, 스캔 판정, 하루 요약, 스캔 뒤 행동 상관 규칙."""
import os
from collections import namedtuple
from datetime import date, datetime, timedelta, timezone

import pytest

import korean
from database import Alert, Event, utcnow
from monitor import firewall_log as fl
from monitor import intrusion
from monitor.firewall_log import FirewallLogWatcher, parse_timestamp, parse_ufw_line, scan_port_key, target_key
from monitor.intrusion import AuthLogWatcher, NetworkWatcher

KST = timezone(timedelta(hours=9))
PUBLIC = "203.0.113.5"
PUBLIC2 = "198.51.100.9"
HOST = "198.51.100.2"


@pytest.fixture(autouse=True)
def reset_registry():
    fl.REGISTRY.clear()
    yield
    fl.REGISTRY.clear()


def _ts(ts):
    return (ts or datetime.now(timezone.utc)).astimezone(KST).isoformat()


def tcp(src, dpt, *, flags="SYN", ts=None, out="", inn="eth0", sim=False):
    return (f"{_ts(ts)} host kernel: [UFW BLOCK] IN={inn} OUT={out} MAC=52:54:00:12:34:56:52:54:00:65:43:21:08:00 "
            f"SRC={src} DST={HOST} LEN=44 TOS=0x00 PREC=0x00 TTL=240 ID=54321 PROTO=TCP SPT=54321 DPT={dpt} "
            f"WINDOW=1024 RES=0x00 {flags} URGP=0" + (" [SIMULATION]" if sim else ""))


def make_watcher(tmp_path, **kw):
    opts = dict(log_path=str(tmp_path / "ufw.log"), window_sec=60, port_threshold=10, followup_hours=24,
                admin_ips="", ufw_conf=str(tmp_path / "ufw.conf"))
    opts.update(kw)
    return FirewallLogWatcher(**opts)


def scan(w, ip, n=10, start=None, first_port=1000, sim=False):
    start = start or datetime.now(timezone.utc)
    for i in range(n):
        w.process_line(tcp(ip, first_port + i, ts=start + timedelta(seconds=i), sim=sim))


def scan_events(db):
    return db.query(Event).filter(Event.event_type == "FIREWALL_SCAN").all()


# --- 파서 -------------------------------------------------------------------
def test_parse_ipv4_tcp_syn_rfc3339():
    line = ("2026-09-15T20:28:01.123456+09:00 host kernel: [UFW BLOCK] IN=eth0 OUT= MAC=aa:bb SRC=203.0.113.5 "
            "DST=198.51.100.2 LEN=44 TOS=0x00 PREC=0x00 TTL=240 ID=54321 PROTO=TCP SPT=54321 DPT=23 WINDOW=1024 "
            "RES=0x00 SYN URGP=0")
    p = parse_ufw_line(line)
    assert p["src"] == "203.0.113.5" and p["dst"] == "198.51.100.2"
    assert (p["proto"], p["spt"], p["dpt"], p["flags"]) == ("TCP", 54321, 23, ["SYN"])
    assert p["inbound"] is True and p["simulation"] is False
    assert p["ts"] == datetime(2026, 9, 15, 11, 28, 1, 123456)
    assert scan_port_key(p) == "23/tcp"


def test_parse_traditional_timestamp_and_year_rollover():
    line = tcp(PUBLIC, 22).split(" ", 1)[1]
    trad = "Sep 15 20:28:01 " + line
    p = parse_ufw_line(trad, now=datetime(2026, 9, 15, 12, 0), tz=KST)
    assert p["ts"] == datetime(2026, 9, 15, 11, 28, 1)
    # 12월 31일 기록을 1월 1일에 읽으면 작년이다
    assert parse_timestamp("Dec 31 23:59:59 host kernel: x", now=datetime(2027, 1, 1, 0, 10), tz=timezone.utc) \
        == datetime(2026, 12, 31, 23, 59, 59)
    # 한 자리 날짜(공백 두 칸)와 시간대 없는 로컬 해석도 읽는다
    assert parse_timestamp("Sep  5 01:02:03 host kernel: x") is not None
    assert parse_timestamp("2026-09-15T20:28:01Z host kernel: x") == datetime(2026, 9, 15, 20, 28, 1)


def test_parse_ipv6_udp_icmp():
    v6 = ("2026-09-15T20:28:01+09:00 host kernel: [UFW BLOCK] IN=eth0 OUT= MAC=aa SRC=2001:db8::1 DST=2001:db8::2 "
          "LEN=80 TC=0 HOPLIMIT=52 FLOWLBL=0 PROTO=TCP SPT=40000 DPT=3389 WINDOW=64 RES=0x00 SYN URGP=0")
    p = parse_ufw_line(v6)
    assert p["src"] == "2001:db8::1" and p["dpt"] == 3389 and scan_port_key(p) == "3389/tcp"

    udp = ("Sep 15 20:28:01 host kernel: [12345.678901] [UFW BLOCK] IN=eth0 OUT= MAC=aa SRC=192.0.2.7 "
           "DST=198.51.100.2 LEN=40 TOS=0x00 PREC=0x00 TTL=50 ID=1 PROTO=UDP SPT=5353 DPT=161 LEN=20")
    p = parse_ufw_line(udp)
    assert p["proto"] == "UDP" and p["flags"] == [] and scan_port_key(p) == "161/udp"

    # ICMP 오류는 원래 패킷을 [SRC=… ] 로 한 번 더 싣는다 — 바깥 값이 이긴다
    icmp = ("2026-09-15T20:28:01+09:00 host kernel: [UFW BLOCK] IN=eth0 OUT= MAC=aa SRC=192.0.2.8 DST=198.51.100.2 "
            "LEN=84 PROTO=ICMP TYPE=3 CODE=3 [SRC=198.51.100.2 DST=192.0.2.8 LEN=56 PROTO=UDP SPT=53 DPT=33434 ]")
    p = parse_ufw_line(icmp)
    assert p["src"] == "192.0.2.8" and p["proto"] == "ICMP" and p["dpt"] is None
    assert scan_port_key(p) is None and target_key(p) == "icmp"


def test_parse_rejects_garbage_and_other_actions():
    for line in (
        "",
        "hello world",
        "Sep 15 20:28:01 host kernel: [UFW BLOCK] IN=eth0 OUT= SRC=not-an-ip PROTO=TCP DPT=22 SYN",
        "Sep 15 20:28:01 host kernel: [UFW BLOCK] IN=eth0 OUT= DST=198.51.100.2 PROTO=TCP",
        "Sep 15 20:28:01 host kernel: [UFW BLOCK] IN=eth0 OUT= SRC=203.0.113.5",
        tcp(PUBLIC, 22).replace("[UFW BLOCK]", "[UFW AUDIT]"),
        tcp(PUBLIC, 22).replace("[UFW BLOCK]", "[UFW ALLOW]"),
    ):
        assert parse_ufw_line(line) is None
    # ACK 만 달린 TCP(끝난 연결의 늦은 패킷)는 스캔 포트로 세지 않는다
    assert scan_port_key(parse_ufw_line(tcp(PUBLIC, 443, flags="ACK FIN"))) is None
    assert scan_port_key(parse_ufw_line(tcp(PUBLIC, 443, flags="ACK SYN"))) is None


def test_malformed_lines_are_counted_not_raised(tmp_path, db):
    w = make_watcher(tmp_path)
    w.process_line("Sep 15 20:28:01 host kernel: [UFW BLOCK] IN=eth0 garbage")
    w.process_line("random kernel line")
    assert w.stats["malformed"] == 1 and w.stats["lines"] == 2
    assert db.query(Event).count() == 0


# --- 스캔 판정 ----------------------------------------------------------------
def test_threshold_records_one_info_event_per_episode(tmp_path, db):
    w = make_watcher(tmp_path)
    scan(w, PUBLIC, n=9)
    assert scan_events(db) == []
    w.process_line(tcp(PUBLIC, 5000))
    evs = scan_events(db)
    assert len(evs) == 1 and evs[0].severity == "INFO" and not evs[0].is_simulation
    d = evs[0].details_dict()
    assert d["ip"] == PUBLIC and d["port_count"] == 10 and d["lower_bound"] is True
    assert "1000/tcp" in d["ports"] and d["first_seen"] <= d["last_seen"]
    assert "최소치" in evs[0].description_ko
    # 같은 차례에 계속 두드려도 이벤트는 하나 — 목록에서 포트·건수만 늘어난다
    scan(w, PUBLIC, n=30, first_port=2000)
    assert len(scan_events(db)) == 1
    ep = fl.REGISTRY.get(PUBLIC)
    assert ep.port_count == 40 and len(ep.as_dict()["ports"]) == ep.PORT_SAMPLE
    # 공인 IP 의 스캔만으로는 알림이 없다
    assert db.query(Alert).count() == 0


def test_ports_spread_beyond_window_are_not_a_scan(tmp_path, db):
    w = make_watcher(tmp_path)
    start = datetime.now(timezone.utc) - timedelta(minutes=20)
    for i in range(12):
        w.process_line(tcp(PUBLIC, 1000 + i, ts=start + timedelta(seconds=70 * i)))
    assert scan_events(db) == []


def test_single_port_hammering_is_counted_but_not_a_scan(tmp_path, db):
    w = make_watcher(tmp_path)
    for _ in range(50):
        w.process_line(tcp(PUBLIC2, 23))
    assert scan_events(db) == []
    top = w.status_payload()["today"]["top_sources"][0]
    assert top == {"ip": PUBLIC2, "packets": 50, "top_port": "23/tcp", "scanned": False}


def test_new_episode_after_quiet_gap(tmp_path, db):
    w = make_watcher(tmp_path)
    start = datetime.now(timezone.utc) - timedelta(hours=3)
    scan(w, PUBLIC, start=start)
    scan(w, PUBLIC, start=start + timedelta(hours=2), first_port=3000)
    assert len(scan_events(db)) == 2


def test_tracker_memory_is_bounded_and_evicts_oldest(tmp_path, db):
    w = make_watcher(tmp_path, max_tracked=3)
    ips = ["192.0.2.1", "192.0.2.2", "192.0.2.3", "192.0.2.4"]
    for ip in ips:
        scan(w, ip, n=5)
    assert list(w._trackers) == ips[1:] and w.stats["evicted"] == 1
    # 쫓겨난 IP 는 처음부터 다시 센다
    scan(w, ips[0], n=5, first_port=1005)
    assert scan_events(db) == []


def test_admin_and_loopback_are_excluded_private_is_kept(tmp_path, db):
    w = make_watcher(tmp_path, admin_ips="203.0.113.0/24 192.0.2.10")
    scan(w, PUBLIC)
    scan(w, "127.0.0.1")
    scan(w, "::1")
    assert scan_events(db) == [] and w.stats["excluded"] == 30
    assert fl.REGISTRY.get(PUBLIC) is None
    # 사설 대역은 남긴다 (규칙 c 대상)
    scan(w, "10.0.0.5")
    assert len(scan_events(db)) == 1


def test_outbound_blocks_are_not_scans(tmp_path, db):
    w = make_watcher(tmp_path)
    for i in range(12):
        w.process_line(tcp(PUBLIC, 1000 + i, inn="", out="eth0"))
    assert scan_events(db) == [] and w.stats["not_inbound"] == 12


# --- 규칙 c: 내부망 스캔 --------------------------------------------------------
def test_internal_scan_warns_immediately_once_per_episode(tmp_path, db):
    w = make_watcher(tmp_path)
    scan(w, "192.168.1.50", n=15)
    a = db.query(Alert).filter(Alert.rule == "internal_scan").one()
    assert a.severity == "WARNING" and a.fingerprint == "internal_scan:192.168.1.50" and a.count == 1
    assert "최소치" in a.summary_ko and "차단하지 않았습니다" in a.summary_ko
    assert "ip neigh" in a.action_ko
    assert scan_events(db)[0].details_dict()["internal"] is True


def test_documentation_ranges_are_not_internal():
    # ipaddress.is_private 는 문서용 대역도 사설로 본다 — 내부망 판정은 그러면 안 된다
    assert not fl.is_internal_ip("203.0.113.5") and not fl.is_internal_ip("2001:db8::1")
    assert fl.is_internal_ip("10.1.2.3") and fl.is_internal_ip("fd00::1") and fl.is_internal_ip("100.64.0.9")


def test_simulation_lines_are_tagged_and_kept_out_of_daily(tmp_path, db):
    w = make_watcher(tmp_path)
    scan(w, "192.168.1.200", sim=True)
    ev = scan_events(db)[0]
    assert ev.is_simulation is True
    assert db.query(Alert).filter(Alert.rule == "internal_scan").one().is_simulation is True
    assert w.daily.total == 0


# --- 하루 요약 ----------------------------------------------------------------
def test_daily_aggregate_is_an_info_event_without_alerts(tmp_path, db):
    w = make_watcher(tmp_path)
    scan(w, PUBLIC)
    for _ in range(5):
        w.process_line(tcp(PUBLIC2, 23))
    w.process_line(tcp("192.0.2.99", 22, sim=True))
    w.daily.day = date(2026, 9, 14)
    w._local_date = lambda: date(2026, 9, 15)
    w._maybe_roll_day()

    ev = db.query(Event).filter(Event.event_type == "FIREWALL_DAILY").one()
    d = ev.details_dict()
    assert ev.severity == "INFO" and d["date"] == "2026-09-14"
    assert d["total_blocked"] == 15 and d["scanning_ips"] == 1 and d["partial"] is True
    assert d["top_sources"][0]["ip"] == PUBLIC and d["top_sources"][0]["scanned"] is True
    assert {"port": "23/tcp", "packets": 5} in d["top_ports"]
    assert "최소치" in ev.description_ko
    assert db.query(Alert).count() == 0
    # 새 날은 0 부터, 자정에 시작했으니 partial 아님
    assert w.daily.total == 0 and w.daily.partial is False and w.daily.day == date(2026, 9, 15)
    w._maybe_roll_day()
    assert db.query(Event).filter(Event.event_type == "FIREWALL_DAILY").count() == 1


def test_status_payload_shape(tmp_path):
    w = make_watcher(tmp_path)
    scan(w, PUBLIC)
    s = w.status_payload()
    assert s["settings"] == {"window_sec": 60, "port_threshold": 10, "followup_hours": 24, "episode_gap_min": 60}
    assert s["episodes"][0]["ip"] == PUBLIC and s["episodes"][0]["active"] is True
    assert s["today"]["total_blocked"] == 10 and "최소치" in s["lower_bound_note_ko"]


# --- 규칙 a: 스캔 뒤 SSH 인증 ------------------------------------------------------
def auth_watcher():
    w = AuthLogWatcher(log_path="/nonexistent/auth.log", ban_manager_factory=lambda db: None)
    w.threshold = 100          # 브루트포스 규칙과 섞이지 않게
    return w


def fail(ip, user="admin"):
    return f"Sep 15 20:30:00 host sshd[1]: Failed password for invalid user {user} from {ip} port 4444 ssh2"


def accept(ip, user="deploy"):
    return f"Sep 15 20:31:00 host sshd[1]: Accepted publickey for {user} from {ip} port 4444 ssh2: ED25519 SHA256:x"


def test_no_alert_without_followup_and_auth_before_scan_does_not_count(tmp_path, db):
    a = auth_watcher()
    a.process_line(fail(PUBLIC))            # 스캔보다 먼저
    w = make_watcher(tmp_path)
    scan(w, PUBLIC, start=datetime.now(timezone.utc) + timedelta(seconds=2))
    assert db.query(Alert).count() == 0
    # 다른 IP 의 시도는 상관없다
    a.process_line(fail(PUBLIC2))
    assert db.query(Alert).count() == 0


def test_scan_then_auth_failure_warns_once(tmp_path, db):
    w = make_watcher(tmp_path)
    scan(w, PUBLIC)
    a = auth_watcher()
    a.process_line(fail(PUBLIC, "root"))
    a.process_line(fail(PUBLIC, "oracle"))
    al = db.query(Alert).filter(Alert.rule == "scan_then_auth").one()
    assert al.severity == "WARNING" and al.count == 1 and al.fingerprint == f"scan_then_auth:{PUBLIC}:attempt"
    assert "최소치" in al.summary_ko and "차단하지 않았습니다" in al.summary_ko
    assert al.details_dict()["scan"]["port_count"] == 10


def test_auth_during_scan_is_caught_by_backcheck(tmp_path, db):
    w = make_watcher(tmp_path)
    start = datetime.now(timezone.utc) - timedelta(seconds=30)
    for i in range(5):
        w.process_line(tcp(PUBLIC, 1000 + i, ts=start + timedelta(seconds=i)))
    auth_watcher().process_line(fail(PUBLIC))   # 스캔 도중, 아직 임계치 전
    assert db.query(Alert).count() == 0
    for i in range(5, 10):
        w.process_line(tcp(PUBLIC, 1000 + i, ts=start + timedelta(seconds=i)))
    assert db.query(Alert).filter(Alert.rule == "scan_then_auth").count() == 1


def test_scan_then_successful_login_warns(tmp_path, db):
    w = make_watcher(tmp_path)
    scan(w, PUBLIC)
    auth_watcher().process_line(accept(PUBLIC, "deploy"))
    al = db.query(Alert).filter(Alert.rule == "scan_then_auth").one()
    assert al.severity == "WARNING" and al.fingerprint == f"scan_then_auth:{PUBLIC}:login:deploy"
    assert "deploy" in al.title_ko


def test_login_after_failures_gets_scan_context_not_a_duplicate(tmp_path, db):
    w = make_watcher(tmp_path)
    scan(w, PUBLIC)
    a = auth_watcher()
    a.process_line(fail(PUBLIC, "bob"))
    a.process_line("Sep 15 20:31:00 host sshd[1]: Accepted password for bob from 203.0.113.5 port 4444 ssh2")
    crit = db.query(Alert).filter(Alert.rule == "login_after_failures").one()
    assert crit.severity == "CRITICAL" and crit.details_dict()["prior_scan"]["ip"] == PUBLIC
    assert "스캔" in crit.summary_ko
    assert db.query(Alert).filter(Alert.fingerprint.like("%:login:%")).count() == 0


def test_followup_window_expires_and_admin_scans_never_register(tmp_path, db):
    w = make_watcher(tmp_path)
    scan(w, PUBLIC)
    later = utcnow() + timedelta(hours=25)
    assert fl.note_auth_activity(PUBLIC, "auth_failure", user="x", now=later) is False
    assert db.query(Alert).count() == 0

    fl.REGISTRY.clear()
    admin = make_watcher(tmp_path, admin_ips=PUBLIC)
    scan(admin, PUBLIC)
    auth_watcher().process_line(fail(PUBLIC))
    assert db.query(Alert).count() == 0


def test_registry_is_restored_from_events_after_restart(tmp_path, db):
    w = make_watcher(tmp_path)
    scan(w, PUBLIC, n=12)
    fl.REGISTRY.clear()
    make_watcher(tmp_path)._seed_registry()
    ep = fl.REGISTRY.get(PUBLIC)
    # 이벤트는 판정 순간의 값(10개)을 남긴다 — 그 뒤 늘어난 포트는 메모리에만 있었다
    assert ep is not None and ep.port_count == 10 and ep.notified == set()
    auth_watcher().process_line(fail(PUBLIC))
    assert db.query(Alert).filter(Alert.rule == "scan_then_auth").count() == 1


# --- 규칙 b: 스캔 뒤 리스닝 포트 연결 ------------------------------------------------
Addr = namedtuple("Addr", "ip port")
Conn = namedtuple("Conn", "fd family type laddr raddr status pid")


def network_watcher(monkeypatch, conns):
    monkeypatch.setattr(intrusion.psutil, "net_connections", lambda kind="inet": conns)
    monkeypatch.setattr(intrusion, "_proc_info", lambda pid: {"process": "nginx", "user": "www-data",
                                                              "exe": "/usr/sbin/nginx", "pid": pid})
    nw = NetworkWatcher()
    nw.known_listeners = {"0.0.0.0:8080/nginx"}
    return nw


def test_scan_then_connection_to_listening_port(tmp_path, db, monkeypatch):
    conns = [
        Conn(3, 2, 1, Addr("0.0.0.0", 8080), (), "LISTEN", 42),
        Conn(4, 2, 1, Addr(HOST, 8080), Addr(PUBLIC, 51000), "ESTABLISHED", 42),
        # 이 서버가 스캔한 IP 로 '나가는' 연결은 해당 없음
        Conn(5, 2, 1, Addr(HOST, 40000), Addr(PUBLIC, 443), "ESTABLISHED", 43),
    ]
    nw = network_watcher(monkeypatch, conns)
    nw.tick()
    assert db.query(Alert).filter(Alert.rule == "scan_then_connection").count() == 0   # 스캔 전

    scan(make_watcher(tmp_path), PUBLIC)
    nw.tick()
    nw.tick()
    al = db.query(Alert).filter(Alert.rule == "scan_then_connection").one()
    assert al.severity == "WARNING" and al.count == 1
    assert al.fingerprint == f"scan_then_connection:{PUBLIC}:8080" and "nginx" in al.title_ko
    assert "최소치" in al.summary_ko and "ufw" in al.action_ko


# --- 로테이션과 health ------------------------------------------------------------
def test_starts_at_end_and_follows_rotation(tmp_path, db):
    log = tmp_path / "ufw.log"
    log.write_text("".join(tcp(PUBLIC2, 100 + i) + "\n" for i in range(12)))   # 지난 기록은 읽지 않는다
    w = make_watcher(tmp_path)
    w.setup()
    assert w.health == "ok"
    w.tick()
    assert scan_events(db) == []

    with open(log, "a") as f:
        f.writelines(tcp(PUBLIC, 1000 + i) + "\n" for i in range(5))
    w.tick()
    os.rename(log, tmp_path / "ufw.log.1")
    log.write_text("".join(tcp(PUBLIC, 2000 + i) + "\n" for i in range(5)))
    w.tick()            # 로테이션 감지 → 새 파일을 처음부터 다시 연다
    w.tick()
    evs = scan_events(db)
    assert len(evs) == 1 and evs[0].details_dict()["ip"] == PUBLIC


def test_missing_log_is_degraded_with_fix_hint(tmp_path):
    w = make_watcher(tmp_path)
    w.setup()
    assert w.health == "degraded" and "ufw.log" in w.health_reason
    assert "sudo ufw logging low" in w.fix_hint


@pytest.mark.skipif(os.geteuid() == 0, reason="root 는 권한과 무관하게 읽는다")
def test_unreadable_log_is_degraded_with_adm_hint(tmp_path):
    log = tmp_path / "ufw.log"
    log.write_text("")
    log.chmod(0)
    try:
        w = make_watcher(tmp_path)
        w.setup()
        assert w.health == "degraded" and "권한" in w.health_reason and "adm" in w.fix_hint
    finally:
        log.chmod(0o600)


def test_ufw_conf_disabled_or_logging_off_is_degraded(tmp_path):
    (tmp_path / "ufw.log").write_text("")
    conf = tmp_path / "ufw.conf"
    conf.write_text("# comment\nENABLED=no\nLOGLEVEL=low\n")
    w = make_watcher(tmp_path)
    w.setup()
    assert w.health == "degraded" and "ENABLED=no" in w.health_reason and "OpenSSH" in w.fix_hint

    conf.write_text("ENABLED=yes\nLOGLEVEL=off\n")
    w._check_ufw_conf()
    assert w.health == "degraded" and w.fix_hint == "sudo ufw logging low"

    conf.write_text("ENABLED=yes\nLOGLEVEL=low\n")
    w._check_ufw_conf()
    assert w.health == "ok" and w.ufw_conf_state == "enabled"


def test_long_quiet_period_is_info_not_degraded(tmp_path):
    (tmp_path / "ufw.log").write_text("")
    w = make_watcher(tmp_path)
    w.setup()
    assert w.quiet_note() == ""
    w.last_block_at = utcnow() - timedelta(hours=30)
    assert "24시간" in w.quiet_note() and w.health == "ok"


def test_korean_templates():
    assert korean.event_type_ko("FIREWALL_SCAN") != "FIREWALL_SCAN"
    text = korean.event_ko("FIREWALL_SCAN", {"ip": "10.0.0.5", "window_sec": 60, "port_count": 12, "internal": True})
    assert "내부망" in text and "12개" in text
