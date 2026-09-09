import os

from monitor.permissions import (
    PermissionMonitor,
    check_secret,
    check_writable,
    hijack_evidence,
    scan_home,
    scan_tree,
)


def _mk(path, content="x", mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    os.chmod(path, mode)
    return str(path)


# --- check_writable ---
def test_world_writable_dir_is_critical(tmp_path):
    d = tmp_path / "conf"
    d.mkdir()
    os.chmod(d, 0o777)
    f = check_writable(str(d))
    assert f and f["severity"] == "CRITICAL" and f["kind"] == "world_writable"
    assert f["mode"] == "777" and "chmod 700" in f["fix"]


def test_group_writable_is_warning(tmp_path):
    d = tmp_path / "conf"
    d.mkdir()
    os.chmod(d, 0o775)
    f = check_writable(str(d))
    assert f and f["severity"] == "WARNING" and "같은 그룹" in f["title_ko"]


def test_tight_permissions_produce_nothing(tmp_path):
    d = tmp_path / "conf"
    d.mkdir()
    os.chmod(d, 0o700)
    assert check_writable(str(d)) is None


def test_sticky_dir_is_not_flagged(tmp_path):
    """/tmp 처럼 sticky bit 가 있으면 남의 파일을 지울 수 없으므로 정상."""
    d = tmp_path / "shared"
    d.mkdir()
    os.chmod(d, 0o1777)
    assert check_writable(str(d)) is None


def test_shell_rc_file_fix_keeps_644(tmp_path):
    p = _mk(tmp_path / ".bashrc", mode=0o777)
    f = check_writable(p)
    assert f and "chmod 644" in f["fix"]


def test_symlink_is_not_followed(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    os.chmod(target, 0o700)
    link = tmp_path / "link"
    link.symlink_to(target)
    assert check_writable(str(link)) is None


# --- check_secret ---
def test_readable_credential_is_flagged(tmp_path):
    p = _mk(tmp_path / ".git-credentials", mode=0o644)
    f = check_secret(p)
    assert f and f["severity"] == "WARNING" and "chmod 600" in f["fix"]


def test_private_key_readable_is_critical(tmp_path):
    p = _mk(tmp_path / ".ssh" / "id_rsa", mode=0o644)
    f = check_secret(p)
    assert f and f["severity"] == "CRITICAL" and "개인키" in f["title_ko"]


def test_public_key_is_ignored(tmp_path):
    p = _mk(tmp_path / ".ssh" / "id_rsa.pub", mode=0o644)
    assert check_secret(p) is None


def test_secret_with_600_is_ok(tmp_path):
    p = _mk(tmp_path / ".netrc", mode=0o600)
    assert check_secret(p) is None


# --- hijack evidence ---
def test_autostart_entries_are_reported(tmp_path):
    cfg = tmp_path / ".config"
    (cfg / "autostart").mkdir(parents=True)
    (cfg / "autostart" / "evil.desktop").write_text("[Desktop Entry]")
    assert "evil.desktop" in hijack_evidence(str(cfg))


def test_empty_autostart_says_so(tmp_path):
    cfg = tmp_path / ".config"
    (cfg / "autostart").mkdir(parents=True)
    assert "비어" in hijack_evidence(str(cfg))


def test_gitconfig_hook_is_reported(tmp_path):
    p = _mk(tmp_path / ".gitconfig", content="[core]\n\thooksPath = /tmp/hooks\n")
    assert "hooksPath" in hijack_evidence(p)


# --- scan_home / scan_tree ---
def test_scan_home_finds_both_kinds(tmp_path):
    home = tmp_path / "home" / "someone"
    (home / ".config").mkdir(parents=True)
    os.chmod(home / ".config", 0o777)
    _mk(home / ".ssh" / "id_ed25519", mode=0o644)
    os.chmod(home, 0o750)

    paths = {f["path"]: f for f in scan_home(str(home))}
    assert str(home / ".config") in paths
    assert str(home / ".ssh" / "id_ed25519") in paths
    assert str(home) not in paths  # 홈 자체는 750 이라 정상


def test_scan_tree_respects_depth(tmp_path):
    deep = tmp_path / "a" / "b" / "c" / "d"
    deep.mkdir(parents=True)
    victim = deep / "toodeep.conf"
    victim.write_text("x")
    os.chmod(victim, 0o666)
    shallow = tmp_path / "a" / "near.conf"
    shallow.write_text("x")
    os.chmod(shallow, 0o666)

    found = {f["path"] for f in scan_tree(str(tmp_path), max_depth=2)}
    assert str(shallow) in found
    assert str(victim) not in found


# --- monitor ---
def test_scan_keeps_worst_finding_per_path(tmp_path):
    home = tmp_path / "home" / "someone"
    (home / ".ssh").mkdir(parents=True)
    key = _mk(home / ".ssh" / "id_rsa", mode=0o646)  # 쓰기 가능 + 읽기 노출 둘 다 해당
    os.chmod(home, 0o750)

    mon = PermissionMonitor(homes=[str(home)], trees=[])
    rows = {f["path"]: f for f in mon.scan()}
    assert rows[key]["severity"] == "CRITICAL"
    assert sum(1 for p in rows if p == key) == 1


def test_status_payload_counts(tmp_path):
    home = tmp_path / "home" / "someone"
    (home / ".config").mkdir(parents=True)
    os.chmod(home / ".config", 0o777)
    os.chmod(home, 0o750)

    mon = PermissionMonitor(homes=[str(home)], trees=[])
    mon.findings = mon.scan()
    payload = mon.status_payload()
    assert payload["counts"]["critical"] >= 1
    assert payload["scanned_homes"] == [str(home)]


def test_resolved_when_permission_tightened(tmp_path):
    """권한을 고치면 알림이 자동 해결되고 다시 열리면 또 올라온다."""
    home = tmp_path / "home" / "someone"
    cfg = home / ".config"
    cfg.mkdir(parents=True)
    os.chmod(home, 0o750)
    os.chmod(cfg, 0o777)

    mon = PermissionMonitor(homes=[str(home)], trees=[])
    mon.tick()
    assert f"perm:{cfg}" in mon._open

    os.chmod(cfg, 0o700)
    mon.tick()
    assert mon._open == set()
