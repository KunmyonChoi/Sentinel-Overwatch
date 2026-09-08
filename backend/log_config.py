"""
로그 파일 구조 설계
====================

목적: Claude Code 등 도구로 직접 분석 가능한 구조

디렉터리 레이아웃:
  logs/
  ├── security.log              # 전체 통합 로그 (현재 날짜, 항상 최신)
  ├── security.log.2026-04-01   # 날짜별 로테이션 보관 (30일)
  ├── critical.log              # CRITICAL 이벤트만 별도 기록 (영구 보관)
  └── daily/
      └── 2026-04-02.log        # 날짜별 스냅샷 (분석용)

파일명 규칙:
  - security.log        : 전체 통합 (tail -f, 실시간 모니터링용)
  - critical.log        : CRITICAL만 (사고 분석, 감사 추적용)
  - daily/YYYY-MM-DD.log: 날짜별 전체 (특정 날 이벤트 분석용)

로그 포맷:
  2026-04-02 16:45:01 | CRITICAL  | malware_monitor      | Suspicious process detected: nmap (PID: 1234)
  ──────────────────   ─────────   ────────────────────   ─────────────────────────────────────────────
  timestamp            level       module(monitor 이름)   message

분석 예시 (Claude Code에서):
  - Read("logs/critical.log")                    → 전체 위협 이력
  - Read("logs/daily/2026-04-02.log")            → 특정일 전체 이벤트
  - Grep("MALWARE", "logs/security.log")         → 악성코드 이벤트만
  - Grep("intrusion_monitor", "logs/security.log") → 침입 탐지만
"""

import logging
import logging.handlers
import os
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
DAILY_DIR = os.path.join(LOG_DIR, "daily")

_configured = False

FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
DATEFMT = "%Y-%m-%d %H:%M:%S"


class CriticalFileHandler(logging.FileHandler):
    """CRITICAL 레벨 이벤트만 기록하는 핸들러."""
    def emit(self, record):
        if record.levelno >= logging.CRITICAL:
            super().emit(record)


class DailySnapshotHandler(logging.handlers.BaseRotatingHandler):
    """날짜가 바뀔 때 daily/YYYY-MM-DD.log 로 자동 전환하는 핸들러."""
    def __init__(self):
        self._current_date = self._today()
        path = os.path.join(DAILY_DIR, f"{self._current_date}.log")
        super().__init__(path, mode="a", encoding="utf-8")

    def _today(self):
        return datetime.now().strftime("%Y-%m-%d")

    def shouldRollover(self, record):
        return self._today() != self._current_date

    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        self._current_date = self._today()
        self.baseFilename = os.path.join(DAILY_DIR, f"{self._current_date}.log")
        self.stream = self._open()


def setup_logging():
    global _configured
    if _configured:
        return
    _configured = True

    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(DAILY_DIR, exist_ok=True)

    fmt = logging.Formatter(fmt=FORMAT, datefmt=DATEFMT)

    # 1. 전체 통합 로그 (일별 로테이션, 30일 보관)
    main_handler = logging.handlers.TimedRotatingFileHandler(
        os.path.join(LOG_DIR, "security.log"),
        when="midnight", interval=1, backupCount=30, encoding="utf-8",
    )
    main_handler.setFormatter(fmt)
    main_handler.setLevel(logging.INFO)

    # 2. CRITICAL 전용 로그 (로테이션 없이 영구 누적)
    critical_handler = CriticalFileHandler(
        os.path.join(LOG_DIR, "critical.log"), encoding="utf-8"
    )
    critical_handler.setFormatter(fmt)

    # 3. 날짜별 스냅샷 (daily/YYYY-MM-DD.log)
    daily_handler = DailySnapshotHandler()
    daily_handler.setFormatter(fmt)
    daily_handler.setLevel(logging.INFO)

    # 4. 콘솔 출력
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    console_handler.setLevel(logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in (main_handler, critical_handler, daily_handler, console_handler):
        root.addHandler(handler)
