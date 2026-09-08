"""
모든 모니터의 공통 기반.

핵심 원칙: 조용히 실패하지 않는다.
데이터 소스를 읽을 수 없으면 health 를 'down' 또는 'degraded' 로 바꾸고
운영자가 고칠 수 있는 힌트(fix_hint)를 함께 노출한다.
"""
import json
import logging
import threading
import time
from datetime import datetime

from database import Event, SessionLocal, utcnow
import korean

logger = logging.getLogger("monitor")


class BaseMonitor:
    name = "BaseMonitor"
    label = "기본 모니터"
    interval = 30

    def __init__(self, interval: int | None = None):
        if interval is not None:
            self.interval = interval
        self.running = False
        self.last_started: datetime | None = None
        self.last_check_at: datetime | None = None
        self.last_event_at: datetime | None = None
        self.health = "starting"          # starting / ok / degraded / down
        self.health_reason = ""
        self.fix_hint = ""
        self.source = ""                  # 사람이 읽을 데이터 소스 설명
        self._stop = threading.Event()
        self.log = logging.getLogger(self.__class__.__name__)

    # --- 서브클래스가 구현 ---
    def setup(self) -> None:
        """시작 시 1회. 데이터 소스 접근 확인과 기준선 구축."""

    def tick(self) -> None:
        """주기적으로 호출."""

    # --- 공통 루프 ---
    def monitor(self):
        self.running = True
        self.last_started = utcnow()
        try:
            self.setup()
        except Exception as e:
            self.set_health("down", f"초기화 실패: {e}")
            self.log.exception("setup failed")
            self.running = False
            return
        if self.health == "starting":
            self.set_health("ok")
        while self.running and not self._stop.is_set():
            try:
                self.tick()
            except Exception as e:
                self.log.exception("tick failed")
                self.set_health("degraded", f"주기 점검 오류: {e}")
            self.last_check_at = utcnow()
            self._stop.wait(self.interval)
        self.running = False

    def stop(self):
        self.running = False
        self._stop.set()

    def set_health(self, status: str, reason: str = "", hint: str = ""):
        changed = (status, reason) != (self.health, self.health_reason)
        self.health, self.health_reason, self.fix_hint = status, reason, hint
        if changed and status in ("degraded", "down"):
            self.log.warning(f"health={status}: {reason} {('(' + hint + ')') if hint else ''}")

    def status_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "running": self.running,
            "health": self.health,
            "health_reason": self.health_reason,
            "fix_hint": self.fix_hint,
            "source": self.source,
            "interval": self.interval,
            "started_at": self.last_started.isoformat() if self.last_started else None,
            "last_check_at": self.last_check_at.isoformat() if self.last_check_at else None,
            "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None,
        }

    # --- 이벤트 기록 ---
    def log_event(
        self,
        event_type: str,
        severity: str,
        description: str,
        details: dict | None = None,
        description_ko: str | None = None,
        is_simulation: bool = False,
        source: str | None = None,
    ):
        if description_ko is None:
            description_ko = korean.event_ko(event_type, details)
        level = logging.CRITICAL if severity == "CRITICAL" else logging.WARNING if severity == "WARNING" else logging.INFO
        self.log.log(level, f"{event_type}: {description}")
        db = SessionLocal()
        try:
            db.add(Event(
                event_type=event_type,
                severity=severity,
                source=source or self.name,
                description=description,
                description_ko=description_ko,
                details=json.dumps(details, ensure_ascii=False) if details else None,
                is_simulation=is_simulation,
            ))
            db.commit()
            self.last_event_at = utcnow()
        except Exception as e:
            db.rollback()
            self.log.error(f"DB error: {e}")
        finally:
            db.close()


class TailReader:
    """로그 파일을 tail -f 처럼 읽는다. 로테이션/절단을 감지해 다시 연다."""

    def __init__(self, path: str):
        self.path = path
        self._fh = None
        self._inode = None

    def open(self, seek_end: bool = True):
        self.close()
        self._fh = open(self.path, "r", encoding="utf-8", errors="replace")
        import os
        st = os.fstat(self._fh.fileno())
        self._inode = st.st_ino
        if seek_end:
            self._fh.seek(0, 2)

    def close(self):
        if self._fh:
            try:
                self._fh.close()
            except Exception:
                pass
        self._fh = None

    def _rotated(self) -> bool:
        import os
        try:
            st = os.stat(self.path)
        except FileNotFoundError:
            return False
        if st.st_ino != self._inode:
            return True
        try:
            return st.st_size < self._fh.tell()
        except Exception:
            return False

    def readline(self) -> str:
        if not self._fh:
            self.open()
        line = self._fh.readline()
        if line:
            return line
        if self._rotated():
            try:
                self.open(seek_end=False)
            except FileNotFoundError:
                pass
        return ""
