import alerts
from database import Alert


def test_dedup_and_escalation(db):
    a1, created1 = alerts.raise_alert("r", "WARNING", "t", fingerprint="fp:1")
    a2, created2 = alerts.raise_alert("r", "WARNING", "t", fingerprint="fp:1")
    assert created1 and not created2 and a2.id == a1.id and a2.count == 2
    alerts.ack_alert(a1.id, "me", db)
    db.expire_all()
    assert db.get(Alert, a1.id).status == "ACKED"
    a3, _ = alerts.raise_alert("r", "CRITICAL", "t", fingerprint="fp:1")
    assert a3.severity == "CRITICAL" and a3.status == "OPEN"   # 심각도 상승 시 다시 미확인


def test_defcon_only_from_open_alerts(db):
    assert alerts.compute_defcon(db)["status"] == "SAFE"
    w, _ = alerts.raise_alert("r", "WARNING", "warn", fingerprint="w")
    assert alerts.compute_defcon(db)["status"] == "DEFCON 3"
    c, _ = alerts.raise_alert("r", "CRITICAL", "crit", fingerprint="c", action_ko="do X")
    d = alerts.compute_defcon(db)
    assert d["status"] == "DEFCON 1" and d["action"] == "do X" and d["top_alert_id"] == c.id
    alerts.ack_alert(c.id, "me", db)
    assert alerts.compute_defcon(db)["status"] == "DEFCON 3"
    alerts.resolve_alert(w.id, "me", "done", db)
    d = alerts.compute_defcon(db)
    assert d["status"] == "SAFE" and d["acked"] == 1


def test_auto_resolve(db):
    alerts.raise_alert("r", "WARNING", "pending", fingerprint="pending_x")
    assert alerts.auto_resolve("pending_x") == 1
    assert db.query(Alert).filter(Alert.status == "RESOLVED").count() == 1
    alerts.raise_alert("r", "WARNING", "pending", fingerprint="pending_x")
    assert db.query(Alert).count() == 2   # 해결된 뒤 재발하면 새 알림


def test_defcon_watcher_notifies_on_transition(monkeypatch):
    sent = []
    monkeypatch.setattr(alerts.notifications, "enqueue", lambda **kw: sent.append(kw["title"]))
    w = alerts.DefconWatcher()
    w.prev, w.current = "SAFE", {"status": "DEFCON 1", "reason": "x", "action": "y"}
    w._on_transition("SAFE", "DEFCON 1")
    w._on_transition("DEFCON 1", "SAFE")
    assert any("DEFCON 1" in t for t in sent) and any("완화" in t for t in sent)
