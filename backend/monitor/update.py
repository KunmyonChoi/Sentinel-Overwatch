import logging
import time
import re
from database import SessionLocal, Event

logger = logging.getLogger("update_monitor")

# dpkg.log action keywords to track
TRACK_ACTIONS = {"install", "upgrade", "remove", "purge"}

# dpkg.log line format:
# 2026-04-01 14:23:34 upgrade coreutils:amd64 9.4-3ubuntu6.1 9.4-3ubuntu6.2
LINE_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})\s+(install|upgrade|remove|purge)\s+(\S+)\s+(.*)"
)


class UpdateMonitor:
    def __init__(self, log_path="/var/log/dpkg.log"):
        self.log_path = log_path
        self.running = False
        self.last_started = None

    def monitor(self):
        self.running = True
        logger.info(f"Starting Update Monitor on {self.log_path}")
        try:
            with open(self.log_path, "r") as f:
                # Seek to end — only watch new entries
                f.seek(0, 2)
                while self.running:
                    line = f.readline()
                    if not line:
                        time.sleep(2)
                        continue
                    self._process_line(line.strip())
        except FileNotFoundError:
            logger.warning(f"dpkg log not found: {self.log_path}")
        except PermissionError:
            logger.warning(f"Cannot read dpkg log (permission denied): {self.log_path}")
        except Exception as e:
            logger.error(f"Update monitor error: {e}")

    def _process_line(self, line: str):
        m = LINE_PATTERN.match(line)
        if not m:
            return

        timestamp, action, package, versions = m.groups()
        # Strip :amd64/:all etc for cleaner display
        pkg_name = package.split(":")[0]

        if action in ("remove", "purge"):
            severity = "WARNING"
            desc = f"Package {action}d: {pkg_name} ({versions.strip()})"
        elif action == "install":
            severity = "INFO"
            desc = f"Package installed: {pkg_name} {versions.strip()}"
        elif action == "upgrade":
            severity = "INFO"
            old, new = (versions.strip().split() + ["", ""])[:2]
            desc = f"Package upgraded: {pkg_name} {old} → {new}"
        else:
            return

        logger.info(desc)
        self._log_event(severity, desc)

    def _log_event(self, severity: str, description: str):
        db = SessionLocal()
        try:
            db.add(Event(
                event_type="SOFTWARE_UPDATE",
                severity=severity,
                source="UpdateMonitor",
                description=description,
            ))
            db.commit()
        except Exception as e:
            logger.error(f"Database error: {e}")
        finally:
            db.close()
