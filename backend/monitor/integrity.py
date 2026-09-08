import hashlib
import logging
import time
import os
from pathlib import Path
from database import SessionLocal, Event
from notifications import notify_critical_event

logger = logging.getLogger("integrity_monitor")

WATCH_PATHS = [
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
    "/etc/ssh/sshd_config",
    str(Path.home() / ".ssh" / "authorized_keys"),
]


def _sha256(path: str) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except FileNotFoundError:
        return None
    except PermissionError:
        return "PERMISSION_DENIED"
    except Exception as e:
        logger.error(f"Hash error for {path}: {e}")
        return None


class IntegrityMonitor:
    def __init__(self, interval=60):
        self.interval = interval
        self.running = False
        self.baselines: dict[str, str | None] = {}

    def monitor(self):
        self.running = True
        logger.info("Starting Integrity Monitor")
        self._build_baseline()
        while self.running:
            time.sleep(self.interval)
            self.check_integrity()

    def _build_baseline(self):
        for path in WATCH_PATHS:
            self.baselines[path] = _sha256(path)
            status = "ok" if self.baselines[path] else "not found"
            logger.info(f"Baseline [{status}]: {path}")

    def check_integrity(self):
        for path in WATCH_PATHS:
            current = _sha256(path)
            baseline = self.baselines.get(path)

            if baseline is None and current is None:
                continue  # file didn't exist at baseline and still doesn't

            if baseline is None and current is not None:
                # File appeared after baseline
                self.log_event(path, f"New file detected (was absent at startup): {path}")
                self.baselines[path] = current
            elif current is None and baseline is not None:
                # File was deleted
                self.log_event(path, f"Watched file deleted: {path}")
                self.baselines[path] = None
            elif current != baseline:
                # File content changed
                self.log_event(path, f"File integrity violation: {path} has been modified.")
                self.baselines[path] = current  # Update baseline to avoid repeat alerts

    def log_event(self, path: str, description: str):
        logger.critical(description)
        notify_critical_event("FILE_INTEGRITY", description)
        db = SessionLocal()
        try:
            db.add(Event(
                event_type="FILE_INTEGRITY",
                severity="CRITICAL",
                source="IntegrityMonitor",
                description=description,
            ))
            db.commit()
        except Exception as e:
            logger.error(f"Database error: {e}")
        finally:
            db.close()
