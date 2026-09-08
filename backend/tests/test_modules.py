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
