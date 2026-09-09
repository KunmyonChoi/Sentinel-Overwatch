import database
from integrations.containers import actionable, audit_container
from monitor.container_audit import ContainerAudit


class FakeClient:
    """DockerClient 대역. snapshot() 만 흉내낸다."""

    def __init__(self, snapshot):
        self._snapshot = snapshot

    def snapshot(self):
        return self._snapshot


def _snapshot(*objs):
    from integrations.containers import audit_all
    rows = audit_all(list(objs))
    return {
        "available": True, "reason": "", "fix_hint": "", "containers": rows,
        "counts": {"total": len(rows), "privileged": sum(1 for r in rows if r["privileged"]),
                   "with_findings": sum(1 for r in rows if r["findings"]),
                   "actionable": sum(1 for r in rows if actionable(r))},
    }


PRIVILEGED = {
    "Id": "a" * 64, "Name": "/builder",
    "Config": {"Image": "moby/buildkit:latest", "User": ""},
    "HostConfig": {"Privileged": True, "RestartPolicy": {"Name": "unless-stopped"}, "NetworkMode": "bridge"},
}
CLEAN = {
    "Id": "b" * 64, "Name": "/registry",
    "Config": {"Image": "registry:2", "User": "10001"},
    "HostConfig": {"Privileged": False, "RestartPolicy": {"Name": "unless-stopped"}, "NetworkMode": "bridge",
                   "PortBindings": {"5000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "5000"}]}},
}


def _alerts():
    db = database.SessionLocal()
    try:
        return db.query(database.Alert).all()
    finally:
        db.close()


def test_actionable_excludes_info():
    row = audit_container(CLEAN)
    assert [f["code"] for f in row["findings"]] == []  # 비특권 + 루프백 + 비root → 깨끗
    root_row = audit_container(PRIVILEGED)
    codes = {f["code"] for f in root_row["findings"]}
    assert "run_as_root" in codes  # INFO 는 findings 에는 있고
    assert "run_as_root" not in {f["code"] for f in actionable(root_row)}  # 조치 목록에는 없다


def test_privileged_container_raises_critical_alert():
    mon = ContainerAudit(client=FakeClient(_snapshot(PRIVILEGED)))
    mon.tick()
    alerts = _alerts()
    assert len(alerts) == 1
    a = alerts[0]
    assert a.severity == "CRITICAL" and a.rule == "container_config"
    assert "builder" in a.title_ko
    assert "buildx stop" in a.action_ko          # 조치가 실행 가능한 명령인지
    assert a.fingerprint == "container:privileged:builder"


def test_clean_container_raises_nothing():
    mon = ContainerAudit(client=FakeClient(_snapshot(CLEAN)))
    mon.tick()
    assert _alerts() == []
    assert mon.health == "ok"


def test_repeated_tick_does_not_duplicate():
    mon = ContainerAudit(client=FakeClient(_snapshot(PRIVILEGED)))
    mon.tick()
    mon.tick()
    assert len(_alerts()) == 1


def test_alert_resolves_when_container_is_fixed():
    mon = ContainerAudit(client=FakeClient(_snapshot(PRIVILEGED)))
    mon.tick()
    assert _alerts()[0].status == "OPEN"

    mon.client = FakeClient(_snapshot(CLEAN))
    mon.tick()
    assert _alerts()[0].status == "RESOLVED"
    assert mon._open == set()


def test_docker_unavailable_is_degraded_not_down():
    """컨테이너를 쓰지 않는 호스트는 정상이다. 알림을 만들지 않는다."""
    mon = ContainerAudit(client=FakeClient({
        "available": False, "reason": "docker 미설치", "fix_hint": "무시해도 됩니다",
        "containers": [], "counts": {},
    }))
    mon.tick()
    assert mon.health == "degraded" and "docker" in mon.health_reason
    assert _alerts() == []


def test_status_payload_exposes_counts():
    mon = ContainerAudit(client=FakeClient(_snapshot(PRIVILEGED, CLEAN)))
    mon.tick()
    payload = mon.status_payload()
    assert payload["counts"]["privileged"] == 1
    assert payload["counts"]["actionable"] == 1
    assert payload["containers"][0]["name"] == "builder"  # 문제 있는 것이 앞에
