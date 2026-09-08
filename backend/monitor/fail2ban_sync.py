"""fail2ban 의 실제 차단 목록을 주기적으로 DB 에 동기화한다."""
from ban_manager import BanManager
from database import SessionLocal
from integrations.fail2ban import Fail2banClient
from monitor.base import BaseMonitor


class Fail2banSync(BaseMonitor):
    name = "Fail2banSync"
    label = "fail2ban 차단 동기화"
    interval = 30

    def __init__(self, interval: int | None = None, client: Fail2banClient | None = None):
        super().__init__(interval)
        self.client = client or Fail2banClient()
        self.source = f"fail2ban-client (jail {self.client.jail})"
        self.stats: dict = {}

    def setup(self):
        self.tick()

    def tick(self):
        # sudo 호출은 주기당 1회 (status <jail>) 로 제한한다. 실패했을 때만 원인 진단 호출을 추가한다.
        banned, stats = self.client.status_snapshot()
        if banned is None:
            ok, why, hint = self.client.availability()
            self.set_health("degraded", why if not ok else f"차단 목록 조회 실패: {self.client.last_error}", hint)
            return
        db = SessionLocal()
        try:
            result = BanManager(db, self.client).sync_from_fail2ban(banned)
        finally:
            db.close()
        self.stats = stats | {"banned": len(banned)}
        self.set_health("ok")
