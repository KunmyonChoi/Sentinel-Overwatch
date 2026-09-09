"""
권한 일괄 조치 호출기.

대시보드는 '무엇을 고칠지' 를 지정하지 않는다. deploy/fix-permissions.sh 를 부르면 그 스크립트가
root 권한으로 직접 다시 스캔해 대상을 정한다. 그래서 API 토큰이 유출되어도 임의 경로의 권한을
바꿀 수 없다. 여기서는 스크립트를 호출하고 JSON 을 돌려받는 일만 한다.

조용히 실패하지 않는다. sudo 가 막혀 있으면 '고쳤다' 가 아니라 사유와 해결 방법을 돌려준다.
"""
import json
import logging
import os
import shutil
import subprocess

import config

logger = logging.getLogger("permission_fix")

_TIMEOUT = 120


def _cmd(apply: bool) -> list[str]:
    base = [config.PERMISSION_FIX_SCRIPT]
    if apply:
        base.append("--apply")
    if config.PERMISSION_FIX_USE_SUDO:
        return ["sudo", "-n", *base]
    return base


def availability() -> tuple[bool, str, str]:
    """(사용 가능 여부, 사유, 해결 힌트)"""
    script = config.PERMISSION_FIX_SCRIPT
    if not os.path.exists(script):
        return False, f"조치 스크립트가 없음: {script}", "deploy/update.sh 로 배포하면 함께 설치됩니다."
    if not os.access(script, os.X_OK):
        return False, f"조치 스크립트에 실행 권한이 없음: {script}", f"chmod +x {script}"
    if config.PERMISSION_FIX_USE_SUDO and not shutil.which("sudo"):
        return False, "sudo 가 없음", "root 로 실행하거나 sudo 를 설치하세요."
    return True, "", ""


def run(apply: bool = False) -> dict:
    """dry-run 또는 실제 적용. 항상 {ok, ...} 형태의 dict 를 돌려준다."""
    ok, reason, hint = availability()
    if not ok:
        return {"ok": False, "error": reason, "fix_hint": hint, "results": [], "applied": apply, "changed": 0}
    try:
        proc = subprocess.run(
            _cmd(apply), capture_output=True, text=True, timeout=_TIMEOUT,
            env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"},
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "조치 스크립트 응답 시간 초과", "fix_hint": "직접 실행해 확인하세요.", "results": [], "applied": apply, "changed": 0}
    except OSError as e:
        return {"ok": False, "error": f"조치 스크립트 실행 실패: {e}", "fix_hint": "", "results": [], "applied": apply, "changed": 0}

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if not out:
        low = err.lower()
        if "password is required" in low or "sudo:" in low:
            return {"ok": False, "error": f"sudo 로 조치 스크립트를 호출할 수 없음: {err[:150]}",
                    "fix_hint": "deploy/sudoers-secdash 에 fix-permissions.sh 항목이 설치되었는지 확인하세요 (sudo deploy/update.sh).",
                    "results": [], "applied": apply, "changed": 0}
        return {"ok": False, "error": f"조치 스크립트가 출력을 내지 않음 (rc={proc.returncode}): {err[:150]}",
                "fix_hint": "", "results": [], "applied": apply, "changed": 0}
    try:
        data = json.loads(out)
    except ValueError:
        return {"ok": False, "error": f"조치 스크립트 출력을 해석할 수 없음: {out[:150]}", "fix_hint": "",
                "results": [], "applied": apply, "changed": 0}
    if not isinstance(data, dict):
        return {"ok": False, "error": "조치 스크립트 출력 형식이 올바르지 않음", "fix_hint": "", "results": [], "applied": apply, "changed": 0}
    data.setdefault("results", [])
    data.setdefault("changed", 0)
    data.setdefault("applied", apply)
    if not data.get("ok") and not data.get("fix_hint"):
        # 스크립트가 스스로 거부한 경우(root 아님 등)에도 다음에 할 일을 알려준다
        data["fix_hint"] = (
            "sudo 로 호출되도록 SECDASH_PERMISSION_FIX_USE_SUDO 를 켜고, "
            "deploy/sudoers-secdash 의 fix-permissions.sh 항목이 설치되었는지 확인하세요 (sudo deploy/update.sh)."
        )
    return data
