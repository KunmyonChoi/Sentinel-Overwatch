from integrations.modules import blocked_modules, usb_storage_status


def test_usb_storage_status_states(tmp_path):
    mp = tmp_path / "modprobe.d"; mp.mkdir()
    sysmod = tmp_path / "sys_module"; sysmod.mkdir()
    s = usb_storage_status(str(mp), str(sysmod))
    assert s["state"] == "allowed" and not s["blocked_by_config"]
    (mp / "90-secdash-hardening.conf").write_text("install dccp /bin/false\nblacklist dccp\ninstall usb-storage /bin/false\nblacklist usb-storage\n")
    s = usb_storage_status(str(mp), str(sysmod))
    assert s["state"] == "blocked" and s["config_file"].endswith("90-secdash-hardening.conf")
    (sysmod / "usb_storage").mkdir()
    s = usb_storage_status(str(mp), str(sysmod))
    assert s["state"] == "temporarily_unblocked" and "modprobe --ignore-install" in s["commands"]["temp_unblock"]
    assert blocked_modules(str(mp)) == ["dccp", "usb-storage"]


# --- usr-merge 경로에서 패키지 소유 판정 ---
from integrations.apt import merged_usr_candidates  # noqa: E402


def test_merged_usr_tries_both_directions():
    """
    usr-merge 시스템에서 dpkg 는 /sbin/x 로 기억하는데 파일은 /usr/sbin/x 에 있다.
    한쪽만 물으면 배포판 정상 파일이 '소유 패키지 없음'이 되어 긴급 오탐이 난다.
    """
    c = merged_usr_candidates("/usr/sbin/pam-tmpdir-helper")
    assert "/usr/sbin/pam-tmpdir-helper" in c
    assert "/sbin/pam-tmpdir-helper" in c


def test_merged_usr_covers_bin_and_lib():
    assert "/bin/ls" in merged_usr_candidates("/usr/bin/ls")
    assert "/lib/x.so" in merged_usr_candidates("/usr/lib/x.so")


def test_non_merged_path_is_unchanged():
    assert merged_usr_candidates("/opt/app/tool") == ["/opt/app/tool"]


def test_candidates_have_no_duplicates():
    c = merged_usr_candidates("/usr/bin/ls")
    assert len(c) == len(set(c))


def test_reboot_required_is_watched_and_clears_itself(db, tmp_path, monkeypatch):
    """이번 상황의 진짜 위험은 '업데이트 안 함'이 아니라 '업데이트했는데 재부팅 안 함'이었다.

    apt 는 그때 "밀린 것 없음"이라고 답한다. 이 파일을 보지 않으면 남은 할 일을
    아무도 알려주지 않는다.
    """
    from monitor import update as U
    from database import Alert

    flag = tmp_path / "reboot-required"
    monkeypatch.setattr(U, "REBOOT_FLAGS", (str(flag),))
    m = U.UpdateMonitor(log_path=str(tmp_path / "dpkg.log"))

    m._check_reboot()                      # 파일이 없으면 아무 일도 없다
    assert db.query(Alert).count() == 0
    assert m.reboot == {"required": False, "packages": []}

    flag.write_text("*** System restart required ***\n")
    (tmp_path / "reboot-required.pkgs").write_text("libc6\nlinux-image-6.8.0-51-generic\n")
    m._check_reboot()
    db.expire_all()
    a = db.query(Alert).filter(Alert.rule == "reboot_required").one()
    assert a.status == "OPEN" and "재부팅" in a.title_ko
    assert "libc6" in a.summary_ko                    # 무엇 때문인지 말한다
    assert "그대로 쓰고 있어서" in a.summary_ko        # 왜 급한지도 말한다
    assert m.reboot["required"] and "libc6" in m.reboot["packages"]

    # 같은 상태로 다시 불러도 발생 횟수를 부풀리지 않는다
    m._check_reboot()
    db.expire_all()
    assert db.query(Alert).filter(Alert.rule == "reboot_required").one().count == 1

    flag.unlink()                          # 재부팅함
    m._check_reboot()
    db.expire_all()
    assert db.query(Alert).filter(Alert.rule == "reboot_required").one().status == "RESOLVED"


def test_reboot_alert_is_not_silenced_by_maintenance_mode():
    """재부팅은 점검 창이 끝나도 남는 '할 일'이다. 자동 확인으로 묻히면 안 된다."""
    from alerts import MAINTENANCE_RULE_PREFIXES
    assert not "reboot_required".startswith(MAINTENANCE_RULE_PREFIXES)
