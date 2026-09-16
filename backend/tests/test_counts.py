"""
잘린 목록이 '전부'처럼 보이지 않게 하는 건수 엔드포인트.

운영 화면에서 관측된 것: 알림 머리글은 "미확인 1 / 진행 중 99", 시스템 상태 패널은
"185 대응 중". 머리글이 불러온 행을 셌고, 목록은 limit=100 에서 잘려 있었다.
사용자는 어느 숫자가 참인지 알 방법이 없고 85건은 조용히 사라진다.
"""
import pytest
from fastapi.testclient import TestClient

import alerts
import database

H = {"X-API-Token": "test-token"}


@pytest.fixture
def client():
    import app as app_module
    return TestClient(app_module.app)


def _make_acked(db, n):
    for i in range(n):
        a, _ = alerts.raise_alert("r", "WARNING", f"t{i}", fingerprint=f"fp:{i}")
        alerts.ack_alert(a.id, "tester", db)


def test_count_is_authoritative_when_list_is_truncated(client, db):
    # 미확인 1건을 먼저 만들어 목록 첫 페이지(최신 100건) 밖으로 밀려나게 한다 —
    # 운영에서 벌어진 상황이 정확히 이것이다.
    alerts.raise_alert("r", "CRITICAL", "old open", fingerprint="fp:open", title_ko="오래된 미확인")
    _make_acked(db, 120)

    rows = client.get("/api/alerts?status=active", headers=H).json()
    assert len(rows) == 100                                  # 목록은 잘린다
    assert all(r["status"] == "ACKED" for r in rows)          # 미확인은 화면 밖에 있다

    c = client.get("/api/alerts/count?status=active", headers=H).json()
    assert c["total"] == 121 and c["open"] == 1 and c["acked"] == 120
    assert c["open_critical"] == 1 and c["open_warning"] == 0 and c["resolved"] == 0
    assert c["simulation"] == 0 and c["max_limit"] == 500

    # 두 패널이 같은 사실을 말해야 한다
    stats = client.get("/api/stats", headers=H).json()
    assert stats["acked"] == c["acked"] and stats["open_critical"] == c["open_critical"]

    # limit 을 올리면 나머지도 실제로 받을 수 있다 ('더 보기')
    assert len(client.get("/api/alerts?status=active&limit=200", headers=H).json()) == 121


def test_count_follows_same_status_filter_as_list(client, db):
    a, _ = alerts.raise_alert("r", "WARNING", "w", fingerprint="fp:w")
    alerts.resolve_alert(a.id, "me", "done", db)
    alerts.raise_alert("r", "CRITICAL", "c", fingerprint="fp:c")

    active = client.get("/api/alerts/count?status=active", headers=H).json()
    assert active["total"] == 1 and active["open"] == 1 and active["resolved"] == 0
    every = client.get("/api/alerts/count?status=all", headers=H).json()
    assert every["total"] == 2 and every["resolved"] == 1

    # 목록 길이와 건수가 어긋나면 화면의 숫자가 다시 둘로 갈린다
    for status in ("active", "all", "resolved"):
        rows = client.get(f"/api/alerts?status={status}&limit=500", headers=H).json()
        total = client.get(f"/api/alerts/count?status={status}", headers=H).json()["total"]
        assert len(rows) == total


def test_count_reports_simulation_rows_separately(client, db):
    alerts.raise_alert("r", "WARNING", "real", fingerprint="fp:r")
    alerts.raise_alert("r", "WARNING", "sim", fingerprint="fp:s", is_simulation=True)

    c = client.get("/api/alerts/count?status=active", headers=H).json()
    assert c["total"] == 2 and c["open"] == 2 and c["simulation"] == 1
    # /api/stats 는 시뮬레이션을 빼고 센다. 그 차이를 화면이 설명할 수 있어야 한다.
    assert client.get("/api/stats", headers=H).json()["open_warning"] == 1


def test_event_count_mirrors_list_filters(client, db):
    for i in range(5):
        db.add(database.Event(
            event_type="AUTH_FAILURE", severity="WARNING" if i == 0 else "INFO",
            source="192.0.2.10", description=f"x{i}", is_simulation=(i % 2 == 0),
        ))
    db.add(database.Event(event_type="THREAT_INTEL", severity="INFO", source="feed", description="intel"))
    db.commit()

    assert client.get("/api/events/count", headers=H).json()["total"] == 5          # THREAT_INTEL 제외
    assert client.get("/api/events/count?include_simulation=false", headers=H).json()["total"] == 2
    assert client.get("/api/events/count?severity=info", headers=H).json()["total"] == 4
    # 목록이 잘려도 건수는 전체를 말한다
    assert len(client.get("/api/events?limit=2", headers=H).json()) == 2
    assert client.get("/api/events/count", headers=H).json()["max_limit"] == 500


def test_count_endpoints_require_token(client):
    assert client.get("/api/alerts/count").status_code == 401
    assert client.get("/api/events/count").status_code == 401
