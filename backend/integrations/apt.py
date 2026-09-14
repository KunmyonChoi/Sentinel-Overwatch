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


def merged_usr_candidates(path: str) -> list[str]:
    """
    dpkg 에 물어볼 경로 후보.

    usr-merge 된 시스템(Ubuntu 24.04 등)에서는 /sbin 이 /usr/sbin 을 가리키는 심볼릭 링크지만,
    dpkg 데이터베이스는 패키지를 만들 때의 경로(/sbin/...)를 그대로 들고 있다.
    그래서 실제 파일 경로(/usr/sbin/...)로 물으면 "소유 패키지 없음"이 돌아온다.

    이 판정을 틀리면 배포판이 배포한 정상 파일이 '패키지 소유가 아닌 SUID 바이너리'로 보여
    긴급 알림이 뜬다 (실제로 libpam-tmpdir 의 pam-tmpdir-helper 가 그렇게 잘못 잡혔다).
    그래서 링크를 따라가는 방향과 되돌리는 방향을 모두 시도한다.
    """
    import os
    out = [path]
    real = os.path.realpath(path)
    if real != path:
        out.append(real)                       # /sbin/x → /usr/sbin/x
    for merged in ("/usr/bin/", "/usr/sbin/", "/usr/lib/", "/usr/lib64/"):
        if path.startswith(merged):
            out.append("/" + path[len("/usr/"):])   # /usr/sbin/x → /sbin/x
            break
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


@lru_cache(maxsize=4096)
def package_owner(path: str) -> str | None:
    """dpkg -S 로 파일의 소유 패키지를 찾는다. 없으면 None. (usr-merge 경로를 양방향으로 시도)"""
    if not shutil.which("dpkg-query"):
        return None
    for p in merged_usr_candidates(path):
        try:
            proc = subprocess.run(["dpkg-query", "-S", p], capture_output=True, text=True, timeout=10)
        except Exception:
            return None
        if proc.returncode == 0 and proc.stdout:
            owner = proc.stdout.split(":", 1)[0].strip()
            # "diversion by ..." 형식 제외
            if owner and " " not in owner:
                return owner.split(",")[0].strip()
    return None


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
