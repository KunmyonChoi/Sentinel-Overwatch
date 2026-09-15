import pytest
from fastapi.testclient import TestClient

import alerts
import database
from monitor.intel import match_usn, parse_rss

H = {"X-API-Token": "test-token"}


def test_parse_rss_and_usn_matching():
    xml = b"""<rss><channel><item><title>USN-1-1: foo vulnerability</title><link>https://u/USN-1-1</link>
    <guid isPermaLink="false">https://u/USN-1-1</guid><description>d</description></item></channel></rss>"""
    items = parse_rss(xml)
    assert items[0]["guid"] == "https://u/USN-1-1" and items[0]["title"].startswith("USN-1-1")
    rel = {"noble": [
        {"name": "foo", "version": "1.0-2", "is_source": True},
        {"name": "foo", "version": "1.0-2", "is_source": False},
        {"name": "libfoo1", "version": "1.0-2", "is_source": False},
        {"name": "bar", "version": "9", "is_source": False},
    ]}
    installed = {"foo": "1.0-1", "libfoo1": "1.0-2", "unrelated": "1"}
    hits = match_usn(rel, "noble", installed)
    assert hits == [{"package": "foo", "installed": "1.0-1", "fixed": "1.0-2"}]
    assert match_usn(rel, "jammy", installed) == []


@pytest.fixture
def client():
    import app as app_module
    return TestClient(app_module.app)


def test_api_requires_token(client):
    assert client.get("/api/alerts").status_code == 401
    assert client.get("/api/alerts", headers={"X-API-Token": "wrong"}).status_code == 401
    assert client.get("/api/alerts", headers=H).status_code == 200


def test_alert_ack_resolve_flow(client, db):
    a, _ = alerts.raise_alert("r", "CRITICAL", "t", fingerprint="api:1", title_ko="테스트 알림", action_ko="확인")
    stats = client.get("/api/stats", headers=H).json()
    assert stats["status"] == "DEFCON 1" and stats["reason"] == "테스트 알림"
    r = client.post(f"/api/alerts/{a.id}/ack", headers=H, json={"by": "tester"})
    assert r.status_code == 200 and r.json()["status"] == "ACKED"
    assert client.get("/api/stats", headers=H).json()["status"] == "SAFE"
    r = client.post(f"/api/alerts/{a.id}/resolve", headers=H, json={"by": "tester", "note": "false positive"})
    assert r.json()["status"] == "RESOLVED" and r.json()["resolution_note"] == "false positive"
    assert client.get("/api/alerts?status=active", headers=H).json() == []
    assert len(client.get("/api/alerts?status=all", headers=H).json()) == 1


def test_events_hide_simulation_when_requested(client, db):
    db.add(database.Event(event_type="AUTH_FAILURE", severity="INFO", source="t", description="x", is_simulation=True))
    db.add(database.Event(event_type="AUTH_FAILURE", severity="INFO", source="t", description="y", is_simulation=False))
    db.commit()
    assert len(client.get("/api/events", headers=H).json()) == 2
    assert len(client.get("/api/events?include_simulation=false", headers=H).json()) == 1


def test_unblock_validates_ip(client):
    assert client.post("/api/blocked/not-an-ip/unblock", headers=H).status_code == 400
    assert client.post("/api/blocked/203.0.113.9/unblock", headers=H).status_code == 409


def test_summary_and_monitors_endpoints(client):
    s = client.get("/api/summary/korean", headers=H).json()
    assert "미확인 알림이 없습니다" in s["highlight"]
    assert client.get("/api/monitors", headers=H).json() == []   # lifespan 미실행
    host = client.get("/api/host", headers=H).json()
    assert "privileges" in host and "auth_log_readable" in host["privileges"]
    # 실행 계정은 USER 환경변수가 아니라 실제 uid 에서 풀어야 한다 (systemd 아래에선 비어 있다)
    assert host["running_as"]["user"]


def test_host_reports_which_instance_this_is(client, monkeypatch):
    """개발 인스턴스와 운영 서비스는 겉보기가 같다. 화면이 구별하려면 백엔드가 말해줘야 한다."""
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    inst = client.get("/api/host", headers=H).json()["instance"]
    assert inst["mode"] == "dev" and inst["user"] and inst["port"]

    # systemd 가 띄운 프로세스에만 INVOCATION_ID 가 있다
    monkeypatch.setenv("INVOCATION_ID", "deadbeef")
    assert client.get("/api/host", headers=H).json()["instance"]["mode"] == "service"


def test_timeline_hours_and_utc_timestamps(client, db):
    from datetime import timedelta
    now = database.utcnow()
    db.add(database.Event(event_type="AUTH_FAILURE", severity="WARNING", source="t", description="x", timestamp=now - timedelta(hours=30)))
    db.add(database.Event(event_type="AUTH_FAILURE", severity="INFO", source="t", description="y", timestamp=now - timedelta(minutes=5)))
    db.commit()
    rows = client.get("/api/stats/timeline?hours=48", headers=H).json()
    assert len(rows) == 48 and rows[0]["ts"].endswith("Z")
    assert sum(r["warning"] for r in rows) == 1 and sum(r["info"] for r in rows) == 1
    assert len(client.get("/api/stats/timeline?hours=24", headers=H).json()) == 24
    assert sum(r["warning"] for r in client.get("/api/stats/timeline?hours=24", headers=H).json()) == 0   # 30시간 전 이벤트는 24h 창 밖


def test_usn_alert_resolves_itself_once_the_fix_is_installed(db, monkeypatch):
    """알림을 띄우기 전에 지금 설치된 버전과 다시 대조한다.

    공지를 받은 시점의 판정은 그 시점의 사실일 뿐이다. 그 뒤 업데이트를 적용하면
    이미 끝난 일인데도 알림이 사람이 손으로 닫을 때까지 남는다. 그렇게 쌓인 목록은
    결국 아무도 안 본다.
    """
    from monitor.intel import IntelMonitor
    from integrations import apt
    import alerts as A

    affected = [{"package": "libc6", "installed": "2.39-0ubuntu8.3", "fixed": "2.39-0ubuntu8.5"}]
    A.raise_alert("usn_affects_host", "WARNING", "USN-9999-1 affects installed packages",
                  fingerprint="usn:USN-9999-1", title_ko="테스트 공지",
                  details={"affected": affected, "feed": "usn"})
    db.expire_all()
    assert db.query(database.Alert).filter(database.Alert.status == "OPEN").count() == 1

    m = IntelMonitor(feeds=[], usn_url="")

    # 아직 옛 버전이면 그대로 둔다
    monkeypatch.setattr(apt, "installed_packages", lambda: {"libc6": "2.39-0ubuntu8.3"})
    m._recheck_open()
    db.expire_all()
    assert db.query(database.Alert).one().status == "OPEN"

    # 수정 버전이 깔렸으면 스스로 정리한다
    monkeypatch.setattr(apt, "installed_packages", lambda: {"libc6": "2.39-0ubuntu8.5"})
    m._recheck_open()
    db.expire_all()
    a = db.query(database.Alert).one()
    assert a.status == "RESOLVED" and "수정 버전" in (a.resolution_note or "")


def test_usn_recheck_does_nothing_when_package_list_is_unreadable(db, monkeypatch):
    """설치 목록을 못 읽으면 아무 판단도 하지 않는다 — 못 읽은 것을 '해결됨'으로 바꾸면 조용히 지우는 셈이다."""
    from monitor.intel import IntelMonitor
    from integrations import apt
    import alerts as A

    A.raise_alert("usn_affects_host", "WARNING", "x", fingerprint="usn:USN-9998-1",
                  details={"affected": [{"package": "libc6", "installed": "1", "fixed": "2"}]})
    monkeypatch.setattr(apt, "installed_packages", lambda: {})
    IntelMonitor(feeds=[], usn_url="")._recheck_open()
    db.expire_all()
    assert db.query(database.Alert).one().status == "OPEN"


def test_cors_allows_desktop_app_origin_only(client):
    """데스크톱 앱(Tauri)의 출처는 preflight 를 통과하고, 모르는 출처는 통과하지 못한다."""
    pre = {"Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "X-API-Token"}
    for origin in ("tauri://localhost", "http://tauri.localhost"):
        r = client.options("/api/stats", headers={**pre, "Origin": origin})
        assert r.status_code == 200
        assert r.headers.get("access-control-allow-origin") == origin
    r = client.options("/api/stats", headers={**pre, "Origin": "https://evil.example"})
    assert r.headers.get("access-control-allow-origin") is None
    # 출처를 허용해도 토큰 없이는 읽을 수 없다.
    assert client.get("/api/stats", headers={"Origin": "tauri://localhost"}).status_code == 401
