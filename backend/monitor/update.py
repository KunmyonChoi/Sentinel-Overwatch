"""
소프트웨어 업데이트 감시.
  - dpkg.log 를 tail 해 설치/업그레이드/제거를 원시 이벤트로 남긴다.
  - 주기적으로 apt 의 미적용 업데이트를 확인해 보안 업데이트가 있으면 알림을 올린다.
"""
import re
import time

import config
from alerts import auto_resolve, raise_alert
from integrations import apt
from monitor.base import BaseMonitor, TailReader

LINE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})\s+(install|upgrade|remove|purge)\s+(\S+)\s+(.*)")
PENDING_CHECK_INTERVAL = 6 * 3600


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

    def setup(self):
        self._try_open()
        self._check_pending()

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
        if time.time() - self._last_pending_check >= self._pending_interval:
            self._check_pending()

    def _process_line(self, line: str):
        m = LINE_PATTERN.match(line)
        if not m:
            return
        _ts, action, package, versions = m.groups()
        pkg = package.split(":")[0]
        v = versions.strip().split()
        if action in ("remove", "purge"):
            d = {"action": action, "package": pkg, "version": v[0] if v else ""}
            self.log_event("SOFTWARE_UPDATE", "WARNING", f"Package {action}d: {pkg} {d['version']}", d)
            if pkg in ("fail2ban", "rsyslog", "openssh-server", "auditd", "ufw", "apparmor", "unattended-upgrades"):
                raise_alert("security_package_removed", "CRITICAL", f"Security package removed: {pkg}",
                            fingerprint=f"pkg_removed:{pkg}", title_ko=f"보안 관련 패키지 제거됨: {pkg}",
                            summary_ko="방어 도구가 제거되면 이 대시보드의 탐지 범위도 줄어듭니다.",
                            action_ko=f"예정된 작업이 아니면 `sudo apt install {pkg}` 로 복구하고 제거한 주체를 auth.log 의 sudo 기록에서 확인하세요.", details=d)
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
