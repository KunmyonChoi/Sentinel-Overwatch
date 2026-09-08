"""
IP 차단 관리.

실제 차단은 fail2ban 이 수행한다. fail2ban 을 쓸 수 없으면 차단했다고 표시하지 않고
'RECOMMENDED' 상태로 기록해 운영자가 직접 실행할 명령을 보여준다.
"""
import json
import logging

from sqlalchemy.orm import Session

import config
import korean
from database import BlockedIP, Event, utcnow
from integrations.fail2ban import Fail2banClient

logger = logging.getLogger("ban_manager")


def manual_block_command(ip: str) -> str:
    return f"sudo fail2ban-client set {config.FAIL2BAN_JAIL} banip {ip}  # 또는: sudo nft add rule inet filter input ip saddr {ip} drop"


class BanManager:
    def __init__(self, db: Session, client: Fail2banClient | None = None):
        self.db = db
        self.client = client or Fail2banClient()

    def _log(self, event_type: str, severity: str, description: str, details: dict, is_simulation: bool = False):
        self.db.add(Event(
            event_type=event_type, severity=severity, source="BanManager",
            description=description, description_ko=korean.event_ko(event_type, details),
            details=json.dumps(details, ensure_ascii=False), is_simulation=is_simulation,
        ))

    def ban_ip(self, ip_address: str, reason: str, is_simulation: bool = False) -> dict:
        row = self.db.query(BlockedIP).filter(BlockedIP.ip_address == ip_address).first()
        if row and row.status == "ACTIVE":
            return {"status": "ACTIVE", "changed": False}

        available, why, _hint = (False, "시뮬레이션", "") if is_simulation else self.client.availability()
        if available:
            ok = self.client.ban(ip_address)
            status = "ACTIVE" if ok else "RECOMMENDED"
            source = "fail2ban"
            if not ok:
                why = self.client.last_error
        else:
            status, source = "RECOMMENDED", "detector"

        if row:
            row.status, row.reason, row.source = status, reason, source
            row.blocked_at, row.unblocked_at, row.jail = utcnow(), None, config.FAIL2BAN_JAIL
        else:
            self.db.add(BlockedIP(ip_address=ip_address, reason=reason, status=status, source=source, jail=config.FAIL2BAN_JAIL))

        if status == "ACTIVE":
            logger.warning(f"banned {ip_address} via fail2ban: {reason}")
            self._log("IP_BLOCKED", "INFO", f"IP {ip_address} blocked via fail2ban. Reason: {reason}",
                      {"ip": ip_address, "reason": reason, "source": "fail2ban"}, is_simulation)
        else:
            logger.warning(f"could not ban {ip_address} ({why}); recorded as RECOMMENDED")
            self._log("IP_BLOCK_RECOMMENDED", "WARNING",
                      f"IP {ip_address} should be blocked but fail2ban is unavailable ({why}). Run: {manual_block_command(ip_address)}",
                      {"ip": ip_address, "reason": reason, "why": why, "command": manual_block_command(ip_address)}, is_simulation)
        self.db.commit()
        return {"status": status, "changed": True, "why": why}

    def unblock_ip(self, ip_address: str, by: str = "dashboard") -> tuple[bool, str]:
        row = self.db.query(BlockedIP).filter(
            BlockedIP.ip_address == ip_address, BlockedIP.status.in_(["ACTIVE", "RECOMMENDED"])
        ).first()
        if not row:
            return False, "차단 목록에 없음"
        if row.status == "ACTIVE":
            available, why, _ = self.client.availability()
            if not available:
                return False, f"fail2ban 을 제어할 수 없어 해제하지 못함: {why}"
            if not self.client.unban(ip_address):
                return False, f"fail2ban 해제 실패: {self.client.last_error}"
        row.status = "UNBLOCKED"
        row.unblocked_at = utcnow()
        self._log("IP_UNBLOCKED", "INFO", f"IP {ip_address} unblocked by {by}", {"ip": ip_address, "by": by})
        self.db.commit()
        return True, "해제됨"

    def sync_from_fail2ban(self, banned: list[str] | dict[str, str] | None = None) -> dict | None:
        """fail2ban 의 실제 차단 목록을 DB 에 반영한다. banned 는 [ip] 또는 {ip: jail}. 실패 시 None."""
        if banned is None:
            banned = self.client.banned_ips()
        if banned is None:
            return None
        jail_of: dict[str, str] = banned if isinstance(banned, dict) else {ip: config.FAIL2BAN_JAIL for ip in banned}
        banned_set = set(jail_of)
        active_rows = self.db.query(BlockedIP).filter(BlockedIP.status == "ACTIVE").all()
        active_map = {r.ip_address: r for r in active_rows}
        added, expired = 0, 0
        for ip in banned_set - set(active_map):
            jail = jail_of[ip]
            row = self.db.query(BlockedIP).filter(BlockedIP.ip_address == ip).first()
            if row:
                row.status, row.source, row.blocked_at, row.unblocked_at, row.jail = "ACTIVE", "fail2ban", utcnow(), None, jail
                row.reason = row.reason or f"fail2ban jail {jail}"
            else:
                self.db.add(BlockedIP(ip_address=ip, reason=f"fail2ban jail {jail}", status="ACTIVE", source="fail2ban", jail=jail))
            self._log("IP_BLOCKED", "INFO", f"fail2ban banned {ip} (jail {jail})",
                      {"ip": ip, "reason": f"fail2ban jail {jail}", "source": "fail2ban"})
            added += 1
        # 이미 ACTIVE 인 IP 의 jail 이 바뀌면(sshd → recidive) 반영
        for ip in banned_set & set(active_map):
            if active_map[ip].jail != jail_of[ip]:
                active_map[ip].jail = jail_of[ip]
        for ip, row in active_map.items():
            if ip not in banned_set and row.source == "fail2ban":
                row.status, row.unblocked_at = "EXPIRED", utcnow()
                expired += 1
        self.db.commit()
        return {"banned": len(banned_set), "added": added, "expired": expired}
