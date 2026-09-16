"""확인(ACKED)한 알림이 어떻게 끝나는가.

세 갈래를 확인한다.
  1. 쉬운 화면의 해결 경로: '다 했어요'(해결)와 '읽었지만 아직 못 했어요'(확인)가 다른 상태가 되는지
  2. 조건 해소 자동 해결: 포트가 닫히고, 프로세스 수가 돌아오고, 제거된 패키지가 다시 설치될 때
  3. 노후 정리: 확인만 된 채 오래된 알림을 정리하되 침입 신호는 건드리지 않는지
"""
import datetime
import types

import pytest
from fastapi.testclient import TestClient

import alerts
import config
import database
from alerts import raise_alert
from database import Alert, Event

H = {"X-API-Token": "test-token"}


@pytest.fixture
def client():
    # lifespan 을 띄우지 않는다 (프로젝트 관례). 모니터를 기동하면 테스트마다 상태가 섞인다.
    import app as app_module
    return TestClient(app_module.app)


def _mk(rule, fp=None, sev="WARNING", status=None, last_seen=None, note=None):
    a, _ = raise_alert(rule, sev, rule, fingerprint=fp or f"{rule}:x", title_ko=rule)
    if status or last_seen or note:
        db = database.SessionLocal()
        try:
            row = db.get(Alert, a.id)
            if status:
                row.status = status
                if status == "ACKED":
                    row.acked_at, row.acked_by = database.utcnow(), "사용자"
            if last_seen:
                row.last_seen_at = last_seen
            if note:
                row.resolution_note = note
            db.commit()
        finally:
            db.close()
    return a.id


def _get(alert_id):
    db = database.SessionLocal()
    try:
        return db.get(Alert, alert_id)
    finally:
        db.close()


def _one(rule):
    db = database.SessionLocal()
    try:
        return db.query(Alert).filter(Alert.rule == rule).one()
    finally:
        db.close()


def _events(event_type):
    db = database.SessionLocal()
    try:
        return db.query(Event).filter(Event.event_type == event_type).all()
    finally:
        db.close()


def _old(days):
    return database.utcnow() - datetime.timedelta(days=days)


# --- 1. 쉬운 화면의 해결 경로 -------------------------------------------------

def test_plain_screen_can_resolve_a_guide_task(client):
    """'알려주신 대로 다 했어요'는 확인이 아니라 해결이다 (전문가 화면의 '해결'과 같은 상태)."""
    i = _mk("exposed_port", fp="exposure:tcp:8080")
    r = client.post("/api/alerts/respond", headers=H,
                    json={"ids": [i], "answer": "fixed", "by": "사용자", "note": "쉬운 화면에서 조치를 마쳤다고 답함"})
    assert r.status_code == 200 and r.json()["updated"] == 1
    a = _get(i)
    assert a.status == "RESOLVED" and a.resolved_by == "사용자" and a.resolved_at is not None
    assert a.details_dict()["user_response"] == "fixed"
    assert "조치를 마쳤다" in (a.resolution_note or "")


def test_plain_screen_ack_is_not_a_resolve(client):
    """'읽었지만 아직 못 했어요'는 봤다는 표시일 뿐이다. 해결로 바꾸면 남은 일이 사라진다."""
    i = _mk("exposed_port", fp="exposure:tcp:8081")
    r = client.post("/api/alerts/ack-all", headers=H,
                    json={"ids": [i], "by": "사용자", "note": "쉬운 화면에서 확인만 함 (조치는 아직)"})
    assert r.status_code == 200 and r.json()["acked"] == 1
    a = _get(i)
    assert a.status == "ACKED" and a.resolved_at is None
    assert "조치는 아직" in (a.resolution_note or "")


# --- 2. 조건 해소 자동 해결 ---------------------------------------------------

def _conn(port, pid=101, ip="0.0.0.0", status="LISTEN"):
    return types.SimpleNamespace(status=status, laddr=types.SimpleNamespace(ip=ip, port=port), raddr=None, pid=pid)


def _net(monkeypatch, intrusion, conns):
    monkeypatch.setattr(intrusion.psutil, "net_connections", lambda kind="inet": conns)


def test_new_listener_alert_closes_when_the_port_closes(monkeypatch):
    """문이 닫혔으면 알림도 닫는다 — 이미 없는 일을 목록에 남겨두지 않는다."""
    from monitor import intrusion
    monkeypatch.setattr(intrusion, "_proc_info",
                        lambda pid: {"process": "python3" if pid else None, "exe": "/usr/bin/python3",
                                     "user": "svc", "pid": pid})
    w = intrusion.NetworkWatcher()
    _net(monkeypatch, intrusion, [_conn(9101)])
    w.tick()
    a = _one("new_listener")
    assert a.status == "OPEN" and a.fingerprint == "listener:9101:python3"

    # 확인만 해둔 상태에서도 정리된다 (auto_resolve 는 OPEN/ACKED 를 모두 닫는다)
    db = database.SessionLocal()
    try:
        assert alerts.ack_all(db, "사용자") == 1
    finally:
        db.close()

    _net(monkeypatch, intrusion, [])
    w.tick()
    closed = _get(a.id)
    assert closed.status == "RESOLVED" and closed.resolved_by == "system"
    assert "더는 열려 있지 않음" in closed.resolution_note


def test_new_listener_alert_survives_while_the_port_is_still_open(monkeypatch):
    from monitor import intrusion
    monkeypatch.setattr(intrusion, "_proc_info",
                        lambda pid: {"process": "python3", "exe": "/usr/bin/python3", "user": "svc", "pid": pid})
    w = intrusion.NetworkWatcher()
    _net(monkeypatch, intrusion, [_conn(9102)])
    w.tick()
    w.tick()
    assert _one("new_listener").status == "OPEN"


def test_new_listener_is_not_closed_when_a_socket_has_no_process(monkeypatch):
    """프로세스를 귀속하지 못한 주기에는 아무것도 닫지 않는다.

    지문에 프로세스 이름이 들어가므로, 이름을 모르는 채로 대조하면 아직 열려 있는 문을 닫는다.
    """
    from monitor import intrusion
    monkeypatch.setattr(intrusion, "_proc_info",
                        lambda pid: {"process": "python3" if pid else None, "exe": None, "user": None, "pid": pid})
    w = intrusion.NetworkWatcher()
    _net(monkeypatch, intrusion, [_conn(9103, pid=101)])
    w.tick()
    first = _one("new_listener")

    _net(monkeypatch, intrusion, [_conn(9104, pid=None)])
    w.tick()
    assert _get(first.id).status == "OPEN"


def test_process_spike_resolves_when_the_count_comes_back(monkeypatch):
    """급증 직전 수준으로 돌아왔을 때만 닫는다. 늘어난 프로세스가 남아 있으면 그대로 둔다."""
    from monitor import resource
    monkeypatch.setattr(resource, "time_synchronized", lambda: None)
    monkeypatch.setattr(resource.psutil, "cpu_percent", lambda interval=None: 1.0)
    monkeypatch.setattr(resource.psutil, "virtual_memory",
                        lambda: types.SimpleNamespace(percent=10.0, used=1024, total=8192))
    monkeypatch.setattr(resource.psutil, "disk_usage", lambda p: types.SimpleNamespace(percent=10.0))
    seq = iter([100, 200, 180, 100])
    monkeypatch.setattr(resource.psutil, "pids", lambda: [0] * next(seq))

    m = resource.ResourceMonitor()
    m.tick()                                  # 기준선 100
    m.tick()                                  # 200 → 급증 알림
    a = _one("process_spike")
    assert a.status == "OPEN" and m._spike_base == 100

    db = database.SessionLocal()
    try:
        alerts.ack_alert(a.id, "사용자", db)
    finally:
        db.close()

    m.tick()                                  # 180 — 아직 기준선 위다
    assert _get(a.id).status == "ACKED"

    m.tick()                                  # 100 — 급증 직전 수준으로 복귀
    closed = _get(a.id)
    assert closed.status == "RESOLVED" and "급증 직전 수준" in closed.resolution_note


def _removal_line(pkg="fail2ban"):
    return f"2026-09-10 10:00:00 remove {pkg}:amd64 1.0.2-3 <none>"


def test_security_package_alert_resolves_when_the_package_is_back(monkeypatch):
    from monitor import update as U
    u = U.UpdateMonitor(log_path="/nonexistent", pending_interval=10**9)
    u._process_line(_removal_line())
    a = _one("security_package_removed")
    assert a.status == "OPEN" and a.fingerprint == "pkg_removed:fail2ban"

    # 목록을 못 읽으면 아무 판단도 하지 않는다 (못 읽은 것을 '복구됨'으로 바꾸면 조용히 지우는 셈)
    monkeypatch.setattr(U.apt, "installed_packages", lambda: {})
    u._recheck_removed_packages()
    assert _get(a.id).status == "OPEN"

    monkeypatch.setattr(U.apt, "installed_packages", lambda: {"fail2ban": "1.1.0-1"})
    u._recheck_removed_packages()
    closed = _get(a.id)
    assert closed.status == "RESOLVED" and "다시 설치" in closed.resolution_note and "1.1.0-1" in closed.resolution_note


def test_reinstall_line_closes_the_removal_alert():
    """dpkg 로그에서 재설치를 본 그 자리에서 닫는다 (확인만 해둔 알림도 함께)."""
    from monitor import update as U
    u = U.UpdateMonitor(log_path="/nonexistent", pending_interval=10**9)
    u._process_line(_removal_line("ufw"))
    a = _one("security_package_removed")
    db = database.SessionLocal()
    try:
        alerts.ack_alert(a.id, "사용자", db)
    finally:
        db.close()
    u._process_line("2026-09-10 11:00:00 install ufw:amd64 <none> 0.36.2-6")
    closed = _get(a.id)
    assert closed.status == "RESOLVED" and "0.36.2-6" in closed.resolution_note


# --- 3. 확인만 된 알림의 노후 정리 --------------------------------------------

def test_ageing_resolves_state_class_acked_alerts():
    i = _mk("exposed_port", fp="exposure:tcp:9001", status="ACKED", last_seen=_old(40), note="사용자가 확인")
    r = alerts.age_out_acked(days=30)
    assert r["resolved"] == 1 and r["kept"] == 0
    a = _get(i)
    assert a.status == "RESOLVED" and a.resolved_by == "system"
    assert "시간이 지나 닫은 것" in a.resolution_note
    assert "이전 메모: 사용자가 확인" in a.resolution_note      # 사람이 남긴 메모를 지우지 않는다
    ev = _events("ALERT_AGED")
    assert len(ev) == 1 and "1건" in ev[0].description_ko


INTRUSION_RULES = (
    "brute_force", "login_after_failures", "root_ssh_login", "new_login_ip", "sudo_failure",
    "account_change", "integrity_change", "persistence_cron", "persistence_systemd", "persistence_suid",
    "kernel_module", "ld_preload_write", "security_tool", "proc_exec_from_tmp", "proc_reverse_shell",
    "port_scan", "scan_then_auth", "scan_then_connection", "internal_scan", "monitor_blind_spot",
)


def test_ageing_never_closes_intrusion_signals():
    """'다시 안 보인다'가 '처리됐다'는 뜻이 아니다. 대신 남겨뒀다는 사실을 기록으로 남긴다."""
    kept = [_mk(rule, fp=f"{rule}:198.51.100.7", status="ACKED", last_seen=_old(400)) for rule in INTRUSION_RULES]
    r = alerts.age_out_acked(days=30)
    assert r["resolved"] == 0 and r["kept"] == len(kept)
    assert sorted(r["kept_rules"]) == sorted(INTRUSION_RULES)
    assert all(_get(i).status == "ACKED" for i in kept)
    assert all(_get(i).resolved_at is None for i in kept)
    ev = _events("ALERT_AGED")
    assert len(ev) == 1 and "닫지 않고" in ev[0].description_ko


def test_ageing_leaves_open_and_recent_alerts_alone():
    op = _mk("exposed_port", fp="exposure:tcp:9002", last_seen=_old(400))                      # 아직 미확인
    recent = _mk("exposed_port", fp="exposure:tcp:9003", status="ACKED", last_seen=_old(3))    # 최근에 봤다
    assert alerts.age_out_acked(days=30)["resolved"] == 0
    assert _get(op).status == "OPEN" and _get(recent).status == "ACKED"
    assert _events("ALERT_AGED") == []


def test_ageing_can_be_turned_off():
    i = _mk("exposed_port", fp="exposure:tcp:9004", status="ACKED", last_seen=_old(400))
    r = alerts.age_out_acked(days=0)
    assert r["enabled"] is False and r["resolved"] == 0
    assert _get(i).status == "ACKED"


def test_ageing_uses_the_configured_default(monkeypatch):
    monkeypatch.setattr(config, "ACKED_AGE_DAYS", 5)
    i = _mk("lynis_warning", fp="lynis:warn:AUTH-9262", status="ACKED", last_seen=_old(6))
    assert alerts.age_out_acked()["resolved"] == 1
    assert _get(i).status == "RESOLVED"


def test_ageing_moves_the_alert_but_retention_still_keeps_it():
    """지우지 않는다. 방금 정리한 것은 보존 기간이 남아 기록에 그대로 있다."""
    i = _mk("exposed_port", fp="exposure:tcp:9006", status="ACKED", last_seen=_old(400))
    alerts.age_out_acked(days=30)
    database.apply_retention()
    assert _get(i).status == "RESOLVED"

    db = database.SessionLocal()
    try:
        db.get(Alert, i).resolved_at = _old(config.ALERT_RETENTION_DAYS + 1)
        db.commit()
    finally:
        db.close()
    database.apply_retention()
    assert _get(i) is None      # 보존 기간이 지난 뒤에야 삭제된다
