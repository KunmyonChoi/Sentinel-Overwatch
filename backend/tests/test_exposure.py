import database
from monitor.exposure import ExposureMonitor, classify, is_loopback, parse_expected

FW_OK = {"available": True, "backend": "ufw", "active": True, "default_incoming": "deny",
         "allowed": [{"port": 22, "proto": "tcp"}], "rules": [], "reason": "", "fix_hint": ""}
FW_UNKNOWN = {"available": False, "backend": "", "active": False, "default_incoming": "",
              "allowed": [], "rules": [], "reason": "ufw 조회 권한 없음", "fix_hint": "sudoers 에 추가하세요"}
EXPECTED = parse_expected("22/tcp")


class FakeFirewall:
    def __init__(self, snap):
        self._snap = snap

    def snapshot(self):
        return self._snap


def _alerts():
    db = database.SessionLocal()
    try:
        return db.query(database.Alert).all()
    finally:
        db.close()


def _mon(listeners, fw=FW_OK):
    mon = ExposureMonitor(firewall=FakeFirewall(fw), expected="22/tcp")
    mon.snapshot = lambda: _snapshot_from(mon, listeners, fw)
    return mon


def _snapshot_from(mon, listeners, fw):
    rows = [dict(r) for r in listeners]
    mon.fw = fw
    for r in rows:
        r.update(classify(r["address"], r["port"], r["proto"], fw, mon.expected))
    mon.listeners = rows
    return {
        "listeners": rows, "firewall": fw, "missing_process_info": False,
        "counts": {"total": len(rows), "exposed": sum(1 for r in rows if r["state"] == "exposed"),
                   "unknown": sum(1 for r in rows if r["state"] == "unknown"),
                   "loopback": sum(1 for r in rows if r["state"] == "loopback"),
                   "external_bind": sum(1 for r in rows if r["state"] != "loopback"),
                   "expected": sum(1 for r in rows if r["state"] == "expected")},
    }


L_SSH = {"address": "0.0.0.0", "port": 22, "proto": "tcp", "process": "sshd", "user": "root", "exe": "/usr/sbin/sshd", "pid": 1}
L_DEV = {"address": "0.0.0.0", "port": 8000, "proto": "tcp", "process": "python3", "user": "dev", "exe": "/usr/bin/python3", "pid": 2}
L_LOCAL = {"address": "127.0.0.1", "port": 8000, "proto": "tcp", "process": "python3", "user": "dev", "exe": "/usr/bin/python3", "pid": 2}


# --- 판정 ---
def test_loopback_detection():
    assert is_loopback("127.0.0.1") and is_loopback("127.0.0.53") and is_loopback("::1")
    assert not is_loopback("0.0.0.0") and not is_loopback("192.168.0.5")


def test_parse_expected_defaults_to_tcp():
    assert parse_expected("22, 443/udp") == {(22, "tcp"), (443, "udp")}
    assert parse_expected("") == set()


def test_loopback_is_never_exposed():
    r = classify("127.0.0.1", 8000, "tcp", FW_OK, EXPECTED)
    assert r["state"] == "loopback" and r["reachable"] is False and r["severity"] == "INFO"


def test_external_bind_allowed_by_firewall_is_exposed():
    r = classify("0.0.0.0", 9000, "tcp", {**FW_OK, "allowed": [{"port": 9000, "proto": "tcp"}]}, EXPECTED)
    assert r["state"] == "exposed" and r["reachable"] is True and r["severity"] == "WARNING"


def test_exposed_via_full_rules_snapshot():
    """요약(allowed) 이 아니라 원본 규칙(rules) 만 실린 스냅샷으로도 같은 판정이 나와야 한다."""
    fw = {"available": True, "backend": "ufw", "active": True, "default_incoming": "deny", "allowed": [],
          "rules": [{"port": 9000, "proto": "tcp", "action": "ALLOW", "from": "Anywhere", "to": "", "v6": False, "raw": ""}],
          "reason": "", "fix_hint": ""}
    assert classify("0.0.0.0", 9000, "tcp", fw, EXPECTED)["state"] == "exposed"
    assert classify("0.0.0.0", 8000, "tcp", fw, EXPECTED)["state"] == "firewalled"


def test_external_bind_blocked_by_firewall_is_informational():
    """바인딩은 넓지만 방화벽이 막는 상태 — 알림이 아니라 정보로 남긴다."""
    r = classify("0.0.0.0", 8000, "tcp", FW_OK, EXPECTED)
    assert r["state"] == "firewalled" and r["reachable"] is False and r["severity"] == "INFO"


def test_expected_port_is_not_flagged():
    r = classify("0.0.0.0", 22, "tcp", FW_OK, EXPECTED)
    assert r["state"] == "expected" and r["severity"] == "INFO"


def test_unreadable_firewall_is_unknown_not_safe():
    """방화벽을 못 읽으면 '안전'으로 단정하지 않는다."""
    r = classify("0.0.0.0", 8000, "tcp", FW_UNKNOWN, EXPECTED)
    assert r["state"] == "unknown" and r["reachable"] is None and r["severity"] == "WARNING"


# --- 모니터 ---
def test_firewalled_and_expected_listeners_raise_nothing():
    mon = _mon([L_SSH, L_DEV, L_LOCAL])
    mon.tick()
    assert _alerts() == []


def test_exposed_port_raises_alert_with_actionable_fix():
    fw = {**FW_OK, "allowed": [{"port": 22, "proto": "tcp"}, {"port": 9000, "proto": "tcp"}]}
    mon = _mon([{**L_DEV, "port": 9000}], fw=fw)
    mon.tick()
    alerts = _alerts()
    assert len(alerts) == 1
    a = alerts[0]
    assert a.rule == "exposed_port" and a.severity == "WARNING"
    assert a.fingerprint == "exposure:tcp:9000"
    assert "9000/tcp" in a.action_ko            # 의도된 공개로 등록하는 방법
    assert "ufw delete allow 9000/tcp" in a.action_ko


def test_unknown_firewall_raises_alert_pointing_at_the_fix():
    mon = _mon([L_DEV], fw=FW_UNKNOWN)
    mon.tick()
    a = _alerts()[0]
    assert "판단 불가" in a.title_ko
    assert "sudoers" in a.action_ko or "ufw status" in a.action_ko


def test_alert_resolves_when_bound_to_loopback():
    fw = {**FW_OK, "allowed": [{"port": 22, "proto": "tcp"}, {"port": 8000, "proto": "tcp"}]}
    mon = _mon([L_DEV], fw=fw)
    mon.tick()
    assert _alerts()[0].status == "OPEN"

    mon.snapshot = lambda: _snapshot_from(mon, [L_LOCAL], fw)
    mon.tick()
    assert _alerts()[0].status == "RESOLVED"


def test_repeated_tick_does_not_duplicate():
    fw = {**FW_OK, "allowed": [{"port": 8000, "proto": "tcp"}]}
    mon = _mon([L_DEV], fw=fw)
    mon.tick()
    mon.tick()
    assert len(_alerts()) == 1


def test_closed_port_is_recorded_as_event():
    fw = {**FW_OK, "allowed": [{"port": 22, "proto": "tcp"}]}
    mon = _mon([L_SSH, L_LOCAL], fw=fw)
    mon.tick()
    mon.snapshot = lambda: _snapshot_from(mon, [L_SSH], fw)
    mon.tick()

    db = database.SessionLocal()
    try:
        closed = db.query(database.Event).filter(database.Event.event_type == "PORT_CLOSED").all()
    finally:
        db.close()
    assert len(closed) == 1 and "8000" in closed[0].description


def test_health_degrades_when_firewall_unreadable():
    mon = _mon([L_LOCAL], fw=FW_UNKNOWN)
    mon.tick()
    assert mon.health == "degraded" and "방화벽" in mon.health_reason
