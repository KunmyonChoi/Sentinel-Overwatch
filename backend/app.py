"""
Security Dashboard 백엔드.

역할: 검증된 호스트 도구(fail2ban, rsyslog auth.log, dpkg/apt, /proc)의 관찰 결과를
상관 분석해 알림으로 만들고, 한국어로 조치 방법을 안내하는 뷰/트리아지 계층.
"""
from log_config import setup_logging
setup_logging()

import hmac
import ipaddress
import logging
import os
import platform
import socket
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import psutil
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

import alerts as alert_engine
import config
import database
import korean
import translate
from ban_manager import BanManager, manual_block_command
from database import Alert, BlockedIP, Event, get_db, utcnow
from integrations.fail2ban import Fail2banClient
from integrations import modules as kmod
from monitor.fail2ban_sync import Fail2banSync
from monitor.integrity import IntegrityMonitor, PersistenceMonitor
from monitor.intel import IntelMonitor
from monitor.intrusion import AuthLogWatcher, NetworkWatcher
from monitor.lynis import LynisMonitor
from monitor.audit import AuditMonitor
from monitor.process_audit import ProcessAudit
from monitor.resource import ResourceMonitor
from monitor.update import UpdateMonitor

logger = logging.getLogger("app")

# --- 백그라운드 상태 ------------------------------------------------------
monitor_registry: dict[str, dict] = {}
monitors: list = []
defcon_watcher = alert_engine.DefconWatcher(interval=10)
_resource_cache: dict = {"cpu_percent": 0.0, "mem_used_gb": 0.0, "mem_total_gb": 0.0, "mem_percent": 0.0, "disk_percent": 0.0}
_started_at = utcnow()


def _update_resource_cache():
    while True:
        try:
            cpu = psutil.cpu_percent(interval=3)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            _resource_cache.update({
                "cpu_percent": cpu,
                "mem_used_gb": round(mem.used / 1024**3, 1),
                "mem_total_gb": round(mem.total / 1024**3, 1),
                "mem_percent": mem.percent,
                "disk_percent": disk.percent,
            })
        except Exception:
            pass
        time.sleep(7)


def _retention_loop():
    # 기동 직후에는 실행하지 않는다: 운영자가 보존 기간(SECDASH_*_RETENTION_DAYS)을 조정할 여유를 준다
    time.sleep(3600)
    while True:
        database.apply_retention()
        time.sleep(24 * 3600)


def _start_monitor(instance):
    t = threading.Thread(target=instance.monitor, daemon=True, name=instance.name)
    t.start()
    monitors.append(instance)
    monitor_registry[instance.name] = {"instance": instance, "thread": t}


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    translate.load_cache()
    for inst in (
        AuthLogWatcher(), Fail2banSync(), NetworkWatcher(), ProcessAudit(), IntegrityMonitor(),
        PersistenceMonitor(), UpdateMonitor(), ResourceMonitor(), IntelMonitor(),
        AuditMonitor(), LynisMonitor(),
    ):
        try:
            _start_monitor(inst)
        except Exception as e:
            logger.exception(f"failed to start {inst.name}: {e}")
    threading.Thread(target=defcon_watcher.monitor, daemon=True, name="DefconWatcher").start()
    threading.Thread(target=_update_resource_cache, daemon=True, name="ResourceCache").start()
    threading.Thread(target=_retention_loop, daemon=True, name="Retention").start()
    logger.info(f"all monitors started; API token file: {config.API_TOKEN_FILE}")
    yield
    for m in monitors:
        m.stop()
    defcon_watcher.running = False


app = FastAPI(title="Security Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", f"http://{config.HOST}:{config.PORT}", f"http://localhost:{config.PORT}"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Token"],
)


@app.middleware("http")
async def require_api_token(request: Request, call_next):
    """모든 /api 요청은 X-API-Token 헤더가 필요하다. 커스텀 헤더라 브라우저가 preflight 를 강제하므로 CSRF 도 막힌다."""
    if request.url.path.startswith("/api/") and request.method != "OPTIONS":
        token = request.headers.get("X-API-Token", "")
        if not token or not hmac.compare_digest(token, config.API_TOKEN):
            return JSONResponse({"detail": "invalid or missing X-API-Token"}, status_code=401)
    return await call_next(request)


# --- 직렬화 -----------------------------------------------------------------
def _event_dict(e: Event) -> dict:
    return {
        "id": e.id,
        "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        "event_type": e.event_type,
        "event_type_ko": korean.event_type_ko(e.event_type),
        "severity": e.severity,
        "source": e.source,
        "description": e.description,
        "description_ko": e.description_ko or "",
        "details": e.details_dict(),
        "is_simulation": bool(e.is_simulation),
    }


def _blocked_dict(b: BlockedIP) -> dict:
    return {
        "id": b.id, "ip_address": b.ip_address, "reason": b.reason, "status": b.status, "source": b.source, "jail": b.jail,
        "blocked_at": b.blocked_at.isoformat() if b.blocked_at else None,
        "manual_command": manual_block_command(b.ip_address) if b.status == "RECOMMENDED" else None,
    }


# --- 엔드포인트 -------------------------------------------------------------
@app.get("/api/events")
def get_events(limit: int = 100, include_simulation: bool = True, severity: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Event).filter(Event.event_type != "THREAT_INTEL")
    if not include_simulation:
        q = q.filter(Event.is_simulation == False)  # noqa: E712
    if severity:
        q = q.filter(Event.severity == severity.upper())
    rows = q.order_by(Event.timestamp.desc(), Event.id.desc()).limit(min(limit, 500)).all()
    return [_event_dict(e) for e in rows]


@app.get("/api/intel")
def get_intel(limit: int = 30, db: Session = Depends(get_db)):
    rows = db.query(Event).filter(Event.event_type == "THREAT_INTEL").order_by(Event.timestamp.desc(), Event.id.desc()).limit(min(limit, 200)).all()
    out = []
    for e in rows:
        d = e.details_dict()
        title = d.get("title") or (e.description or "").rsplit(" - ", 1)[0].replace("New Threat Intel: ", "")
        if d.get("feed") == "usn":
            # USN 제목은 정형이라 외부 번역이 필요 없다
            ko, urgency = (f"Ubuntu 보안 공지 — 영향 패키지: " + ", ".join(a["package"] for a in d.get("affected", [])[:6])) if d.get("affects_host") else "", ""
        else:
            ko, urgency = translate.translate_intel(title)
        out.append({
            **_event_dict(e),
            "title": title,
            "link": d.get("link") or ((e.description or "").rsplit(" - ", 1)[-1] if " - " in (e.description or "") else ""),
            "feed": d.get("feed", "news"),
            "affects_host": bool(d.get("affects_host")),
            "affected": d.get("affected", []),
            "cves": d.get("cves", []),
            "description_ko": ko,
            "urgency": ("HIGH" if d.get("affects_host") else urgency),
        })
    return out


@app.get("/api/alerts")
def get_alerts(status: str = "active", limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(Alert)
    if status == "active":
        q = q.filter(Alert.status.in_(["OPEN", "ACKED"]))
    elif status != "all":
        q = q.filter(Alert.status == status.upper())
    rows = q.order_by(Alert.last_seen_at.desc()).limit(min(limit, 500)).all()
    return [alert_engine.serialize(a) for a in rows]


class AckBody(BaseModel):
    by: str = "dashboard"
    note: str = ""


@app.post("/api/alerts/{alert_id}/ack")
def ack_alert(alert_id: int, body: AckBody | None = None, db: Session = Depends(get_db)):
    body = body or AckBody()
    a = alert_engine.ack_alert(alert_id, body.by, db)
    if not a:
        raise HTTPException(404, "alert not found or already resolved")
    return alert_engine.serialize(a)


@app.post("/api/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: int, body: AckBody | None = None, db: Session = Depends(get_db)):
    body = body or AckBody()
    a = alert_engine.resolve_alert(alert_id, body.by, body.note, db)
    if not a:
        raise HTTPException(404, "alert not found")
    return alert_engine.serialize(a)


@app.get("/api/blocked")
def get_blocked(db: Session = Depends(get_db)):
    rows = db.query(BlockedIP).filter(BlockedIP.status.in_(["ACTIVE", "RECOMMENDED"])).order_by(BlockedIP.blocked_at.desc()).all()
    f2b = monitor_registry.get("Fail2banSync", {}).get("instance")
    return {
        "fail2ban": {
            "health": getattr(f2b, "health", "unknown"),
            "reason": getattr(f2b, "health_reason", ""),
            "fix_hint": getattr(f2b, "fix_hint", ""),
            "jail": config.FAIL2BAN_JAIL,
            "stats": getattr(f2b, "stats", {}),
        },
        "items": [_blocked_dict(b) for b in rows],
    }


class BanBody(BaseModel):
    ip: str
    reason: str = "manual block from dashboard"


@app.post("/api/blocked")
def block_ip(body: BanBody, db: Session = Depends(get_db)):
    try:
        ipaddress.ip_address(body.ip)
    except ValueError:
        raise HTTPException(400, "invalid ip")
    result = BanManager(db).ban_ip(body.ip, body.reason)
    return {"ip": body.ip, **result}


@app.post("/api/blocked/{ip_address}/unblock")
def unblock_ip(ip_address: str, db: Session = Depends(get_db)):
    try:
        ipaddress.ip_address(ip_address)
    except ValueError:
        raise HTTPException(400, "invalid ip")
    ok, msg = BanManager(db).unblock_ip(ip_address)
    if not ok:
        raise HTTPException(409, msg)
    return {"status": "success", "message": msg}


@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    since = utcnow() - timedelta(hours=24)
    base = db.query(Event).filter(Event.timestamp >= since, Event.is_simulation == False, Event.event_type != "THREAT_INTEL")  # noqa: E712
    defcon = defcon_watcher.current if defcon_watcher.prev is not None else alert_engine.compute_defcon(db)
    degraded = [m["instance"].label for m in monitor_registry.values() if m["instance"].health in ("degraded", "down")]
    return {
        **defcon,
        "events_24h": base.count(),
        "critical_24h": base.filter(Event.severity == "CRITICAL").count(),
        "warning_24h": base.filter(Event.severity == "WARNING").count(),
        "degraded_monitors": degraded,
        **_resource_cache,
    }


@app.get("/api/stats/timeline")
def get_stats_timeline(db: Session = Depends(get_db)):
    now = utcnow()
    start = now - timedelta(hours=24)
    rows = db.query(Event.timestamp, Event.severity).filter(
        Event.timestamp >= start, Event.event_type != "THREAT_INTEL", Event.is_simulation == False,  # noqa: E712
    ).all()
    buckets = [{"hour": (start + timedelta(hours=i)).strftime("%H:00"), "critical": 0, "warning": 0, "info": 0} for i in range(24)]
    for ts, sev in rows:
        if not ts:
            continue
        idx = int((ts - start).total_seconds() // 3600)
        if 0 <= idx < 24:
            key = (sev or "INFO").lower()
            buckets[idx][key if key in ("critical", "warning") else "info"] += 1
    return buckets


@app.get("/api/monitors")
def get_monitors():
    out = []
    for name, info in monitor_registry.items():
        d = info["instance"].status_dict()
        d["thread_alive"] = info["thread"].is_alive()
        if not d["thread_alive"] and d["health"] not in ("down",):
            d["health"], d["health_reason"] = "down", d.get("health_reason") or "스레드 종료됨"
        out.append(d)
    return out


@app.get("/api/host")
def get_host():
    def readable(p):
        try:
            with open(p, "rb"):
                return True
        except Exception:
            return False
    f2b = monitor_registry.get("Fail2banSync", {}).get("instance")
    ok, why, hint = (f2b.health == "ok", f2b.health_reason, f2b.fix_hint) if f2b else Fail2banClient().availability()
    upd = monitor_registry.get("UpdateMonitor", {}).get("instance")
    return {
        "hostname": socket.gethostname(),
        "os": platform.platform(),
        "kernel": platform.release(),
        "uptime_hours": round((time.time() - psutil.boot_time()) / 3600, 1),
        "dashboard_started_at": _started_at.isoformat(),
        "running_as": {"uid": os.geteuid(), "user": os.environ.get("USER", ""), "root": os.geteuid() == 0},
        "privileges": {
            "auth_log_readable": readable(config.AUTH_LOG_PATH),
            "shadow_readable": readable("/etc/shadow"),
            "fail2ban_control": ok,
            "fail2ban_reason": why,
            "fail2ban_hint": hint,
        },
        "pending_updates": getattr(upd, "pending", {}),
        "usb_storage": kmod.usb_storage_status(),
        "blocked_modules": kmod.blocked_modules(),
        "api_token_file": str(config.API_TOKEN_FILE),
    }


@app.get("/api/hardening")
def get_hardening():
    """Lynis 감사 결과: 강화 지수, 경고, 제안(강화 작업 목록)."""
    inst = monitor_registry.get("LynisMonitor", {}).get("instance")
    if not inst:
        return {"available": False, "health": "down", "health_reason": "LynisMonitor 미기동"}
    return inst.status_payload()


@app.get("/api/summary/korean")
def get_korean_summary(db: Session = Depends(get_db)):
    defcon = alert_engine.compute_defcon(db)
    since = utcnow() - timedelta(hours=24)
    parts = []
    if defcon["open_critical"]:
        parts.append(f"긴급: 미확인 CRITICAL 알림이 {defcon['open_critical']}건 있습니다. 가장 최근 항목은 '{defcon['reason']}' 입니다.")
    elif defcon["open_warning"]:
        parts.append(f"주의: 미확인 경고 알림이 {defcon['open_warning']}건 있습니다. 가장 최근 항목은 '{defcon['reason']}' 입니다.")
    else:
        parts.append("미확인 알림이 없습니다. 최근 24시간 동안 대응이 필요한 사건은 없었습니다.")
    if defcon["acked"]:
        parts.append(f"확인 처리되어 진행 중인 알림 {defcon['acked']}건이 있습니다.")

    degraded = [(m["instance"].label, m["instance"].health_reason) for m in monitor_registry.values() if m["instance"].health in ("degraded", "down")]
    if degraded:
        parts.append("탐지 공백: " + "; ".join(f"{l} — {r}" for l, r in degraded[:3]) + ". 모니터 상태 패널의 해결 방법을 참고하세요.")

    fails = db.query(Event).filter(Event.timestamp >= since, Event.event_type.in_(["AUTH_FAILURE", "INVALID_USER"]), Event.is_simulation == False).count()  # noqa: E712
    logins = db.query(Event).filter(Event.timestamp >= since, Event.event_type == "AUTH_SUCCESS", Event.is_simulation == False).count()  # noqa: E712
    blocked = db.query(BlockedIP).filter(BlockedIP.status == "ACTIVE").count()
    recommended = db.query(BlockedIP).filter(BlockedIP.status == "RECOMMENDED").count()
    parts.append(f"최근 24시간 SSH 로그인 실패 {fails}건, 성공 {logins}건. 현재 fail2ban 차단 IP {blocked}개" + (f", 차단 권고 {recommended}개" if recommended else "") + ".")

    upd = monitor_registry.get("UpdateMonitor", {}).get("instance")
    pending = getattr(upd, "pending", {}) or {}
    if pending.get("available"):
        if pending.get("security"):
            parts.append(f"보안 업데이트 {pending['security']}건이 미적용 상태입니다.")
        else:
            parts.append("미적용 보안 업데이트는 없습니다.")
    lynis = monitor_registry.get("LynisMonitor", {}).get("instance")
    latest = getattr(lynis, "latest", None) or {}
    if latest.get("hardening_index"):
        parts.append(f"Lynis 강화 지수 {latest['hardening_index']}, 미해결 경고 {len(latest.get('warnings', []))}건, 강화 제안 {len(latest.get('suggestions', []))}건.")
    usn = db.query(Alert).filter(Alert.rule == "usn_affects_host", Alert.status.in_(["OPEN", "ACKED"])).count()
    if usn:
        parts.append(f"이 서버의 설치 패키지에 영향을 주는 Ubuntu 보안 공지 {usn}건이 있습니다.")
    return {"highlight": " ".join(parts), "defcon": defcon}


# --- 프론트엔드 정적 서빙 (빌드 결과가 있을 때) -------------------------------
if config.FRONTEND_DIST.exists() and (config.FRONTEND_DIST / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIST), html=True), name="frontend")
else:
    @app.get("/")
    def read_root():
        return {"status": "Security Dashboard running", "frontend": "not built (run: cd frontend && npm run build)"}


if __name__ == "__main__":
    uvicorn.run(app, host=config.HOST, port=config.PORT)
