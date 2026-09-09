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
