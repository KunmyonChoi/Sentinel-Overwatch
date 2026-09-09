"""
컨테이너 설정 점검 (ContainerAudit).

런타임 침해 탐지가 아니라 '설정' 점검이다. privileged, docker 소켓 마운트, 모든 인터페이스 공개 세 가지는
`docker inspect` 한 번으로 확인되며, 각각 호스트 root 획득이나 방화벽 우회로 직결된다.

특히 포트 공개는 호스트 방화벽으로 막히지 않는다. Docker 가 iptables DOCKER 체인에 규칙을 직접 넣어
ufw 보다 먼저 평가되기 때문에, `ufw deny incoming` 만 보고 안전하다고 판단하면 안 된다.

docker 를 쓸 수 없는 호스트에서는 health=degraded 로 표시하고 조용히 넘어간다 (컨테이너를 안 쓰는 것은 정상이다).
"""
from alerts import auto_resolve, raise_alert
from integrations.containers import DockerClient, actionable
from monitor.base import BaseMonitor


class ContainerAudit(BaseMonitor):
    name = "ContainerAudit"
    label = "컨테이너 설정 점검 (docker inspect)"
    interval = 600  # 10분

    def __init__(self, interval: int | None = None, client: DockerClient | None = None):
        super().__init__(interval)
        self.client = client or DockerClient()
        self.source = "docker inspect (실행 중 컨테이너 설정)"
        self.snapshot: dict = {"available": False, "containers": [], "counts": {}}
        self._open: set[str] = set()

    def setup(self):
        self.tick()

    def tick(self):
        snap = self.client.snapshot()
        self.snapshot = snap
        if not snap.get("available"):
            # 컨테이너를 쓰지 않는 호스트도 있으므로 down 이 아니라 degraded 로 둔다
            self.set_health("degraded", snap.get("reason", "docker 상태 확인 불가"), snap.get("fix_hint", ""))
            return
        self.set_health("ok")

        current: set[str] = set()
        for c in snap.get("containers", []):
            for f in actionable(c):
                fp = f"container:{f['code']}:{c['name']}"
                current.add(fp)
                if fp in self._open:
                    continue
                self._open.add(fp)
                d = {
                    "container": c["name"], "container_id": c["id"], "image": c["image"],
                    "restart": c["restart"], "code": f["code"], "severity": f["severity"],
                    "message_ko": f"{c['name']}: {f['title_ko']}",
                }
                self.log_event("CONTAINER_CONFIG", f["severity"], f"{f['code']}: {c['name']} ({c['image']})", d)
                raise_alert(
                    "container_config", f["severity"], f"{f['code']}: {c['name']}",
                    fingerprint=fp,
                    title_ko=f"{f['title_ko']} — {c['name']}",
                    summary_ko=f["detail_ko"],
                    action_ko=f["fix_ko"],
                    evidence=f"image={c['image']} restart={c['restart'] or 'no'}",
                    details=d,
                )
        for fp in sorted(self._open - current):
            auto_resolve(fp, "컨테이너가 내려갔거나 설정이 수정됨")
            self._open.discard(fp)

    def status_payload(self) -> dict:
        return {
            "health": self.health, "health_reason": self.health_reason, "fix_hint": self.fix_hint,
            **self.snapshot,
        }
