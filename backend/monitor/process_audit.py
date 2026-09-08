"""
프로세스 감사(ProcessAudit). 이전 MalwareMonitor 를 대체한다.

이름 부분 일치로 '악성코드' 라고 부르지 않는다. 두 종류로 나눈다.
  1) 도구 실행 감사 (WARNING): nmap, hydra 같은 공격/진단 도구의 실행. 실행 파일 이름 기준 정확 일치.
  2) 실제 지표 (CRITICAL/WARNING):
     - 셸 프로세스의 표준 입출력이 소켓에 연결됨 (리버스 셸 전형)
     - 실행 파일이 /tmp, /var/tmp, /dev/shm 등 임시 디렉터리에 있음
     - 실행 파일이 디스크에서 삭제됨 (업그레이드 후 재시작 필요일 수도 있어 INFO)
"""
import os

import psutil

from alerts import raise_alert
from monitor.base import BaseMonitor

TOOL_NAMES = {
    "nmap", "masscan", "zmap", "hydra", "medusa", "sqlmap", "nikto", "wpscan", "msfconsole", "msfvenom",
    "meterpreter", "mimikatz", "john", "hashcat", "aircrack-ng", "airodump-ng", "tcpdump", "wireshark", "tshark",
    "nc", "ncat", "netcat", "responder", "crackmapexec", "netexec", "impacket-smbclient", "chisel", "ligolo",
}
TMP_DIRS = ("/tmp/", "/var/tmp/", "/dev/shm/", "/run/shm/")
SHELLS = {"sh", "bash", "dash", "zsh", "ash", "ksh", "python", "python3", "perl", "php", "ruby", "socat"}
SIMULATION_SUFFIXES = ("_sim",)


def can_inspect_other_processes() -> bool:
    """root 소유 프로세스(PID 1)의 exe 와 fd 를 읽을 수 있으면 CAP_SYS_PTRACE 가 유효한 것이다."""
    if os.geteuid() == 0:
        return True
    try:
        os.readlink("/proc/1/exe")
        os.listdir("/proc/1/fd")
        return True
    except OSError:
        return False


def _fd_is_socket(pid: int, fd: int) -> bool:
    try:
        return os.readlink(f"/proc/{pid}/fd/{fd}").startswith("socket:")
    except OSError:
        return False


def inspect_process(proc: psutil.Process) -> dict | None:
    """프로세스 하나를 검사해 지표가 있으면 dict 를 반환한다."""
    with proc.oneshot():
        name = (proc.name() or "").lower()
        try:
            cmdline = proc.cmdline()
        except Exception:
            cmdline = []
        try:
            exe = proc.exe()
        except Exception:
            exe = ""
        try:
            user = proc.username()
        except Exception:
            user = "?"
        try:
            parent = proc.parent()
            parent_name = parent.name() if parent else "?"
        except Exception:
            parent_name = "?"
        try:
            cwd = proc.cwd()
        except Exception:
            cwd = "?"

    base_name = os.path.basename(cmdline[0]).lower() if cmdline else name
    is_sim = name.endswith(SIMULATION_SUFFIXES) or base_name.endswith(SIMULATION_SUFFIXES)
    clean = name.removesuffix("_sim") if is_sim else name
    clean_base = base_name.removesuffix("_sim") if is_sim else base_name
    info = {"pid": proc.pid, "name": name, "user": user, "exe": exe or (cmdline[0] if cmdline else ""),
            "cmdline": " ".join(cmdline)[:300], "parent": parent_name, "cwd": cwd, "simulation": is_sim}

    # 지표 1: 셸의 fd 0/1 이 소켓 → 리버스 셸
    if clean in SHELLS or clean_base in SHELLS:
        if _fd_is_socket(proc.pid, 0) and _fd_is_socket(proc.pid, 1):
            return info | {"kind": "indicator", "severity": "CRITICAL", "indicator": "shell_over_socket",
                           "indicator_ko": "셸의 표준 입출력이 네트워크 소켓에 연결됨 (리버스 셸 의심)"}

    # 지표 2: 임시 디렉터리에서 실행
    if exe and exe.startswith(TMP_DIRS):
        sev = "CRITICAL" if user == "root" else "WARNING"
        return info | {"kind": "indicator", "severity": sev, "indicator": "exec_from_tmp",
                       "indicator_ko": f"임시 디렉터리에서 실행 중인 바이너리 ({exe})"}

    # 지표 3: 실행 파일이 삭제됨
    if exe and exe.endswith("(deleted)"):
        return info | {"kind": "indicator", "severity": "INFO", "indicator": "exe_deleted",
                       "indicator_ko": "실행 파일이 디스크에서 삭제됨 (패키지 업그레이드 후 재시작 필요이거나, 흔적 제거 시도)"}

    # 도구 실행 감사
    if clean in TOOL_NAMES or clean_base in TOOL_NAMES:
        return info | {"kind": "tool", "severity": "WARNING", "tool": clean if clean in TOOL_NAMES else clean_base}
    return None


class ProcessAudit(BaseMonitor):
    name = "ProcessAudit"
    label = "프로세스 감사"
    interval = 30

    def __init__(self, interval: int | None = None):
        super().__init__(interval)
        self.source = "psutil.process_iter (/proc)"
        self.seen: set[int] = set()

    def setup(self):
        if not can_inspect_other_processes():
            self.set_health("degraded", "다른 사용자 프로세스의 실행 파일/파일 디스크립터를 읽을 수 없음",
                            "deploy/secdash.service 처럼 CAP_SYS_PTRACE + CAP_DAC_READ_SEARCH 를 부여하거나 root 로 실행하세요.")

    def tick(self):
        active: set[int] = set()
        for proc in psutil.process_iter():
            try:
                found = inspect_process(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception as e:
                self.log.debug(f"inspect failed pid={proc.pid}: {e}")
                continue
            if not found:
                continue
            active.add(proc.pid)
            if proc.pid in self.seen:
                continue
            self.seen.add(proc.pid)
            self._report(found)
        self.seen &= active

    def _report(self, f: dict):
        sim = f["simulation"]
        tag = " [SIMULATION]" if sim else ""
        if f["kind"] == "tool":
            d = {k: f[k] for k in ("pid", "name", "user", "exe", "cmdline", "parent", "cwd", "tool")}
            self.log_event("PROCESS_TOOL", "WARNING", f"Security tool '{f['tool']}' running (PID {f['pid']}, user {f['user']}, exe {f['exe']}){tag}", d, is_simulation=sim)
            raise_alert(
                "security_tool", "WARNING", f"Security tool running: {f['tool']} (PID {f['pid']})",
                fingerprint=f"security_tool:{f['tool']}:{f['user']}",
                title_ko=f"보안/공격 도구 '{f['tool']}' 실행 중 (사용자 {f['user']})",
                summary_ko=f"PID {f['pid']}, 부모 {f['parent']}, 실행 파일 {f['exe']}, 작업 디렉터리 {f['cwd']}",
                action_ko=f"관리자의 진단 작업이면 확인(ack) 처리하세요. 아니라면 `sudo kill -9 {f['pid']}` 로 종료하고 해당 계정의 최근 로그인(`last {f['user']}`)을 확인하세요.",
                evidence=f["cmdline"], details=d, is_simulation=sim,
            )
            return
        d = {k: f[k] for k in ("pid", "name", "user", "exe", "cmdline", "parent", "cwd", "indicator", "indicator_ko")}
        self.log_event("PROCESS_INDICATOR", f["severity"], f"{f['indicator']}: {f['name']} (PID {f['pid']}, user {f['user']}, exe {f['exe']}){tag}", d, is_simulation=sim)
        if f["severity"] == "INFO":
            return
        raise_alert(
            f"proc_{f['indicator']}", f["severity"], f"{f['indicator']}: {f['name']} (PID {f['pid']})",
            fingerprint=f"proc:{f['indicator']}:{f['exe']}:{f['user']}",
            title_ko=f"{f['indicator_ko']} — {f['name']} (사용자 {f['user']})",
            summary_ko=f"PID {f['pid']}, 부모 프로세스 {f['parent']}, 명령줄: {f['cmdline'][:120]}",
            action_ko=f"`sudo ls -l /proc/{f['pid']}/exe /proc/{f['pid']}/cwd` 와 `sudo ss -ptn | grep pid={f['pid']}` 로 확인하세요. 의심되면 `sudo kill -STOP {f['pid']}` 로 먼저 멈춘 뒤 메모리/바이너리를 보존하고 종료하세요.",
            evidence=f["cmdline"], details=d, is_simulation=sim,
        )
