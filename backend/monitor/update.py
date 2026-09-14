"""
소프트웨어 업데이트 감시.
  - dpkg.log 를 tail 해 설치/업그레이드/제거를 원시 이벤트로 남긴다.
  - 주기적으로 apt 의 미적용 업데이트를 확인해 보안 업데이트가 있으면 알림을 올린다.
  - 재부팅이 필요한 상태(/run/reboot-required)를 알린다.

'업데이트 안 함'만 보면 절반만 보는 것이다. 실제로 더 흔하고 더 오래 가는 위험은
**업데이트는 했는데 재부팅을 안 한 상태**다. libc 나 커널을 갈아도 이미 떠 있는
프로세스는 옛 것을 그대로 쓰므로, 취약점은 재부팅 전까지 살아 있다. 그런데 apt 는
"밀린 것 없음"이라고 답하기 때문에, 이 파일을 보지 않으면 남은 할 일을 아무도
알려주지 않는다.
"""
import os
import re
import time

import config
from alerts import auto_resolve, raise_alert, recent_admin_context
from integrations import apt
from monitor.base import BaseMonitor, TailReader

LINE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})\s+(install|upgrade|remove|purge)\s+(\S+)\s+(.*)")
PENDING_CHECK_INTERVAL = 6 * 3600
# /var/run 은 보통 /run 의 심볼릭 링크지만, 아닌 시스템도 있어 둘 다 본다.
REBOOT_FLAGS = ("/run/reboot-required", "/var/run/reboot-required")
# 재부팅 전까지 옛 코드가 계속 도는 것들. 남은 할 일을 말할 때 이 이름이 있으면 더 분명해진다.
REBOOT_HEAVY = ("linux-image", "linux-base", "libc6", "systemd", "dbus", "openssl", "libssl")


class UpdateMonitor(BaseMonitor):
    name = "UpdateMonitor"
    label = "패키지 변경/미적용 업데이트"
    interval = 2

    def __init__(self, log_path: str | None = None, pending_interval: int = PENDING_CHECK_INTERVAL):
        super().__init__()
        self.log_path = log_path or config.DPKG_LOG_PATH
        self.source = f"{self.log_path} + apt list --upgradable"
        self._reader: TailReader | None = None
        self._pending_interval = pending_interval
        self._last_pending_check = 0.0
        self.pending: dict = {}
        self._last_pending_key: tuple | None = None
        self.reboot: dict = {}
        self._last_reboot_key: tuple | None = None

    def setup(self):
        self._try_open()
        self._check_pending()
        self._check_reboot()

    def _try_open(self) -> bool:
        try:
            r = TailReader(self.log_path)
            r.open(seek_end=True)
            self._reader = r
            self.set_health("ok")
            return True
        except FileNotFoundError:
            self.set_health("degraded", f"dpkg 로그 없음: {self.log_path}", "Debian 계열이 아니면 SECDASH_DPKG_LOG 를 비우고 이 모니터를 무시하세요.")
        except PermissionError:
            self.set_health("degraded", f"dpkg 로그 읽기 권한 없음: {self.log_path}")
        return False

    def tick(self):
        if self._reader is None:
            self._try_open()
        if self._reader is not None:
            for _ in range(2000):
                line = self._reader.readline()
                if not line:
                    break
                self._process_line(line.strip())
        # 파일 하나를 보는 일이라 매 주기 확인해도 부담이 없다. 다만 알림은 상태가
        # 바뀔 때만 올린다 — 같은 지문으로 계속 부르면 발생 횟수만 부풀어 오른다.
        self._check_reboot()
        if time.time() - self._last_pending_check >= self._pending_interval:
            self._check_pending()

    def _check_reboot(self):
        """재부팅 대기 상태. 파일이 사라지면(=재부팅함) 스스로 해결 처리한다."""
        flag = next((p for p in REBOOT_FLAGS if os.path.exists(p)), None)
        pkgs: list[str] = []
        if flag:
            try:
                with open(flag + ".pkgs", encoding="utf-8", errors="replace") as f:
                    pkgs = sorted({ln.strip() for ln in f if ln.strip()})
            except OSError:
                pkgs = []   # 목록을 못 읽어도 '재부팅 필요'라는 사실은 그대로다
        key = (bool(flag), tuple(pkgs))
        changed = key != self._last_reboot_key
        self._last_reboot_key = key
        self.reboot = {"required": bool(flag), "packages": pkgs}
        if not flag:
            if changed:
                auto_resolve("reboot_required", "재부팅되어 자동 해결")
            return
        if not changed:
            return
        heavy = [p for p in pkgs if p.startswith(REBOOT_HEAVY)]
        d = {"packages": pkgs, "heavy": heavy, "flag": flag}
        self.log_event("PENDING_UPDATES", "WARNING",
                       f"reboot required ({len(pkgs)} pkg(s))",
                       d | {"message_ko": "재부팅이 필요한 상태입니다"})
        why = ("이미 떠 있는 프로그램은 옛 " + ", ".join(heavy[:3]) + " 를 그대로 쓰고 있어서, "
               "재부팅 전까지 취약점이 살아 있습니다.") if heavy else \
              "새 버전이 설치됐지만 재부팅해야 적용됩니다."
        raise_alert(
            "reboot_required", "WARNING", f"System restart required ({len(pkgs)} pkg(s))",
            fingerprint="reboot_required",
            title_ko="업데이트를 마치려면 재부팅이 필요합니다",
            summary_ko=(("대상: " + ", ".join(pkgs[:15]) + (" 외" if len(pkgs) > 15 else "") + ". ")
                        if pkgs else "") + why,
            action_ko="점검 창을 선언한 뒤 `sudo reboot` 하세요. "
                      "지금 못 하면 `sudo needrestart -r a` 로 재시작이 필요한 서비스만 먼저 올릴 수 있습니다.",
            evidence=f"{flag} 존재\n" + ("\n".join(f"  {p}" for p in pkgs) if pkgs else "  (패키지 목록 없음)"),
            details=d,
        )

    def _process_line(self, line: str):
        m = LINE_PATTERN.match(line)
        if not m:
            return
        _ts, action, package, versions = m.groups()
        pkg = package.split(":")[0]
        v = versions.strip().split()
        if action in ("remove", "purge"):
            # 누가 지웠는지: 최근 sudo 명령/로그인 (패키지 이벤트끼리는 제외해 연쇄 제거 시 자기 참조를 막는다)
            ctx = recent_admin_context(types=("SUDO_COMMAND", "AUTH_SUCCESS", "ROOT_SESSION"))
            d = {"action": action, "package": pkg, "version": v[0] if v else "", "admin_context": ctx}
            self.log_event("SOFTWARE_UPDATE", "WARNING", f"Package {action}d: {pkg} {d['version']}", d)
            if pkg in ("fail2ban", "rsyslog", "openssh-server", "auditd", "ufw", "apparmor", "unattended-upgrades"):
                raise_alert("security_package_removed", "CRITICAL", f"Security package removed: {pkg}",
                            fingerprint=f"pkg_removed:{pkg}", title_ko=f"보안 관련 패키지 제거됨: {pkg}",
                            summary_ko="방어 도구가 제거되면 이 대시보드의 탐지 범위도 줄어듭니다.",
                            action_ko=f"예정된 작업이 아니면 `sudo apt install {pkg}` 로 복구하고 제거한 주체를 확인하세요.",
                            evidence=ctx, details=d)
        elif action == "install":
            d = {"action": action, "package": pkg, "version": v[-1] if v else ""}
            self.log_event("SOFTWARE_UPDATE", "INFO", f"Package installed: {pkg} {d['version']}", d)
        elif action == "upgrade":
            old, new = (v + ["", ""])[:2]
            d = {"action": action, "package": pkg, "old": old, "new": new}
            self.log_event("SOFTWARE_UPDATE", "INFO", f"Package upgraded: {pkg} {old} -> {new}", d)

    def _check_pending(self):
        self._last_pending_check = time.time()
        info = apt.pending_updates()
        self.pending = info
        if not info.get("available"):
            return
        sec = [p["name"] for p in info["packages"] if p["security"]]
        d = {"total": info["total"], "security": info["security"], "packages": sec[:50]}
        key = (info["total"], info["security"])
        changed = key != self._last_pending_key
        self._last_pending_key = key
        if info["security"] > 0:
            if changed:
                self.log_event("PENDING_UPDATES", "WARNING", f"{info['security']} security updates pending ({info['total']} total)", d)
            raise_alert(
                "pending_security_updates", "WARNING", f"{info['security']} security updates pending",
                fingerprint="pending_security_updates",
                title_ko=f"보안 업데이트 {info['security']}건 미적용 (전체 {info['total']}건)",
                summary_ko="대상: " + (", ".join(sec[:15]) + (" 외" if len(sec) > 15 else "") if sec else "apt-check 집계"),
                action_ko="`sudo apt update && sudo apt upgrade` 를 점검 창에서 실행하세요. 커널 업데이트가 포함되면 재부팅이 필요합니다. 자동 적용을 원하면 unattended-upgrades 를 활성화하세요.",
                details=d,
            )
        else:
            auto_resolve("pending_security_updates", "보안 업데이트가 모두 적용됨")
            if info["total"] > 0 and changed:
                self.log_event("PENDING_UPDATES", "INFO", f"{info['total']} non-security updates pending", d)
