"""
APT / dpkg 연동: 설치 패키지 목록, 미적용(보안) 업데이트, 버전 비교.
모두 로컬 명령이며 외부로 아무것도 보내지 않는다.
"""
import logging
import re
import shutil
import subprocess
from functools import lru_cache

logger = logging.getLogger("apt")


def os_codename() -> str:
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VERSION_CODENAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return ""


def installed_packages() -> dict[str, str]:
    """{binary package: version}"""
    if not shutil.which("dpkg-query"):
        return {}
    try:
        out = subprocess.run(
            ["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\t${db:Status-Status}\n"],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except Exception as e:
        logger.error(f"dpkg-query failed: {e}")
        return {}
    pkgs: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[2] == "installed":
            name = parts[0].split(":")[0]   # arch 접미사 제거
            pkgs[name] = parts[1]
    return pkgs


@lru_cache(maxsize=4096)
def version_lt(a: str, b: str) -> bool:
    """dpkg 버전 비교: a < b"""
    if not shutil.which("dpkg"):
        return a != b and a < b
    try:
        rc = subprocess.run(["dpkg", "--compare-versions", a, "lt", b], timeout=5).returncode
        return rc == 0
    except Exception:
        return False


_APT_LINE = re.compile(r"^(?P<pkg>[^/\s]+)/(?P<suite>\S+)\s+(?P<new>\S+)\s+\S+\s+\[upgradable from:\s*(?P<old>[^\]]+)\]")


def pending_updates() -> dict:
    """apt 기준 미적용 업데이트. {'total', 'security', 'packages': [{name, old, new, security}]}"""
    result = {"total": 0, "security": 0, "packages": [], "available": False, "error": ""}
    if not shutil.which("apt"):
        result["error"] = "apt 없음"
        return result
    try:
        out = subprocess.run(
            ["apt", "list", "--upgradable"], capture_output=True, text=True, timeout=60,
            env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"},
        ).stdout
    except Exception as e:
        result["error"] = str(e)
        return result
    for line in out.splitlines():
        m = _APT_LINE.match(line.strip())
        if not m:
            continue
        suite = m.group("suite")
        is_sec = "security" in suite
        result["packages"].append({"name": m.group("pkg"), "old": m.group("old"), "new": m.group("new"), "suite": suite, "security": is_sec})
        result["total"] += 1
        if is_sec:
            result["security"] += 1
    result["available"] = True

    # apt-check 는 security 집계를 별도로 제공한다 (있으면 신뢰)
    apt_check = "/usr/lib/update-notifier/apt-check"
    if shutil.which(apt_check) or __import__("os").path.exists(apt_check):
        try:
            proc = subprocess.run([apt_check], capture_output=True, text=True, timeout=60)
            txt = (proc.stdout + proc.stderr).strip()
            m = re.search(r"^(\d+);(\d+)$", txt, re.M)
            if m:
                result["total"] = max(result["total"], int(m.group(1)))
                result["security"] = max(result["security"], int(m.group(2)))
        except Exception:
            pass
    return result
