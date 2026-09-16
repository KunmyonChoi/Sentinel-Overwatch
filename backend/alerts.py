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

import config
import korean
import notifications
from database import Alert, MaintenanceWindow, SessionLocal, utcnow

logger = logging.getLogger("alerts")

SEVERITY_RANK = {"INFO": 0, "WARNING": 1, "CRITICAL": 2}

# 점검 모드 중 자동 확인되는 규칙 (계획 작업으로 생기는 것들). 침입 신호는 절대 포함하지 않는다.
MAINTENANCE_RULE_PREFIXES = (
    "integrity_change", "persistence_", "security_package_removed", "pending_security_updates",
    "new_listener", "kernel_module", "lynis_", "usn_affects_host", "high_cpu", "high_memory", "disk_full", "process_spike",
    # 설정 점검 계열: 작업 중 서비스를 띄우거나 권한을 잠시 바꾸면 걸리는 것들 (침입 신호가 아니다)
    "exposed_port", "file_permission", "container_config",
)

# 확인(ACKED)만 된 채 오래 남은 알림을 시간 경과로 정리할 수 있는 규칙.
#
# 여기 있는 것은 모두 '지금 상태'에 관한 규칙이고, 조건이 사라지면 그것을 관찰한 모니터가
# auto_resolve 로 직접 닫는다 (노출 포트가 닫힘, 권한이 좁혀짐, 업데이트가 적용됨 …).
# 그래서 이 규칙들이 ACKED 로 오래 남아 있는 것은 "사람이 보고 받아들인 상태"에 가깝다.
#
# 침입 신호(브루트포스, 실패 후 성공, 리버스 셸, 계정 변경, 영속화, 커널 모듈, 스캔 뒤 접속 …)는
# 절대 넣지 않는다. 그것은 '한 번 일어난 사실'이고, 다시 보이지 않는 것이 처리됐다는 뜻이 아니다.
# 목록에 없는 새 규칙도 건드리지 않는다 — 분류하지 않은 것은 그대로 둔다(모르면 손대지 않는다).
AGEABLE_ACKED_RULE_PREFIXES = (
    "exposed_port", "file_permission", "container_config", "new_listener",
    "pending_security_updates", "reboot_required", "usn_affects_host", "lynis_",
    "high_cpu", "high_memory", "disk_full", "process_spike", "time_unsynced",
)
_mw_cache: dict = {"at": 0.0, "win": None}


def active_maintenance(db: Session | None = None, force: bool = False) -> MaintenanceWindow | None:
    """현재 활성 점검 창 (5초 캐시)."""
    now = time.time()
    if not force and now - _mw_cache["at"] < 5:
        return _mw_cache["win"]
    own = db is None
    db = db or SessionLocal()
    try:
        win = (
            db.query(MaintenanceWindow)
            .filter(MaintenanceWindow.ended_at.is_(None), MaintenanceWindow.ends_at > utcnow())
            .order_by(MaintenanceWindow.id.desc()).first()
        )
        if win:
            db.expunge(win)
        _mw_cache.update(at=now, win=win)
        return win
    finally:
        if own:
            db.close()


def start_maintenance(minutes: int, note: str, by: str, db: Session) -> MaintenanceWindow:
    end_maintenance(by, db)
    win = MaintenanceWindow(started_at=utcnow(), ends_at=utcnow() + datetime.timedelta(minutes=max(1, min(minutes, 24 * 60))), note=note, by=by)
    db.add(win)
    db.commit()
    db.refresh(win)
    _mw_cache["at"] = 0.0
    return win


def end_maintenance(by: str, db: Session) -> int:
    rows = db.query(MaintenanceWindow).filter(MaintenanceWindow.ended_at.is_(None), MaintenanceWindow.ends_at > utcnow()).all()
    for w in rows:
        w.ended_at = utcnow()
    db.commit()
    _mw_cache["at"] = 0.0
    return len(rows)


def maintenance_payload(win: MaintenanceWindow | None) -> dict:
    if not win:
        return {"active": False}
    remaining = int((win.ends_at - utcnow()).total_seconds())
    return {"active": True, "id": win.id, "note": win.note, "by": win.by, "started_at": win.started_at.isoformat(),
            "ends_at": win.ends_at.isoformat(), "remaining_seconds": max(0, remaining)}


def ack_all(db: Session, by: str, note: str = "", rule: str | None = None, ids: list[int] | None = None) -> int:
    q = db.query(Alert).filter(Alert.status == "OPEN")
    if rule:
        q = q.filter(Alert.rule == rule)
    if ids:
        q = q.filter(Alert.id.in_(ids))
    rows = q.all()
    now = utcnow()
    for a in rows:
        a.status, a.acked_at, a.acked_by = "ACKED", now, by
        if note:
            a.resolution_note = note
    db.commit()
    return len(rows)


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

        win = active_maintenance() if rule.startswith(MAINTENANCE_RULE_PREFIXES) else None
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
            details=json.dumps((details or {}) | ({"maintenance": win.note or True} if win else {}), ensure_ascii=False) if (details or win) else None,
            is_simulation=is_simulation,
            created_at=now,
            last_seen_at=now,
        )
        if win:
            alert.status, alert.acked_at, alert.acked_by = "ACKED", now, "점검 모드"
            alert.resolution_note = f"점검 모드 중 발생 ({win.by or '?'}: {win.note or '메모 없음'})"
        db.add(alert)
        db.commit()
        db.refresh(alert)
        logger.log(
            logging.CRITICAL if severity == "CRITICAL" else logging.WARNING,
            f"ALERT[{rule}] {title}" + (" [maintenance]" if win else ""),
        )
        if not is_simulation and not win:
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


def open_fingerprints(rule: str, db: Session | None = None) -> set[str]:
    """
    이 규칙으로 아직 살아 있는(OPEN/ACKED) 알림의 지문.

    상태를 대조해 정리하는 모니터(노출 면, 파일 권한, 컨테이너 설정)는 '내가 무엇을 올렸는지'를
    기억해야 조건이 사라졌을 때 해결 처리할 수 있다. 그 기억이 메모리에만 있으면 재시작하는 순간
    사라지고, 이미 없어진 문제의 알림이 영원히 남는다. 그래서 시작할 때 DB 에서 되찾는다.
    """
    own = db is None
    db = db or SessionLocal()
    try:
        rows = db.query(Alert.fingerprint).filter(Alert.rule == rule, Alert.status.in_(["OPEN", "ACKED"])).all()
        return {r[0] for r in rows if r[0]}
    except Exception as e:
        logger.error(f"open_fingerprints({rule}) failed: {e}")
        return set()
    finally:
        if own:
            db.close()


def open_alerts_details(rule: str, db: Session | None = None) -> list[tuple[str, dict]]:
    """살아 있는 알림의 (지문, details).

    알림을 올릴 때 근거가 된 사실을 details 에 넣어두면, 나중에 그 사실이 아직도
    유효한지 다시 대조할 수 있다. 재대조가 없으면 이미 해결된 일의 알림이 사람이
    손으로 닫을 때까지 남는다 — 그게 쌓이면 목록 전체를 안 보게 된다.
    """
    own = db is None
    db = db or SessionLocal()
    try:
        rows = db.query(Alert.fingerprint, Alert.details).filter(
            Alert.rule == rule, Alert.status.in_(["OPEN", "ACKED"])).all()
        out = []
        for fp, raw in rows:
            if not fp:
                continue
            try:
                out.append((fp, json.loads(raw) if raw else {}))
            except (ValueError, TypeError):
                out.append((fp, {}))
        return out
    except Exception as e:
        logger.error(f"open_alerts_details({rule}) failed: {e}")
        return []
    finally:
        if own:
            db.close()


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


def age_out_acked(days: int | None = None, db: Session | None = None) -> dict:
    """확인(ACKED)만 된 채 오래된 알림을 자동 해결로 정리한다.

    확인(ack)은 "봤다"는 표시일 뿐 "끝났다"가 아니다. 그래서 ACKED 는 사람이 해결로 바꾸거나
    모니터가 조건 해소를 관찰할 때까지 남고, 둘 다 일어나지 않으면 영원히 남는다. 오래 운영하면
    여기에만 수백 건이 쌓이는데, 그렇게 쌓인 목록은 결국 아무도 보지 않는다.

    정리 대상은 AGEABLE_ACKED_RULE_PREFIXES 뿐이다. 침입 신호와 아직 분류하지 않은 규칙은
    건드리지 않고, 남겨둔 건수와 규칙을 이벤트로 남긴다 — 조용히 남겨두면 목록이 왜 줄지
    않는지 아무도 알 수 없다.

    지우는 것은 없다. 상태만 RESOLVED 로 옮기고, note 에 '조치를 확인한 것이 아니라 시간이
    지나 닫혔다'고 그대로 적는다. 이후 보존 기간(ALERT_RETENTION_DAYS)이 지나면 삭제된다.
    """
    from database import Event
    days = config.ACKED_AGE_DAYS if days is None else days
    if days <= 0:
        return {"days": days, "resolved": 0, "kept": 0, "kept_rules": [], "enabled": False}
    own = db is None
    db = db or SessionLocal()
    try:
        cutoff = utcnow() - datetime.timedelta(days=days)
        rows = (
            db.query(Alert)
            .filter(Alert.status == "ACKED", Alert.last_seen_at.isnot(None), Alert.last_seen_at < cutoff)
            .all()
        )
        aged = [a for a in rows if (a.rule or "").startswith(AGEABLE_ACKED_RULE_PREFIXES)]
        aged_ids = {a.id for a in aged}
        kept = [a for a in rows if a.id not in aged_ids]
        now = utcnow()
        for a in aged:
            note = (f"확인(ack)만 된 채 {days}일이 지나 자동으로 정리했습니다 "
                    f"(마지막 관찰 {a.last_seen_at.strftime('%Y-%m-%d')}). "
                    f"조치를 확인해서 닫은 것이 아니라 시간이 지나 닫은 것입니다.")
            if a.resolution_note:
                note += f" 이전 메모: {a.resolution_note}"
            a.status, a.resolved_at, a.resolved_by, a.resolution_note = "RESOLVED", now, "system", note
        kept_rules = sorted({a.rule for a in kept if a.rule})
        result = {"days": days, "resolved": len(aged), "kept": len(kept), "kept_rules": kept_rules, "enabled": True}
        if aged or kept:
            msg = (f"확인만 된 채 {days}일이 지난 알림 {len(aged)}건을 자동 해결로 정리했어요"
                   if aged else f"확인만 된 채 {days}일이 지난 알림을 살펴봤어요 (정리한 것 없음)")
            if kept:
                msg += (f". 침입 신호처럼 시간만으로는 끝났다고 볼 수 없는 {len(kept)}건은 닫지 않고 "
                        f"'대응 중'으로 그대로 뒀어요 (규칙: {', '.join(kept_rules[:8])}"
                        f"{' 외' if len(kept_rules) > 8 else ''})")
            db.add(Event(
                event_type="ALERT_AGED", severity="INFO", source="보존 정책",
                description=(f"aged out {len(aged)} ACKED alert(s) not seen for {days}d; "
                             f"kept {len(kept)} unageable (intrusion-signal/unclassified)"),
                description_ko=msg, details=json.dumps(result, ensure_ascii=False),
            ))
            logger.info(f"acked ageing: resolved={len(aged)} kept={len(kept)} rules={kept_rules}")
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        logger.error(f"age_out_acked failed: {e}")
        return {"days": days, "resolved": 0, "kept": 0, "kept_rules": [], "enabled": True, "error": str(e)}
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


def recent_package_activity(package: str, minutes: int = 30) -> str | None:
    """최근 N분 내 해당 패키지의 설치/업그레이드/제거 이벤트가 있으면 그 설명을 돌려준다."""
    from database import Event
    db = SessionLocal()
    try:
        since = utcnow() - datetime.timedelta(minutes=minutes)
        rows = db.query(Event).filter(Event.timestamp >= since, Event.event_type == "SOFTWARE_UPDATE").order_by(Event.id.desc()).limit(300).all()
        for e in rows:
            if e.details_dict().get("package") == package:
                return e.description_ko or e.description
        return None
    except Exception:
        return None
    finally:
        db.close()


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
