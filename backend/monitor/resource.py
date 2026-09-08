import psutil
import logging
import time
from database import SessionLocal, Event

logger = logging.getLogger("resource_monitor")

CPU_WARN_THRESHOLD = 90      # %
MEM_WARN_THRESHOLD = 85      # %
DISK_WARN_THRESHOLD = 90     # %
PROC_SPIKE_THRESHOLD = 50    # 이전 대비 프로세스 수 급증 기준


class ResourceMonitor:
    def __init__(self, interval=30):
        self.interval = interval
        self.running = False
        self.prev_proc_count = None
        # Consecutive high readings required before alerting (avoid transient spikes)
        self._cpu_high_count = 0
        self._mem_alerted = False
        self._disk_alerted = False

    def monitor(self):
        self.running = True
        logger.info("Starting Resource Monitor")
        # Warm-up read (first cpu_percent call always returns 0.0)
        psutil.cpu_percent(interval=None)
        time.sleep(1)
        while self.running:
            self.check_resources()
            time.sleep(self.interval)

    def check_resources(self):
        try:
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            proc_count = len(psutil.pids())

            # CPU sustained high usage (2 consecutive readings)
            if cpu > CPU_WARN_THRESHOLD:
                self._cpu_high_count += 1
                if self._cpu_high_count >= 2:
                    self.log_event(
                        "RESOURCE_ANOMALY", "WARNING", "ResourceMonitor",
                        f"Sustained high CPU usage: {cpu}% (threshold {CPU_WARN_THRESHOLD}%). Possible crypto miner or runaway process."
                    )
                    self._cpu_high_count = 0
            else:
                self._cpu_high_count = 0

            # Memory high usage (alert once, reset when drops below threshold)
            if mem.percent > MEM_WARN_THRESHOLD:
                if not self._mem_alerted:
                    self._mem_alerted = True
                    used_gb = round(mem.used / (1024 ** 3), 1)
                    total_gb = round(mem.total / (1024 ** 3), 1)
                    self.log_event(
                        "RESOURCE_ANOMALY", "WARNING", "ResourceMonitor",
                        f"High memory usage: {mem.percent}% ({used_gb}/{total_gb} GB). Investigate for leaks or malicious activity."
                    )
            else:
                self._mem_alerted = False

            # Disk high usage (alert once)
            if disk.percent > DISK_WARN_THRESHOLD:
                if not self._disk_alerted:
                    self._disk_alerted = True
                    self.log_event(
                        "RESOURCE_ANOMALY", "WARNING", "ResourceMonitor",
                        f"Disk usage critical: {disk.percent}% on /. Risk of service disruption."
                    )
            else:
                self._disk_alerted = False

            # Process count spike
            if self.prev_proc_count is not None:
                delta = proc_count - self.prev_proc_count
                if delta > PROC_SPIKE_THRESHOLD:
                    self.log_event(
                        "RESOURCE_ANOMALY", "WARNING", "ResourceMonitor",
                        f"Process count spiked by {delta} (now {proc_count}). Possible fork bomb or mass spawning."
                    )
            self.prev_proc_count = proc_count

        except Exception as e:
            logger.error(f"Resource check error: {e}")

    def log_event(self, event_type, severity, source, description):
        logger.warning(description)
        db = SessionLocal()
        try:
            db.add(Event(event_type=event_type, severity=severity, source=source, description=description))
            db.commit()
        except Exception as e:
            logger.error(f"Database error: {e}")
        finally:
            db.close()
