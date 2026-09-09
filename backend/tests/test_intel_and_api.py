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
