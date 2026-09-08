"""
fail2ban 연동. 차단의 진실 원천(source of truth)은 fail2ban 이다.

root 가 아니면 sudo -n 으로 fail2ban-client 를 호출한다.
deploy/sudoers-secdash 에 허용 명령이 정의되어 있다.
"""
import logging
import re
import shutil
import subprocess

import config

logger = logging.getLogger("fail2ban")

_IP_RE = re.compile(r"[0-9a-fA-F:.]+")


def parse_banned_output(out: str) -> dict[str, list[str]]:
    """`fail2ban-client banned` 출력: [{'sshd': ['1.2.3.4']}, {'recidive': []}]"""
    import ast
    text = out.strip()
    try:
        data = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return {}
    result: dict[str, list[str]] = {}
    items = data if isinstance(data, list) else [data]
    for item in items:
        if isinstance(item, dict):
            for jail, ips in item.items():
                result[str(jail)] = [str(ip) for ip in (ips or []) if _IP_RE.fullmatch(str(ip))]
    return result


class Fail2banClient:
    def __init__(self, jail: str | None = None, use_sudo: bool | None = None, client: str | None = None):
        self.jail = jail or config.FAIL2BAN_JAIL
        self.use_sudo = config.FAIL2BAN_USE_SUDO if use_sudo is None else use_sudo
        self.client = client or config.FAIL2BAN_CLIENT
        self._last_error = ""

    # --- 저수준 실행 ---
    def _cmd(self, *args: str) -> list[str]:
        base = [self.client, *args]
        if self.use_sudo:
            return ["sudo", "-n", *base]
        return base

    def _run(self, *args: str, timeout: int = 10) -> tuple[int, str]:
        if not shutil.which(self.client) and not shutil.which("fail2ban-client"):
            self._last_error = "fail2ban-client 가 설치되어 있지 않음"
            return 127, ""
        try:
            proc = subprocess.run(self._cmd(*args), capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError as e:
            self._last_error = str(e)
            return 127, ""
        except subprocess.TimeoutExpired:
            self._last_error = "fail2ban-client 응답 시간 초과"
            return 124, ""
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            self._last_error = out.strip().splitlines()[-1] if out.strip() else f"rc={proc.returncode}"
        return proc.returncode, out

    # --- 상태 ---
    def availability(self) -> tuple[bool, str, str]:
        """(사용 가능 여부, 사유, 해결 힌트)"""
        if not shutil.which(self.client) and not shutil.which("fail2ban-client"):
            return False, "fail2ban 미설치", "sudo apt install fail2ban 후 sshd jail 을 활성화하세요."
        rc, out = self._run("status", self.jail)
        if rc == 0:
            return True, "", ""
        err = self._last_error
        if "password is required" in err or "sudo:" in err:
            return (False, f"fail2ban 제어 권한 없음 (sudo 실패: {err[:120]})",
                    "deploy/sudoers-secdash 설치 여부와 systemd 유닛의 CapabilityBoundingSet/ProtectSystem 설정을 확인하세요.")
        if "Permission denied" in err:
            return (False, "fail2ban 소켓 접근 권한 없음",
                    "deploy/sudoers-secdash 를 설치해 sudo -n fail2ban-client 를 허용하세요.")
        if "Failed to access socket" in err or "not running" in err.lower():
            return False, "fail2ban 서비스가 실행 중이 아님", "sudo systemctl enable --now fail2ban"
        if "does not exist" in err.lower() or "unknown jail" in err.lower():
            return False, f"jail '{self.jail}' 이 없음", "/etc/fail2ban/jail.local 에 [sshd] enabled = true 를 설정하세요."
        return False, f"fail2ban 오류: {err}", ""

    def banned_ips(self) -> list[str] | None:
        """현재 jail 의 차단 IP 목록. 실패 시 None."""
        rc, out = self._run("get", self.jail, "banip")
        if rc == 0:
            return [t for t in out.split() if _IP_RE.fullmatch(t)]
        rc, out = self._run("status", self.jail)
        if rc != 0:
            return None
        for line in out.splitlines():
            if "Banned IP list:" in line:
                return [t for t in line.split(":", 1)[1].split() if _IP_RE.fullmatch(t)]
        return []

    def banned_all(self) -> dict[str, list[str]] | None:
        """`fail2ban-client banned` 한 번으로 모든 jail 의 차단 목록을 얻는다. {jail: [ip]}"""
        rc, out = self._run("banned")
        if rc != 0:
            return None
        return parse_banned_output(out)

    def status_snapshot(self) -> tuple[list[str] | None, dict]:
        """status <jail> 한 번으로 (차단 IP 목록, 통계) 를 얻는다. sudo 호출을 최소화하기 위함."""
        rc, out = self._run("status", self.jail)
        if rc != 0:
            return None, {}
        banned: list[str] = []
        stats: dict = {}
        for line in out.splitlines():
            if "Banned IP list:" in line:
                banned = [t for t in line.split(":", 1)[1].split() if _IP_RE.fullmatch(t)]
            m = re.search(r"(Currently failed|Total failed|Currently banned|Total banned):\s*(\d+)", line)
            if m:
                stats[m.group(1).lower().replace(" ", "_")] = int(m.group(2))
        return banned, stats

    def jail_stats(self) -> dict:
        rc, out = self._run("status", self.jail)
        stats: dict = {}
        if rc != 0:
            return stats
        for line in out.splitlines():
            m = re.search(r"(Currently failed|Total failed|Currently banned|Total banned):\s*(\d+)", line)
            if m:
                stats[m.group(1).lower().replace(" ", "_")] = int(m.group(2))
        return stats

    # --- 제어 ---
    def ban(self, ip: str) -> bool:
        rc, out = self._run("set", self.jail, "banip", ip)
        if rc != 0:
            logger.error(f"fail2ban ban {ip} failed: {self._last_error}")
        return rc == 0

    def unban(self, ip: str) -> bool:
        rc, out = self._run("set", self.jail, "unbanip", ip)
        if rc != 0:
            logger.error(f"fail2ban unban {ip} failed: {self._last_error}")
        return rc == 0

    @property
    def last_error(self) -> str:
        return self._last_error
