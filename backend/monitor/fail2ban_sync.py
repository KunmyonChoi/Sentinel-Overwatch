"""fail2ban 의 실제 차단 목록을 주기적으로 DB 에 동기화한다."""
import config
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
        self.source = f"fail2ban-client banned (jails: {', '.join(config.FAIL2BAN_JAILS)})"
        self.stats: dict = {}
        self._tick_no = 0

    def setup(self):
        self.tick()

    def tick(self):
        # sudo 호출은 주기당 1회 (`banned`: 모든 jail) 로 제한한다. 통계는 10주기(5분)마다 한 번 더 읽는다.
        per_jail = self.client.banned_all()
        if per_jail is None:
            ok, why, hint = self.client.availability()
            self.set_health("degraded", why if not ok else f"차단 목록 조회 실패: {self.client.last_error}", hint)
            return
        jail_of: dict[str, str] = {}
        for jail in config.FAIL2BAN_JAILS:
            for ip in per_jail.get(jail, []):
                jail_of.setdefault(ip, jail)
        missing = [j for j in config.FAIL2BAN_JAILS if j not in per_jail]
        db = SessionLocal()
        try:
            BanManager(db, self.client).sync_from_fail2ban(jail_of)
        finally:
            db.close()
        self._tick_no += 1
        if self._tick_no % 10 == 1:
            _b, stats = self.client.status_snapshot()
            self.stats = stats
        self.stats = (self.stats or {}) | {"banned": len(jail_of), "jails": {j: len(per_jail.get(j, [])) for j in per_jail}}
        if missing:
            self.set_health("degraded", f"jail 비활성: {', '.join(missing)}",
                            "deploy/fail2ban-secdash.conf 를 /etc/fail2ban/jail.d/ 에 설치하고 fail2ban 을 reload 하세요.")
        else:
            self.set_health("ok")
