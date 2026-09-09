"""
파일 권한 감시 (PermissionMonitor).

판정 규칙은 integrations/permissions_scan.py 에 있다. root 로 도는 조치 스크립트가
같은 모듈을 쓰기 때문에, 감시와 조치가 서로 다른 기준으로 움직일 일이 없다.
여기서는 스캔 결과를 이벤트·알림으로 바꾸고, 고쳐지면 자동 해결하는 일만 한다.

권한을 좁히는 것만으로는 부족하다. 이미 심어진 것이 있는지(autostart 항목, gitconfig 훅 경로)를
함께 확인해 알림의 근거로 붙인다.
"""
from alerts import auto_resolve, raise_alert
from integrations.permissions_scan import (  # noqa: F401  (재수출: 기존 임포트 경로 유지)
    ETC_MAX_DEPTH,
    HOME_SECRETS,
    HOME_SENSITIVE,
    check_secret,
    check_writable,
    hijack_evidence,
    human_homes,
    mode_of,
    narrow,
    scan as scan_paths,
    scan_home,
    scan_tree,
)
from monitor.base import BaseMonitor


class PermissionMonitor(BaseMonitor):
    name = "PermissionMonitor"
    label = "파일 권한 감시 (world-writable·시크릿 노출)"
    interval = 900  # 15분

    def __init__(self, interval: int | None = None, homes: list[str] | None = None, trees: list[str] | None = None):
        super().__init__(interval)
        self._homes = homes
        self.trees = trees if trees is not None else ["/etc"]
        self.source = "홈 디렉터리 설정 파일, /etc, 시크릿 파일 권한"
        self.findings: list[dict] = []
        self._open: set[str] = set()

    def homes(self) -> list[str]:
        return self._homes if self._homes is not None else human_homes()

    def scan(self) -> list[dict]:
        return scan_paths(self.homes(), self.trees)

    def setup(self):
        self.tick()

    def tick(self):
        self.findings = self.scan()
        self.set_health("ok")
        current = set()
        for f in self.findings:
            fp = f"perm:{f['path']}"
            current.add(fp)
            if fp in self._open:
                continue  # 이미 올린 알림은 반복해서 올리지 않는다
            self._open.add(fp)
            evidence = hijack_evidence(f["path"])
            d = {**f, "evidence": evidence}
            self.log_event("FILE_PERMISSION", f["severity"], f"{f['kind']}: {f['path']} mode {f['mode']}", d)
            raise_alert(
                "file_permission", f["severity"], f"{f['kind']}: {f['path']} ({f['mode']})",
                fingerprint=fp,
                title_ko=f["title_ko"],
                summary_ko=f["detail_ko"] + (f" · {evidence}" if evidence else ""),
                action_ko=f"`{f['fix']}` 로 권한을 좁히세요. 대시보드의 '권한 일괄 조치' 로도 적용할 수 있습니다. "
                          f"고치기 전에 이미 심어진 것이 없는지 함께 확인하세요.",
                evidence=evidence,
                details=d,
            )
        for fp in sorted(self._open - current):
            auto_resolve(fp, "권한이 좁혀져 조건 해소")
            self._open.discard(fp)

    def status_payload(self) -> dict:
        return {
            "health": self.health, "health_reason": self.health_reason,
            "scanned_homes": self.homes(), "scanned_trees": self.trees,
            "findings": self.findings,
            "counts": {
                "total": len(self.findings),
                "critical": sum(1 for f in self.findings if f["severity"] == "CRITICAL"),
                "warning": sum(1 for f in self.findings if f["severity"] == "WARNING"),
            },
        }
