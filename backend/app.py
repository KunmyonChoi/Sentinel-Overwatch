from log_config import setup_logging
setup_logging()

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import threading
import uvicorn
import database
from database import get_db, Event, DailyReport, init_db
from monitor.intrusion import AuthLogWatcher, NetworkWatcher
from monitor.malware import MalwareMonitor
from monitor.intel import IntelMonitor
from monitor.resource import ResourceMonitor
from monitor.integrity import IntegrityMonitor
from monitor.update import UpdateMonitor
import time
from datetime import datetime, timedelta
import os
import json
from deep_translator import GoogleTranslator
import anthropic as _anthropic

_ko_cache: dict[str, str | None] = {}      # None = in progress, "" = failed, str = done
_urgency_cache: dict[str, str] = {}         # "" = unknown, "CRITICAL"/"HIGH"/"MEDIUM"/"LOW"

_URGENCY_PROMPT = """\
You are a cybersecurity analyst. Given the title/description of a threat intelligence article, do two things:
1. Translate the text to Korean.
2. Rate the **security urgency** for a system administrator as one of: CRITICAL, HIGH, MEDIUM, LOW.
   - CRITICAL: zero-day exploit, actively exploited vulnerability in the wild, major ransomware campaign
   - HIGH: new CVE (CVSS ≥ 8), confirmed data breach, active targeted attack campaign
   - MEDIUM: patch/update advisory, general threat report, new malware family (not yet widespread)
   - LOW: general security awareness, research, informational news

Respond ONLY with valid JSON (no markdown):
{"translation": "<Korean translation>", "urgency": "<CRITICAL|HIGH|MEDIUM|LOW>", "urgency_reason": "<one sentence in Korean>"}

Article text:
{text}"""

def _load_translation_cache():
    """Load persisted translations and urgency ratings from DB into memory on startup."""
    db = database.SessionLocal()
    try:
        rows = db.query(database.TranslationCache).all()
        for row in rows:
            _ko_cache[row.source_text] = row.translated_text
            if row.urgency:
                _urgency_cache[row.source_text] = row.urgency
    except Exception:
        pass
    finally:
        db.close()

def _persist_translation(source_text: str, translated_text: str, urgency: str = ""):
    """Upsert a translation + urgency result into the DB."""
    db = database.SessionLocal()
    try:
        row = db.query(database.TranslationCache).filter(
            database.TranslationCache.source_text == source_text
        ).first()
        if row:
            row.translated_text = translated_text
            if urgency:
                row.urgency = urgency
        else:
            db.add(database.TranslationCache(source_text=source_text, translated_text=translated_text, urgency=urgency or None))
        db.commit()
    except Exception:
        pass
    finally:
        db.close()

# Resource metrics cache — updated every 10s in background to avoid blocking API
_resource_cache: dict = {"cpu_percent": 0.0, "mem_used_gb": 0.0, "mem_total_gb": 0.0, "mem_percent": 0.0, "disk_percent": 0.0}

def _update_resource_cache():
    import psutil
    while True:
        try:
            cpu = psutil.cpu_percent(interval=3)   # blocking 3s, but in background thread
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            _resource_cache.update({
                "cpu_percent": cpu,
                "mem_used_gb": round(mem.used / (1024 ** 3), 1),
                "mem_total_gb": round(mem.total / (1024 ** 3), 1),
                "mem_percent": mem.percent,
                "disk_percent": disk.percent,
            })
        except Exception:
            pass
        time.sleep(7)  # update every ~10s (3s measure + 7s sleep)

def _do_translate(clean: str, is_intel: bool = False) -> None:
    """Translate text. For intel articles, also evaluate urgency via Claude API."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if is_intel and api_key:
        try:
            client = _anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                messages=[{"role": "user", "content": _URGENCY_PROMPT.format(text=clean[:600])}],
            )
            data = json.loads(msg.content[0].text)
            translation = data.get("translation") or ""
            urgency = data.get("urgency", "MEDIUM")
            urgency_reason = data.get("urgency_reason", "")
            display = translation
            if urgency_reason:
                display = f"{translation} [{urgency_reason}]"
            _ko_cache[clean] = display
            _urgency_cache[clean] = urgency
            if display:
                _persist_translation(clean, display, urgency)
            return
        except Exception:
            pass  # fall through to Google Translate

    # Fallback: Google Translate (no urgency)
    try:
        translated = GoogleTranslator(source='en', target='ko').translate(clean[:500])
        result = translated or ""
        _ko_cache[clean] = result
        if result:
            _persist_translation(clean, result)
    except Exception:
        _ko_cache[clean] = ""

def _translate_ko(text: str, is_intel: bool = False) -> str | None:
    """Returns None while translating, "" on failure, Korean string on success."""
    if not text:
        return ""
    clean = text.replace('[SIMULATION]', '').strip()
    if clean in _ko_cache:
        return _ko_cache[clean]
    # Mark as in-progress and translate in background
    _ko_cache[clean] = None
    threading.Thread(target=_do_translate, args=(clean, is_intel), daemon=True).start()
    return None

from contextlib import asynccontextmanager

# Monitor registry: {name: {"instance": ..., "label": ...}}
monitor_registry: dict[str, dict] = {}

def _start_monitor(name: str, label: str, instance, registry: dict, monitor_list: list):
    instance.last_started = datetime.utcnow()
    t = threading.Thread(target=instance.monitor, daemon=True, name=name)
    t.start()
    monitor_list.append(instance)
    registry[name] = {"instance": instance, "label": label, "thread": t}

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        _load_translation_cache()
        _start_monitor("AuthLogWatcher",   "SSH/Auth 침입 탐지",   AuthLogWatcher(),   monitor_registry, monitors)
        _start_monitor("NetworkWatcher",   "네트워크 연결 감시",    NetworkWatcher(),   monitor_registry, monitors)
        _start_monitor("MalwareMonitor",   "악성 프로세스 스캔",    MalwareMonitor(),   monitor_registry, monitors)
        _start_monitor("IntelMonitor",     "위협 인텔 RSS 수집",    IntelMonitor(),     monitor_registry, monitors)
        _start_monitor("ResourceMonitor",  "시스템 리소스 감시",    ResourceMonitor(),  monitor_registry, monitors)
        _start_monitor("IntegrityMonitor", "파일 무결성 감시",      IntegrityMonitor(), monitor_registry, monitors)
        _start_monitor("UpdateMonitor",    "소프트웨어 업데이트 감시", UpdateMonitor(),    monitor_registry, monitors)
        threading.Thread(target=_update_resource_cache, daemon=True, name="ResourceCache").start()
        print("All monitors started.")
    except Exception as e:
        print(f"Error starting monitors: {e}")

    yield

    for monitor in monitors:
        monitor.running = False
    print("Monitors stopping...")

app = FastAPI(title="Security Monitor", lifespan=lifespan)
database.init_db()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Vite dev server only
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Global Monitors (Start on startup)
monitors = []

from ban_manager import BanManager
from notifications import send_slack_alert

_prev_defcon: str | None = None  # track DEFCON level changes for alerting

def _check_and_notify(status: str, reason: str):
    """Send Slack when DEFCON level changes to a worse state."""
    global _prev_defcon
    if status != _prev_defcon:
        if status in ("DEFCON 1", "DEFCON 3"):
            color = "#ff0000" if status == "DEFCON 1" else "#ffaa00"
            send_slack_alert(
                title=f"🚨 {status} DECLARED",
                message=reason,
                color=color,
            )
        _prev_defcon = status

@app.get("/")
def read_root():
    return {"status": "Security Monitor Running"}

@app.get("/api/intel")
def get_intel(limit: int = 20, db: Session = Depends(database.get_db)):
    events = db.query(database.Event).filter(
        database.Event.event_type == "THREAT_INTEL"
    ).order_by(database.Event.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": e.id,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "event_type": e.event_type,
            "severity": e.severity,
            "source": e.source,
            "description": e.description,
            "description_ko": _translate_ko(e.description, is_intel=True),
            "urgency": _urgency_cache.get(e.description.replace('[SIMULATION]', '').strip(), ""),
            "details": e.details,
        }
        for e in events
    ]

@app.get("/api/events")
def get_events(limit: int = 50, db: Session = Depends(database.get_db)):
    events = db.query(database.Event).filter(
        database.Event.event_type != "THREAT_INTEL"
    ).order_by(database.Event.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": e.id,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "event_type": e.event_type,
            "severity": e.severity,
            "source": e.source,
            "description": e.description,
            "description_ko": _translate_ko(e.description),
            "details": e.details,
        }
        for e in events
    ]

@app.get("/api/blocked")
def get_blocked_ips(db: Session = Depends(database.get_db)):
    ips = db.query(database.BlockedIP).filter(database.BlockedIP.status == "ACTIVE").order_by(database.BlockedIP.blocked_at.desc()).all()
    return ips

@app.post("/api/unblock/{ip_address}")
def unblock_ip(ip_address: str, db: Session = Depends(database.get_db)):
    manager = BanManager(db)
    success = manager.unblock_ip(ip_address)
    if success:
        return {"status": "success", "message": f"IP {ip_address} unblocked"}
    return {"status": "error", "message": "IP not found or already unblocked"}


@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    total_events = db.query(Event).count()
    since_24h = datetime.utcnow() - timedelta(hours=24)
    critical_events = db.query(Event).filter(
        Event.severity == 'CRITICAL',
        Event.timestamp >= since_24h,
        ~Event.description.contains('[SIMULATION]')
    ).count()
    warning_events = db.query(Event).filter(
        Event.severity == 'WARNING',
        Event.timestamp >= since_24h,
        ~Event.description.contains('[SIMULATION]')
    ).count()

    # Use cached resource metrics (updated every ~10s in background)
    cpu_percent = _resource_cache["cpu_percent"]
    mem_used_gb = _resource_cache["mem_used_gb"]
    mem_total_gb = _resource_cache["mem_total_gb"]
    mem_percent = _resource_cache["mem_percent"]
    disk_percent = _resource_cache["disk_percent"]

    # Determine Status and Action
    status = "SAFE"
    reason = "System Normal"
    action = "Monitor systems."

    if critical_events > 0:
        status = "DEFCON 1"
        latest_critical = db.query(Event).filter(
            Event.severity == 'CRITICAL',
            ~Event.description.contains('[SIMULATION]')
        ).order_by(Event.timestamp.desc()).first()
        if latest_critical:
            if "MALWARE" in latest_critical.event_type:
                reason = f"Active Malware: {latest_critical.description}"
                action = "Isolate host. Terminate process immediately."
            elif "FILE_INTEGRITY" in latest_critical.event_type:
                reason = f"File Integrity Violation: {latest_critical.description}"
                action = "Inspect modified files immediately."
            else:
                reason = f"Critical Alert: {latest_critical.description}"
                action = "Investigate logs immediately."
    elif warning_events > 5:
        status = "DEFCON 3"
        reason = "High volume of warning events (Intrusion Attempts)"
        action = "Check firewall rules. Verify Block List."
    elif cpu_percent > 90:
        status = "DEFCON 3"
        reason = f"CPU usage critical: {cpu_percent}%"
        action = "Check running processes for anomalies."
    elif mem_percent > 85:
        status = "DEFCON 3"
        reason = f"Memory usage critical: {mem_percent}%"
        action = "Check for memory leaks or crypto miners."

    _check_and_notify(status, reason)

    return {
        "total": total_events,
        "critical": critical_events,
        "warning": warning_events,
        "status": status,
        "reason": reason,
        "action": action,
        "cpu_percent": cpu_percent,
        "mem_used_gb": mem_used_gb,
        "mem_total_gb": mem_total_gb,
        "mem_percent": mem_percent,
        "disk_percent": disk_percent,
    }


@app.get("/api/stats/timeline")
def get_stats_timeline(db: Session = Depends(get_db)):
    """Return hourly event counts for the last 24 hours (CRITICAL/WARNING/INFO)."""
    now = datetime.utcnow()
    start = now - timedelta(hours=24)

    events = db.query(Event).filter(
        Event.timestamp >= start,
        Event.event_type != "THREAT_INTEL",
        ~Event.description.contains('[SIMULATION]'),
    ).all()

    # Build 24 hourly buckets
    buckets: list[dict] = []
    for i in range(24):
        h = start + timedelta(hours=i)
        buckets.append({
            "hour": h.strftime("%H:00"),
            "critical": 0,
            "warning": 0,
            "info": 0,
        })

    for e in events:
        if not e.timestamp:
            continue
        idx = int((e.timestamp - start).total_seconds() // 3600)
        if 0 <= idx < 24:
            sev = (e.severity or "INFO").upper()
            if sev == "CRITICAL":
                buckets[idx]["critical"] += 1
            elif sev == "WARNING":
                buckets[idx]["warning"] += 1
            else:
                buckets[idx]["info"] += 1

    return buckets


@app.get("/api/monitors")
def get_monitors():
    result = []
    for name, info in monitor_registry.items():
        inst = info["instance"]
        thread = info["thread"]
        result.append({
            "name": name,
            "label": info["label"],
            "running": getattr(inst, "running", False),
            "thread_alive": thread.is_alive(),
            "started_at": inst.last_started.isoformat() if hasattr(inst, "last_started") else None,
        })
    return result

@app.get("/api/highlight/korean")
def get_korean_highlight(db: Session = Depends(get_db)):
    critical_events = db.query(Event).filter(Event.severity == 'CRITICAL').count()
    warning_events = db.query(Event).filter(Event.severity == 'WARNING').count()
    intel_events = db.query(Event).filter(Event.event_type == 'THREAT_INTEL').count()
    
    if critical_events > 0:
        highlight = f"긴급: 총 {critical_events}건의 심각한(CRITICAL) 시스템 보안 위협이 라이브 피드에 감지되었습니다! 즉각적인 확인이 필요합니다."
    elif warning_events > 0:
        highlight = f"주의: 라이브 피드에 의심스러운 접근 시도 등 {warning_events}건의 경고(WARNING) 기록이 있습니다. 주의 깊게 시스템을 주시해 주시기 바랍니다."
    else:
        highlight = "라이브 피드 확인 결과 시스템은 매우 안정적입니다. 심각한 위협이나 경고가 없습니다."
        
    if intel_events > 0:
        highlight += f" 또한, 위협 인텔(Threat Intel)을 통해 {intel_events}건의 관련된 글로벌 보안 뉴스와 취약점 정보가 수집되었습니다. 우측 피드를 통해 최신 위협 동향을 파악할 수 있습니다."
    else:
        highlight += " 현재 수집된 새로운 위협 인텔 정보는 없습니다."

    update_events = db.query(Event).filter(Event.event_type == 'SOFTWARE_UPDATE').count()
    if update_events > 0:
        removed = db.query(Event).filter(
            Event.event_type == 'SOFTWARE_UPDATE', Event.severity == 'WARNING'
        ).count()
        highlight += f" 소프트웨어 업데이트 {update_events}건이 기록되었습니다."
        if removed > 0:
            highlight += f" (패키지 제거 {removed}건 포함 — 확인 필요)"

    return {"highlight": highlight}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
