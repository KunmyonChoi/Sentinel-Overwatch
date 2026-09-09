import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import config
from integrations import permission_fix
from integrations.permissions_scan import narrow, scan

BACKEND = Path(__file__).resolve().parents[1]
FIXER = BACKEND / "fix_permissions.py"
SCRIPT = BACKEND.parent / "deploy" / "fix-permissions.sh"


# --- 불변식: 절대 넓히지 않는다 ---
@pytest.mark.parametrize("old,target", [
    (0o777, 0o700), (0o777, 0o644), (0o664, 0o600), (0o400, 0o644),
    (0o755, 0o750), (0o600, 0o644), (0o1777, 0o700), (0o000, 0o777),
])
def test_narrow_never_widens(old, target):
    new = narrow(old, target)
    assert new & ~old == 0, "기존에 없던 권한 비트가 생기면 안 된다"
    assert new <= old


def test_narrow_reaches_target_when_possible():
    assert narrow(0o777, 0o700) == 0o700
    assert narrow(0o666, 0o600) == 0o600


# --- 조치기 본체 (root 가 아니어도 dry-run 계산 경로는 검증할 수 있다) ---
def test_fixer_refuses_without_root():
    """root 가 아니면 아무것도 하지 않고 정직하게 거부한다."""
    proc = subprocess.run([sys.executable, str(FIXER), "--apply"], capture_output=True, text=True, timeout=60)
    data = json.loads(proc.stdout)
    assert data["ok"] is False and "root" in data["error"]
    assert data["results"] == []


def test_wrapper_rejects_unknown_arguments():
    """경로를 인자로 넘기려는 시도는 거부되어야 한다 (허용 인자는 --apply 뿐)."""
    proc = subprocess.run(["bash", str(SCRIPT), "--apply", "/etc/shadow"], capture_output=True, text=True, timeout=60)
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0
    # root 검사가 먼저 걸리든 인자 검사가 걸리든, 어느 쪽이든 실행되지 않아야 한다
    assert '"ok": false' in out.lower() or "root" in out


def test_wrapper_is_executable():
    assert os.access(SCRIPT, os.X_OK), "sudoers 로 호출하려면 실행 권한이 있어야 한다"


# --- 호출기 (실제 스크립트를 부르지 않고 경로만 바꿔 검증) ---
def test_availability_reports_missing_script(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PERMISSION_FIX_SCRIPT", str(tmp_path / "nope.sh"))
    ok, reason, hint = permission_fix.availability()
    assert ok is False and "없음" in reason and "update.sh" in hint


def test_availability_reports_non_executable(monkeypatch, tmp_path):
    p = tmp_path / "fix.sh"
    p.write_text("#!/bin/bash\n")
    os.chmod(p, 0o644)
    monkeypatch.setattr(config, "PERMISSION_FIX_SCRIPT", str(p))
    ok, reason, hint = permission_fix.availability()
    assert ok is False and "실행 권한" in reason and "chmod +x" in hint


def test_run_returns_error_not_success_when_unavailable(monkeypatch, tmp_path):
    """조치하지 못했는데 성공처럼 보이면 안 된다."""
    monkeypatch.setattr(config, "PERMISSION_FIX_SCRIPT", str(tmp_path / "nope.sh"))
    r = permission_fix.run(apply=True)
    assert r["ok"] is False and r["changed"] == 0 and r["results"] == []


def test_run_parses_script_output(monkeypatch, tmp_path):
    fake = tmp_path / "fix.sh"
    fake.write_text('#!/bin/bash\necho \'{"ok": true, "applied": true, "changed": 1, '
                    '"results": [{"path": "/x", "before": "777", "after": "700", "applied": true}]}\'\n')
    os.chmod(fake, 0o755)
    monkeypatch.setattr(config, "PERMISSION_FIX_SCRIPT", str(fake))
    monkeypatch.setattr(config, "PERMISSION_FIX_USE_SUDO", False)
    r = permission_fix.run(apply=True)
    assert r["ok"] is True and r["changed"] == 1
    assert r["results"][0]["after"] == "700"


def test_run_reports_sudo_denial_with_hint(monkeypatch, tmp_path):
    fake = tmp_path / "fix.sh"
    fake.write_text('#!/bin/bash\necho "sudo: a password is required" >&2\nexit 1\n')
    os.chmod(fake, 0o755)
    monkeypatch.setattr(config, "PERMISSION_FIX_SCRIPT", str(fake))
    monkeypatch.setattr(config, "PERMISSION_FIX_USE_SUDO", False)
    r = permission_fix.run(apply=True)
    assert r["ok"] is False and "sudo" in r["error"]
    assert "sudoers" in r["fix_hint"]


def test_run_rejects_garbage_output(monkeypatch, tmp_path):
    fake = tmp_path / "fix.sh"
    fake.write_text('#!/bin/bash\necho "not json"\n')
    os.chmod(fake, 0o755)
    monkeypatch.setattr(config, "PERMISSION_FIX_SCRIPT", str(fake))
    monkeypatch.setattr(config, "PERMISSION_FIX_USE_SUDO", False)
    r = permission_fix.run()
    assert r["ok"] is False and "해석" in r["error"]


# --- 스캔 → 조치 목표가 실제로 문제를 없애는지 ---
def test_scan_targets_resolve_the_finding(tmp_path):
    home = tmp_path / "home" / "someone"
    (home / ".config").mkdir(parents=True)
    os.chmod(home, 0o750)
    os.chmod(home / ".config", 0o777)
    rc = tmp_path / "home" / "someone" / ".bashrc"
    rc.write_text("x")
    os.chmod(rc, 0o777)

    findings = scan([str(home)], [])
    assert findings, "문제를 찾지 못하면 조치할 것도 없다"
    for f in findings:
        new = narrow(int(f["mode"], 8), f["target"])
        os.chmod(f["path"], new)
    assert scan([str(home)], []) == [], "목표 권한을 적용하면 같은 문제가 다시 나오면 안 된다"


# --- apply_one: 실제로 권한을 바꾸는 지점 (자기 파일이라 root 없이 검증 가능) ---
def _apply_one():
    sys.path.insert(0, str(BACKEND))
    from fix_permissions import apply_one
    return apply_one


def test_apply_one_narrows(tmp_path):
    p = tmp_path / "conf"
    p.write_text("x")
    os.chmod(p, 0o777)
    r = _apply_one()(str(p), 0o644)
    assert r["applied"] is True and r["before"] == "777" and r["after"] == "644"
    assert oct(os.stat(p).st_mode)[-3:] == "644"


def test_apply_one_refuses_to_widen(tmp_path):
    p = tmp_path / "tight"
    p.write_text("x")
    os.chmod(p, 0o400)
    r = _apply_one()(str(p), 0o644)
    assert r["applied"] is False and "넓히지" in r["error"]
    assert oct(os.stat(p).st_mode)[-3:] == "400", "권한이 그대로여야 한다"


def test_apply_one_refuses_symlink(tmp_path):
    """스캔과 적용 사이에 대상이 링크로 바뀌어도 엉뚱한 파일을 건드리면 안 된다."""
    target = tmp_path / "secret"
    target.write_text("x")
    os.chmod(target, 0o600)
    link = tmp_path / "link"
    link.symlink_to(target)

    r = _apply_one()(str(link), 0o700)
    assert r["applied"] is False
    assert oct(os.stat(target).st_mode)[-3:] == "600", "링크가 가리키는 파일의 권한이 바뀌면 안 된다"


def test_apply_one_handles_missing_path(tmp_path):
    r = _apply_one()(str(tmp_path / "gone"), 0o600)
    assert r["applied"] is False and r["error"]
