"""쉬운 화면에서 사용자가 답한 것이 어떻게 기록되는가."""
import pytest
from fastapi.testclient import TestClient

import database
from alerts import raise_alert

H = {"X-API-Token": "test-token"}


@pytest.fixture
def client():
    # lifespan 을 띄우지 않는다 (프로젝트 관례). 모니터를 기동하면 테스트마다 상태가 섞인다.
    import app as app_module
    return TestClient(app_module.app)


def _mk(sev="WARNING", rule="new_login_ip"):
    a, _ = raise_alert(rule, sev, "t", fingerprint=f"{rule}:x", title_ko="처음 보는 곳에서 로그인")
    return a.id


def _get(alert_id):
    db = database.SessionLocal()
    try:
        return db.query(database.Alert).filter(database.Alert.id == alert_id).first()
    finally:
        db.close()


def _events():
    db = database.SessionLocal()
    try:
        return db.query(database.Event).filter(database.Event.event_type == "USER_RESPONSE").all()
    finally:
        db.close()


def test_mine_acks_and_leaves_the_list(client):
    i = _mk()
    r = client.post("/api/alerts/respond", headers=H, json={"ids": [i], "answer": "mine"})
    assert r.status_code == 200 and r.json()["updated"] == 1
    a = _get(i)
    assert a.status == "ACKED" and a.acked_by == "사용자"
    assert a.details_dict()["user_response"] == "mine"


def test_not_me_stays_open_and_escalates(client):
    """본인이 아니라고 했으면 가장 강한 신호다. 목록에서 빼면 안 된다."""
    i = _mk(sev="WARNING")
    r = client.post("/api/alerts/respond", headers=H, json={"ids": [i], "answer": "not_me"})
    assert r.json()["escalated"] is True
    a = _get(i)
    assert a.status == "OPEN" and a.severity == "CRITICAL"


def test_unsure_stays_open_without_escalating(client):
    """억지로 판단하게 하지 않는다. 다만 열어둔 상태는 유지한다 — 숨기면 잊힌다."""
    i = _mk(sev="WARNING")
    client.post("/api/alerts/respond", headers=H, json={"ids": [i], "answer": "unsure"})
    a = _get(i)
    assert a.status == "OPEN" and a.severity == "WARNING"
    assert a.details_dict()["user_response"] == "unsure"


def test_every_answer_is_recorded_as_an_event(client):
    """'보고도 판단을 미룬 것'과 '아예 열어보지 않은 것'을 구분할 수 있어야 한다."""
    i = _mk()
    client.post("/api/alerts/respond", headers=H, json={"ids": [i], "answer": "unsure"})
    ev = _events()
    assert len(ev) == 1
    assert "잘 모르겠다" in ev[0].description_ko


def test_grouped_answer_writes_one_event_not_twenty(client):
    ids = [_mk(rule=f"persistence_cron{n}") for n in range(5)]
    client.post("/api/alerts/respond", headers=H, json={"ids": ids, "answer": "mine"})
    assert len(_events()) == 1
    assert all(_get(i).status == "ACKED" for i in ids)


def test_bad_answer_is_rejected(client):
    i = _mk()
    assert client.post("/api/alerts/respond", headers=H, json={"ids": [i], "answer": "무엇"}).status_code == 400


def test_unknown_ids_are_rejected(client):
    assert client.post("/api/alerts/respond", headers=H, json={"ids": [999999], "answer": "mine"}).status_code == 404


def test_requires_token(client):
    i = _mk()
    assert client.post("/api/alerts/respond", json={"ids": [i], "answer": "mine"}).status_code == 401
