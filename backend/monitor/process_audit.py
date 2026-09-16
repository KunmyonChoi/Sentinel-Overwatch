"""
프로세스 감사(ProcessAudit). 이전 MalwareMonitor 를 대체한다.

이름 부분 일치로 '악성코드' 라고 부르지 않는다. 두 종류로 나눈다.
  1) 도구 실행 감사 (WARNING): nmap, hydra 같은 공격/진단 도구의 실행. 실행 파일 이름 기준 정확 일치.
  2) 실제 지표 (CRITICAL/WARNING):
     - 셸 프로세스의 표준 입출력이 소켓에 연결됨 (리버스 셸 전형)
     - 실행 파일이 /tmp, /var/tmp, /dev/shm 등 임시 디렉터리의 **쓰기 가능한** 자리에 있음
     - 실행 파일이 디스크에서 삭제됨 (업그레이드 후 재시작 필요일 수도 있어 INFO)

임시 디렉터리 판정은 경로 접두사만 보지 않는다. 이 규칙이 잡으려는 것은 '/tmp 라는 이름' 이
아니라 '아무나 파일을 떨어뜨릴 수 있는 자리에서의 실행' 이다. 그래서 경로가 임시 디렉터리
안이라도 읽기 전용으로 마운트된 이미지(AppImage 의 자기 마운트, squashfs, ISO) 안의 파일이면
그 자리에는 애초에 페이로드를 떨어뜨릴 수 없으므로 알림이 아니라 정보 이벤트로 실행 파일마다
한 번만 남긴다. 쓰기 가능한 임시 자리에 떨어진 파일의 실행은 그대로 잡는다.
"""
import fnmatch
import os
import re

import psutil

import config
from alerts import raise_alert
from monitor.base import BaseMonitor

TOOL_NAMES = {
    "nmap", "masscan", "zmap", "hydra", "medusa", "sqlmap", "nikto", "wpscan", "msfconsole", "msfvenom",
    "meterpreter", "mimikatz", "john", "hashcat", "aircrack-ng", "airodump-ng", "tcpdump", "wireshark", "tshark",
    "nc", "ncat", "netcat", "responder", "crackmapexec", "netexec", "impacket-smbclient", "chisel", "ligolo",
}
TMP_DIRS = ("/tmp/", "/var/tmp/", "/dev/shm/", "/run/shm/")
TMP_ROOTS = tuple(d.rstrip("/") for d in TMP_DIRS)
SHELLS = {"sh", "bash", "dash", "zsh", "ash", "ksh", "python", "python3", "perl", "php", "ruby", "socat"}
SIMULATION_SUFFIXES = ("_sim",)

MOUNTINFO = "/proc/self/mountinfo"
DELETED_SUFFIX = " (deleted)"
# mktemp -d 가 만드는 디렉터리 모양. 지문에서 고정한다.
_MKTEMP_RE = re.compile(r"tmp\.[A-Za-z0-9]{6,}")


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


# --- 마운트 판정 ---

def _unescape(field: str) -> str:
    """mountinfo 는 공백·탭·개행·역슬래시를 8진수로 이스케이프한다."""
    for esc, ch in (("\\040", " "), ("\\011", "\t"), ("\\012", "\n"), ("\\134", "\\")):
        field = field.replace(esc, ch)
    return field


def read_mounts(path: str = MOUNTINFO) -> list[tuple[str, str, bool]]:
    """(마운트 지점, 파일 시스템 종류, 읽기 전용) 목록. 읽지 못하면 빈 목록을 돌려준다.

    빈 목록은 '판단할 근거가 없다' 는 뜻이고, 그때는 예전처럼 경로만 보고 수상하다고 본다.
    조용히 안전하다고 단정하지 않는다.
    """
    mounts: list[tuple[str, str, bool]] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return mounts
    for line in lines:
        parts = line.split()
        if "-" not in parts:
            continue
        sep = parts.index("-")
        if sep < 6 or len(parts) <= sep + 1:
            continue
        mount_point = _unescape(parts[4])
        opts = parts[5].split(",")
        fstype = parts[sep + 1]
        super_opts = parts[sep + 3].split(",") if len(parts) > sep + 3 else []
        mounts.append((mount_point, fstype, "ro" in opts or "ro" in super_opts))
    return mounts


def backing_mount(path: str, mounts: list[tuple[str, str, bool]]) -> tuple[str, str, bool] | None:
    """경로를 담고 있는 가장 깊은 마운트."""
    best: tuple[str, str, bool] | None = None
    for mount_point, fstype, read_only in mounts:
        root = mount_point.rstrip("/")
        if path == mount_point or path.startswith(root + "/"):
            if best is None or len(root) > len(best[0].rstrip("/")):
                best = (mount_point, fstype, read_only)
    return best


def tmp_root_of(path: str) -> str | None:
    """경로가 임시 디렉터리 안이면 그 임시 디렉터리를, 아니면 None."""
    for root in TMP_ROOTS:
        if path.startswith(root + "/"):
            return root
    return None


def normalize_exe(path: str) -> str:
    """지문용 경로. 실행할 때마다 이름이 달라지는 임시 디렉터리 조각을 고정한다.

    AppImage 는 켤 때마다 `.mount_<앱이름><무작위>` 에 자기를 마운트하고 `mktemp -d` 는
    `tmp.<무작위>` 를 만든다. 정규화하지 않으면 같은 실행 파일이 켤 때마다 새 알림이 된다.
    """
    segments = []
    for seg in path.split("/"):
        if seg.startswith(".mount_"):
            segments.append(".mount_*")
        elif _MKTEMP_RE.fullmatch(seg):
            segments.append("tmp.*")
        else:
            segments.append(seg)
    return "/".join(segments)


def _is_inside(mount_point: str, tmp_root: str) -> bool:
    """마운트 지점이 임시 디렉터리 '안쪽' 인가. /tmp 자체나 그 상위(/)는 해당하지 않는다."""
    point = mount_point.rstrip("/")
    return len(point) > len(tmp_root) and point.startswith(tmp_root + "/")


def _gone_self_mount(path: str, tmp_root: str, isdir) -> bool:
    """`.mount_*` 조각이 있고 그 디렉터리까지 이미 사라졌으면 마운트 해제 뒤의 잔상으로 본다.

    AppImage 가 새 버전으로 교체되면 아직 돌고 있는 예전 프로세스의 경로가 이 모양이 된다.
    """
    segments = path.split("/")
    for i, seg in enumerate(segments):
        prefix = "/".join(segments[: i + 1])
        if seg.startswith(".mount_") and prefix.startswith(tmp_root + "/"):
            return not isdir(prefix)
    return False


def exec_origin(exe: str, *, mounts: list[tuple[str, str, bool]] | None = None,
                allow: list[str] | None = None, isdir=os.path.isdir) -> dict | None:
    """실행 파일이 임시 디렉터리 안인지, 안이라면 수상한지 판정한다.

    임시 디렉터리 밖이면 None. 안이면 suspicious 와 사람이 읽을 판정 이유를 담은 dict.
    """
    if not exe:
        return None
    deleted = exe.endswith(DELETED_SUFFIX)
    real = exe[: -len(DELETED_SUFFIX)] if deleted else exe
    root = tmp_root_of(real)
    if root is None:
        return None
    verdict = {"path": real, "deleted": deleted, "mount": "", "fstype": ""}

    for pattern in (config.TMP_EXEC_ALLOW if allow is None else allow):
        if fnmatch.fnmatch(real, pattern):
            return verdict | {"suspicious": False, "kind": "allowlist",
                              "reason_ko": f"운영자가 SECDASH_TMP_EXEC_ALLOW 에 넣은 '{pattern}' 과 일치"}

    mount = backing_mount(real, read_mounts() if mounts is None else mounts)
    if mount:
        mount_point, fstype, read_only = mount
        verdict |= {"mount": mount_point, "fstype": fstype}
        if read_only and _is_inside(mount_point, root):
            return verdict | {"suspicious": False, "kind": "readonly_mount",
                              "reason_ko": f"읽기 전용으로 마운트된 이미지({fstype}) 안의 파일 — {mount_point}. "
                                           "이 자리에는 파일을 떨어뜨릴 수 없다"}
    if deleted and _gone_self_mount(real, root, isdir):
        return verdict | {"suspicious": False, "kind": "readonly_mount_gone",
                          "reason_ko": "자기 마운트 디렉터리가 사라진 뒤 남은 경로 "
                                       "(AppImage 가 새 버전으로 교체되면 이 모양이 된다)"}
    if deleted:
        return verdict | {"suspicious": True, "kind": "deleted",
                          "reason_ko": "임시 디렉터리에서 실행된 뒤 실행 파일이 지워짐"}
    return verdict | {"suspicious": True, "kind": "writable",
                      "reason_ko": "쓰기 가능한 임시 디렉터리에 놓인 실행 파일"}


def inspect_process(proc: psutil.Process, *, mounts: list[tuple[str, str, bool]] | None = None) -> dict | None:
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

    # 지표 2: 임시 디렉터리에서 실행 — 경로 이름이 아니라 그 자리에 쓸 수 있는지로 판단한다
    origin = exec_origin(exe, mounts=mounts)
    if origin:
        info |= {"exe_real": origin["path"], "origin": origin["kind"], "origin_ko": origin["reason_ko"],
                 "mount": origin["mount"], "fstype": origin["fstype"],
                 "fingerprint_exe": normalize_exe(origin["path"])}
        if origin["suspicious"]:
            sev = "CRITICAL" if user == "root" else "WARNING"
            return info | {"kind": "indicator", "severity": sev, "indicator": "exec_from_tmp",
                           "indicator_ko": f"임시 디렉터리에서 실행 중인 바이너리 ({origin['path']})"}
        return info | {"kind": "benign_tmp", "severity": "INFO", "indicator": "exec_from_tmp_ignored",
                       "indicator_ko": f"임시 디렉터리 경로이지만 페이로드를 떨어뜨릴 수 없는 자리 ({origin['path']})"}

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
        self.benign_seen: set[str] = set()   # 임시 경로지만 무해로 판정한 실행 파일 (정규화 경로)

    def setup(self):
        if not can_inspect_other_processes():
            self.set_health("degraded", "다른 사용자 프로세스의 실행 파일/파일 디스크립터를 읽을 수 없음",
                            "deploy/secdash.service 처럼 CAP_SYS_PTRACE + CAP_DAC_READ_SEARCH 를 부여하거나 root 로 실행하세요.")

    def tick(self):
        active: set[int] = set()
        mounts = read_mounts()
        for proc in psutil.process_iter():
            try:
                found = inspect_process(proc, mounts=mounts)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception as e:
                self.log.debug(f"inspect failed pid={proc.pid}: {e}")
                continue
            if not found:
                continue
            if found["kind"] == "benign_tmp":
                self._note_benign(found)
                continue
            active.add(proc.pid)
            if proc.pid in self.seen:
                continue
            self.seen.add(proc.pid)
            self._report(found)
        self.seen &= active

    def _note_benign(self, f: dict):
        """알림은 올리지 않는다. 다만 '봤고 이런 이유로 넘겼다' 를 실행 파일마다 한 번 남긴다.

        프로세스마다 남기면 Electron 앱 하나가 라이브 피드를 덮어 버린다.
        """
        key = f["fingerprint_exe"]
        if key in self.benign_seen:
            return
        self.benign_seen.add(key)
        d = {k: f[k] for k in ("pid", "name", "user", "exe", "cmdline", "parent", "cwd",
                               "indicator", "indicator_ko", "origin", "origin_ko", "mount", "fstype")}
        self.log_event("PROCESS_INDICATOR", "INFO",
                       f"exec_from_tmp ignored: {f['exe']} ({f['origin']})", d, is_simulation=f["simulation"])

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
        keys = ["pid", "name", "user", "exe", "cmdline", "parent", "cwd", "indicator", "indicator_ko"]
        keys += [k for k in ("origin", "origin_ko", "mount", "fstype") if k in f]
        d = {k: f[k] for k in keys}
        self.log_event("PROCESS_INDICATOR", f["severity"], f"{f['indicator']}: {f['name']} (PID {f['pid']}, user {f['user']}, exe {f['exe']}){tag}", d, is_simulation=sim)
        if f["severity"] == "INFO":
            return
        # 지문은 실행 파일마다 하나다. 켤 때마다 이름이 바뀌는 임시 디렉터리 때문에 알림이 늘어나지 않게 한다.
        fp_exe = f.get("fingerprint_exe") or f["exe"]
        raise_alert(
            f"proc_{f['indicator']}", f["severity"], f"{f['indicator']}: {f['name']} (PID {f['pid']})",
            fingerprint=f"proc:{f['indicator']}:{fp_exe}:{f['user']}",
            title_ko=f"{f['indicator_ko']} — {f['name']} (사용자 {f['user']})",
            summary_ko=f"PID {f['pid']}, 부모 프로세스 {f['parent']}, 명령줄: {f['cmdline'][:120]}",
            action_ko=f"`sudo ls -l /proc/{f['pid']}/exe /proc/{f['pid']}/cwd` 와 `sudo ss -ptn | grep pid={f['pid']}` 로 확인하세요. 의심되면 `sudo kill -STOP {f['pid']}` 로 먼저 멈춘 뒤 메모리/바이너리를 보존하고 종료하세요.",
            evidence=f["cmdline"], details=d, is_simulation=sim,
        )
