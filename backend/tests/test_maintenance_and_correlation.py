import os

import alerts
import database
from database import Alert, Event
from fastapi.testclient import TestClient
from integrations import apt
from monitor.integrity import IntegrityMonitor, PersistenceMonitor, summarize_generic

H = {"X-API-Token": "test-token"}


def test_maintenance_auto_acks_planned_rules_but_not_intrusions(db):
    alerts.start_maintenance(30, "harden.sh 적용", "kunmyon", db)
    a, _ = alerts.raise_alert("integrity_change", "CRITICAL", "sshd banner", fingerprint="mw:1")
    b, _ = alerts.raise_alert("persistence_cron", "WARNING", "cron", fingerprint="mw:2")
    c, _ = alerts.raise_alert("brute_force", "WARNING", "bf", fingerprint="mw:3")
    d, _ = alerts.raise_alert("login_after_failures", "CRITICAL", "laf", fingerprint="mw:4")
    assert a.status == "ACKED" and a.acked_by == "점검 모드" and "harden.sh" in a.resolution_note
    assert b.status == "ACKED" and b.details_dict()["maintenance"] == "harden.sh 적용"
    assert c.status == "OPEN" and d.status == "OPEN"
    assert alerts.compute_defcon(db)["status"] == "DEFCON 1"   # 침입 신호는 그대로
    assert alerts.end_maintenance("kunmyon", db) == 1
    e, _ = alerts.raise_alert("integrity_change", "CRITICAL", "after", fingerprint="mw:5")
    assert e.status == "OPEN"


def test_ack_all_by_ids_and_rule(db):
    ids = [alerts.raise_alert("persistence_cron", "WARNING", f"c{i}", fingerprint=f"aa:{i}")[0].id for i in range(3)]
    alerts.raise_alert("brute_force", "WARNING", "bf", fingerprint="aa:bf")
    assert alerts.ack_all(db, "me", "planned", ids=ids[:2]) == 2
    assert alerts.ack_all(db, "me", "", rule="persistence_cron") == 1
    assert db.query(Alert).filter(Alert.status == "OPEN").count() == 1   # brute_force 만 남음


def _pkg_event(db, package):
    db.add(Event(event_type="SOFTWARE_UPDATE", severity="INFO", source="UpdateMonitor", description=f"Package installed: {package}",
                 description_ko=f"패키지 설치됨: {package}", details=f'{{"action": "install", "package": "{package}"}}'))
    db.commit()


def test_package_owned_persistence_and_suid_become_info(db, tmp_path, monkeypatch):
    cron = tmp_path / "cron.d"; cron.mkdir()
    sysd = tmp_path / "systemd"; sysd.mkdir()
    bins = tmp_path / "bin"; bins.mkdir()
    m = PersistenceMonitor(cron_dirs=[str(cron)], systemd_dirs=[str(sysd)], suid_dirs=[str(bins)])
    m.setup()
    _pkg_event(db, "debsums")
    _pkg_event(db, "libpam-tmpdir")
    owners = {str(cron / "debsums"): "debsums", str(bins / "pam-tmpdir-helper"): "libpam-tmpdir"}
    monkeypatch.setattr(apt, "package_owner", lambda p: owners.get(os.path.realpath(p)) or owners.get(p))
    (cron / "debsums").write_text("0 4 * * * root debsums\n")
    (cron / "evil").write_text("* * * * * root /tmp/x\n")
    helper = bins / "pam-tmpdir-helper"; helper.write_text("#!/bin/sh\n"); os.chmod(helper, 0o4755)
    (sysd / "cups.service").symlink_to("/dev/null")
    (sysd / "snap-opera-492.mount").write_text("[Mount]\n")
    m.tick()
    rules = sorted(a.rule + ":" + os.path.basename(a.details_dict()["path"]) for a in db.query(Alert).all())
    assert rules == ["persistence_cron:evil"]                      # 패키지 소유·마스크·snap·패키지 SUID 는 알림 없음
    infos = {(e.details_dict().get("path", "").split("/")[-1], e.severity) for e in db.query(Event).filter(Event.event_type == "PERSISTENCE").all()}
    assert ("debsums", "INFO") in infos and ("pam-tmpdir-helper", "INFO") in infos and ("cups.service", "INFO") in infos and ("snap-opera-492.mount", "INFO") in infos


def test_always_alert_paths_ignore_package_correlation(db, tmp_path, monkeypatch):
    sudoers = tmp_path / "sudoers.d"; sudoers.mkdir()
    f = sudoers / "pkg"; f.write_text("a\n")
    m = IntegrityMonitor(watch={str(f): ("CRITICAL", False, summarize_generic, "sudo 정책")})
    m.setup()
    _pkg_event(db, "somepkg")
    monkeypatch.setattr(apt, "package_owner", lambda p: "somepkg")
    f.write_text("b ALL=(ALL) NOPASSWD:ALL\n")
    m.tick()
    assert db.query(Alert).filter(Alert.rule == "integrity_change").count() == 1


def test_maintenance_api(db):
    import app as app_module
    c = TestClient(app_module.app)
    assert c.get("/api/maintenance", headers=H).json()["active"] is False
    r = c.post("/api/maintenance", headers=H, json={"minutes": 15, "note": "test", "by": "me"}).json()
    assert r["active"] and r["remaining_seconds"] > 800
    assert c.get("/api/stats", headers=H).json()["maintenance"]["active"] is True
    assert c.delete("/api/maintenance", headers=H).json()["ended"] == 1
    a, _ = alerts.raise_alert("persistence_cron", "WARNING", "x", fingerprint="api:ack")
    assert c.post("/api/alerts/ack-all", headers=H, json={"ids": [a.id], "note": "n"}).json()["acked"] == 1
