import shutil
import subprocess
import time

import psutil

from alerts import auto_resolve, raise_alert
from monitor.base import BaseMonitor

CPU_WARN_THRESHOLD = 90
MEM_WARN_THRESHOLD = 85
DISK_WARN_THRESHOLD = 90
PROC_SPIKE_THRESHOLD = 50


def time_synchronized() -> bool | None:
    """timedatectl 의 NTPSynchronized. 확인 불가(비 systemd 등)면 None."""
    if not shutil.which("timedatectl"):
        return None
    try:
        out = subprocess.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"], capture_output=True, text=True, timeout=5).stdout.strip().lower()
    except Exception:
        return None
    if out in ("yes", "no"):
        return out == "yes"
    return None


class ResourceMonitor(BaseMonitor):
    name = "ResourceMonitor"
    label = "시스템 리소스 감시"
    interval = 30

    def __init__(self, interval: int | None = None):
        super().__init__(interval)
        self.source = "psutil (cpu/mem/disk/pids)"
        self.prev_proc_count = None
        self._cpu_high_count = 0
        self._mem_alerted = False
        self._disk_alerted = False
        self._last_time_check = 0.0
        self.time_synced: bool | None = None

    def setup(self):
        psutil.cpu_percent(interval=None)

    def tick(self):
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        proc_count = len(psutil.pids())

        if cpu > CPU_WARN_THRESHOLD:
            self._cpu_high_count += 1
            if self._cpu_high_count >= 2:
                top = self._top_cpu()
                d = {"cpu": cpu, "top": top, "message_ko": f"CPU 사용률 {cpu}% 지속 (상위: {top})"}
                self.log_event("RESOURCE_ANOMALY", "WARNING", f"Sustained high CPU {cpu}% top={top}", d)
                raise_alert("high_cpu", "WARNING", f"Sustained high CPU: {cpu}%", fingerprint="high_cpu",
                            title_ko=f"CPU 사용률 {cpu}% 지속", summary_ko=f"상위 프로세스: {top}",
                            action_ko="`top -o %CPU` 로 프로세스를 확인하세요. 모르는 프로세스라면 실행 파일 경로(/proc/<pid>/exe)를 확인하고 크립토마이너 여부를 의심하세요.", details=d)
                self._cpu_high_count = 0
        else:
            self._cpu_high_count = 0
            auto_resolve("high_cpu")

        if mem.percent > MEM_WARN_THRESHOLD:
            if not self._mem_alerted:
                self._mem_alerted = True
                used_gb, total_gb = round(mem.used / 1024**3, 1), round(mem.total / 1024**3, 1)
                d = {"mem_percent": mem.percent, "message_ko": f"메모리 사용률 {mem.percent}% ({used_gb}/{total_gb} GB)"}
                self.log_event("RESOURCE_ANOMALY", "WARNING", f"High memory {mem.percent}% ({used_gb}/{total_gb} GB)", d)
                raise_alert("high_memory", "WARNING", f"High memory usage {mem.percent}%", fingerprint="high_memory",
                            title_ko=f"메모리 사용률 {mem.percent}%", summary_ko=f"{used_gb}/{total_gb} GB 사용 중",
                            action_ko="`ps aux --sort=-%mem | head` 로 원인 프로세스를 확인하세요.", details=d)
        else:
            if self._mem_alerted:
                auto_resolve("high_memory")
            self._mem_alerted = False

        if disk.percent > DISK_WARN_THRESHOLD:
            if not self._disk_alerted:
                self._disk_alerted = True
                d = {"disk_percent": disk.percent, "message_ko": f"루트 디스크 사용률 {disk.percent}%"}
                self.log_event("RESOURCE_ANOMALY", "WARNING", f"Disk usage {disk.percent}% on /", d)
                raise_alert("disk_full", "WARNING", f"Disk usage {disk.percent}% on /", fingerprint="disk_full",
                            title_ko=f"디스크 사용률 {disk.percent}% (/)", summary_ko="로그가 기록되지 못하면 탐지가 멈출 수 있습니다.",
                            action_ko="`sudo du -xh --max-depth=2 / | sort -h | tail` 로 큰 디렉터리를 찾아 정리하세요.", details=d)
        else:
            if self._disk_alerted:
                auto_resolve("disk_full")
            self._disk_alerted = False

        if self.prev_proc_count is not None:
            delta = proc_count - self.prev_proc_count
            if delta > PROC_SPIKE_THRESHOLD:
                d = {"delta": delta, "count": proc_count, "message_ko": f"프로세스 수 급증 +{delta} (현재 {proc_count})"}
                self.log_event("RESOURCE_ANOMALY", "WARNING", f"Process count spiked by {delta} (now {proc_count})", d)
                raise_alert("process_spike", "WARNING", f"Process count spiked by {delta}", fingerprint="process_spike",
                            title_ko=f"프로세스 수 급증: +{delta} (현재 {proc_count})", summary_ko="포크 폭탄이나 대량 생성 공격일 수 있습니다.",
                            action_ko="`ps -eo pid,ppid,user,comm --sort=-pid | head -60` 로 새로 생긴 프로세스를 확인하세요.", details=d)
        self.prev_proc_count = proc_count

        if time.time() - self._last_time_check >= 600:
            self._check_time_sync()

    def _check_time_sync(self):
        """시간 동기화 여부 (timedatectl). 로그·감사 타임스탬프의 신뢰성과 직결된다. Lynis TIME-3185 를 대체."""
        self._last_time_check = time.time()
        synced = time_synchronized()
        if synced is None:
            return
        self.time_synced = synced
        if synced:
            auto_resolve("time_unsynced", "시간 동기화 복구")
            return
        d = {"message_ko": "시스템 시간이 NTP 와 동기화되지 않음"}
        self.log_event("RESOURCE_ANOMALY", "WARNING", "System clock not NTP-synchronized", d)
        raise_alert("time_unsynced", "WARNING", "System clock not NTP-synchronized", fingerprint="time_unsynced",
                    title_ko="시스템 시간이 NTP 와 동기화되지 않음",
                    summary_ko="로그와 감사 기록의 시각이 어긋나면 사고 분석과 인증서 검증이 흔들립니다.",
                    action_ko="`timedatectl timesync-status` 로 서버 응답을 확인하고 `sudo systemctl restart systemd-timesyncd` 를 실행하세요. 방화벽에서 UDP 123 이 막혔는지도 확인하세요.",
                    details=d)

    @staticmethod
    def _top_cpu() -> str:
        try:
            procs = []
            for p in psutil.process_iter(["pid", "name", "cpu_percent"]):
                procs.append((p.info["cpu_percent"] or 0.0, p.info["name"], p.info["pid"]))
            procs.sort(reverse=True)
            return ", ".join(f"{n}({pid}) {c:.0f}%" for c, n, pid in procs[:3])
        except Exception:
            return "?"
