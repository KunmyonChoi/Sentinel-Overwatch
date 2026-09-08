"""
알림(Alert) 엔진.

- 모니터는 사실(Event)을 기록하고, 판단이 필요한 것만 raise_alert 로 올린다.
- 같은 fingerprint 의 OPEN/ACKED 알림이 있으면 count 만 올린다 (중복 억제).
- DEFCON 은 미확인(OPEN) 알림에서만 계산한다. 확인(ack)하면 레벨에서 빠진다.
"""
import datetime
import json
import logging
import threading
import time

from sqlalchemy.orm import Session

import korean
import notifications
from database import Alert, SessionLocal, utcnow

logger = logging.getLogger("alerts")

SEVERITY_RANK = {"INFO": 0, "WARNING": 1, "CRITICAL": 2}


def raise_alert(
    rule: str,
    severity: str,
    title: str,
    *,
    fingerprint: str,
    title_ko: str = "",
    summary: str = "",
    summary_ko: str = "",
    action_ko: str = "",
    evidence: str = "",
    details: dict | None = None,
    is_simulation: bool = False,
    db: Session | None = None,
) -> tuple[Alert, bool]:
    """알림을 생성하거나 기존 알림의 발생 횟수를 올린다. (alert, created) 반환."""
    own = db is None
    db = db or SessionLocal()
    try:
        existing = (
            db.query(Alert)
            .filter(Alert.fingerprint == fingerprint, Alert.status.in_(["OPEN", "ACKED"]))
            .order_by(Alert.id.desc())
            .first()
        )
        now = utcnow()
        if existing:
            existing.count = (existing.count or 1) + 1
            existing.last_seen_at = now
            existing.summary = summary or existing.summary
            existing.summary_ko = summary_ko or existing.summary_ko
            existing.evidence = evidence or existing.evidence
            if details:
                existing.details = json.dumps(details, ensure_ascii=False)
            escalated = SEVERITY_RANK.get(severity, 0) > SEVERITY_RANK.get(existing.severity, 0)
            if escalated:
                existing.severity = severity
                # 심각도가 올라가면 다시 미확인 상태로 돌린다
                existing.status = "OPEN"
            db.commit()
            db.refresh(existing)
            if escalated and not is_simulation:
                _notify(existing, escalated=True)
            return existing, False

        alert = Alert(
            rule=rule,
            fingerprint=fingerprint,
            severity=severity,
            title=title,
            title_ko=title_ko or title,
            summary=summary,
            summary_ko=summary_ko or summary,
            action_ko=action_ko,
            evidence=evidence[:8000] if evidence else None,
            details=json.dumps(details, ensure_ascii=False) if details else None,
            is_simulation=is_simulation,
            created_at=now,
            last_seen_at=now,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        logger.log(
            logging.CRITICAL if severity == "CRITICAL" else logging.WARNING,
            f"ALERT[{rule}] {title}",
        )
        if not is_simulation:
            _notify(alert)
        return alert, True
    except Exception as e:
        db.rollback()
        logger.error(f"raise_alert failed: {e}")
        raise
    finally:
        if own:
            db.close()


def _notify(alert: Alert, escalated: bool = False):
    icon = "🔴" if alert.severity == "CRITICAL" else "🟠"
    prefix = "ESCALATED" if escalated else alert.severity
    msg = alert.summary_ko or alert.summary or ""
    if alert.action_ko:
        msg += f"\n조치: {alert.action_ko}"
    notifications.enqueue(
        title=f"{icon} [{prefix}] {alert.title_ko or alert.title}",
        message=msg,
        color="#ff0000" if alert.severity == "CRITICAL" else "#ffaa00",
    )


def ack_alert(alert_id: int, by: str, db: Session) -> Alert | None:
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert or alert.status == "RESOLVED":
        return None
    alert.status = "ACKED"
    alert.acked_at = utcnow()
    alert.acked_by = by
    db.commit()
    db.refresh(alert)
    return alert


def resolve_alert(alert_id: int, by: str, note: str, db: Session) -> Alert | None:
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return None
    alert.status = "RESOLVED"
    alert.resolved_at = utcnow()
    alert.resolved_by = by
    alert.resolution_note = note or None
    db.commit()
    db.refresh(alert)
    return alert


def auto_resolve(fingerprint: str, note: str = "조건 해소로 자동 해결", db: Session | None = None) -> int:
    """조건이 사라진 알림(예: 미적용 업데이트 0건)을 자동으로 해결 처리한다."""
    own = db is None
    db = db or SessionLocal()
    try:
        rows = db.query(Alert).filter(Alert.fingerprint == fingerprint, Alert.status.in_(["OPEN", "ACKED"])).all()
        for a in rows:
            a.status = "RESOLVED"
            a.resolved_at = utcnow()
            a.resolved_by = "system"
            a.resolution_note = note
        db.commit()
        return len(rows)
    finally:
        if own:
            db.close()


def compute_defcon(db: Session) -> dict:
    """미확인 알림에서 DEFCON 레벨을 계산한다."""
    open_alerts = (
        db.query(Alert)
        .filter(Alert.status == "OPEN", Alert.is_simulation == False)  # noqa: E712
        .order_by(Alert.last_seen_at.desc())
        .all()
    )
    acked = db.query(Alert).filter(Alert.status == "ACKED", Alert.is_simulation == False).count()  # noqa: E712
    critical = [a for a in open_alerts if a.severity == "CRITICAL"]
    warning = [a for a in open_alerts if a.severity == "WARNING"]

    if critical:
        top = critical[0]
        status = "DEFCON 1"
    elif warning:
        top = warning[0]
        status = "DEFCON 3"
    else:
        top = None
        status = "SAFE"

    return {
        "status": status,
        "status_ko": korean.defcon_ko(status),
        "reason": (top.title_ko or top.title) if top else "미확인 알림 없음",
        "action": top.action_ko if top and top.action_ko else ("모니터 상태와 라이브 피드를 주기적으로 확인하세요." if not top else "알림 상세를 확인하세요."),
        "top_alert_id": top.id if top else None,
        "open_critical": len(critical),
        "open_warning": len(warning),
        "acked": acked,
    }


class DefconWatcher:
    """DEFCON 전이를 감시해 상승/복구 알림을 보낸다 (GET 핸들러에 부작용을 두지 않기 위함)."""

    def __init__(self, interval: int = 10):
        self.interval = interval
        self.running = False
        self.prev: str | None = None
        self.current: dict = {"status": "SAFE"}

    def monitor(self):
        self.running = True
        while self.running:
            try:
                db = SessionLocal()
                try:
                    self.current = compute_defcon(db)
                finally:
                    db.close()
                status = self.current["status"]
                if self.prev is not None and status != self.prev:
                    self._on_transition(self.prev, status)
                self.prev = status
            except Exception as e:
                logger.error(f"defcon watcher error: {e}")
            time.sleep(self.interval)

    def _on_transition(self, old: str, new: str):
        rank = {"SAFE": 0, "DEFCON 3": 1, "DEFCON 1": 2}
        if rank.get(new, 0) > rank.get(old, 0):
            color = "#ff0000" if new == "DEFCON 1" else "#ffaa00"
            notifications.enqueue(
                title=f"🚨 {new} ({korean.defcon_ko(new)})",
                message=f"{self.current.get('reason', '')}\n조치: {self.current.get('action', '')}",
                color=color,
            )
        else:
            notifications.enqueue(
                title=f"✅ 상태 완화: {old} → {new} ({korean.defcon_ko(new)})",
                message="미확인 알림이 처리되었습니다.",
                color="#36a64f",
            )


ADMIN_CONTEXT_TYPES = ("SUDO_COMMAND", "AUTH_SUCCESS", "ROOT_SESSION", "SOFTWARE_UPDATE", "AUDIT_WRITE")


def recent_admin_context(minutes: int = 15, limit: int = 5, types: tuple[str, ...] = ADMIN_CONTEXT_TYPES) -> str:
    """무결성/영속화/패키지 이벤트에 붙일 '누가 방금 무엇을 했나' 컨텍스트 (sudo 명령, 로그인)."""
    from database import Event
    db = SessionLocal()
    try:
        since = utcnow() - datetime.timedelta(minutes=minutes)
        rows = (
            db.query(Event)
            .filter(Event.timestamp >= since, Event.event_type.in_(list(types)),
                    Event.is_simulation == False)  # noqa: E712
            .order_by(Event.id.desc()).limit(limit).all()
        )
        if not rows:
            return f"최근 {minutes}분 내 관리자 활동 기록 없음 (sudo/로그인/패키지 변경 없음 → 자동화나 외부 변경 가능성)"
        lines = [f"{e.timestamp.strftime('%H:%M:%S')} {e.description_ko or e.description}"[:160] for e in rows]
        return f"최근 {minutes}분 관리자 활동:\n" + "\n".join(lines)
    except Exception as e:
        return f"(관리자 활동 조회 실패: {e})"
    finally:
        db.close()


def serialize(alert: Alert) -> dict:
    return {
        "id": alert.id,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
        "last_seen_at": alert.last_seen_at.isoformat() if alert.last_seen_at else None,
        "rule": alert.rule,
        "severity": alert.severity,
        "title": alert.title,
        "title_ko": alert.title_ko,
        "summary": alert.summary,
        "summary_ko": alert.summary_ko,
        "action_ko": alert.action_ko,
        "evidence": alert.evidence,
        "details": alert.details_dict(),
        "count": alert.count,
        "status": alert.status,
        "acked_at": alert.acked_at.isoformat() if alert.acked_at else None,
        "acked_by": alert.acked_by,
        "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        "resolved_by": alert.resolved_by,
        "resolution_note": alert.resolution_note,
        "is_simulation": bool(alert.is_simulation),
    }
