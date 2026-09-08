"""
auditd 로그 연동 (AuditMonitor).

deploy/audit-secdash.rules 가 남기는 다섯 가지 키를 해석한다.
  secdash_exec      대화형 세션의 execve  → 도구 실행·임시 디렉터리 실행을 즉시 탐지 (ProcessAudit 의 30초 샘플링 보완)
  secdash_identity  passwd/shadow/group 쓰기
  secdash_sudo      sudoers 쓰기          → "누가 어떤 프로그램으로 썼나" 를 이벤트로 남긴다.
  secdash_ssh       sshd_config, root 키   IntegrityMonitor 의 diff 알림은 그대로 오고,
  secdash_persist   cron/systemd/ld.so.preload  이 이벤트가 그 알림의 '최근 관리자 활동' 에 붙는다.
  secdash_modules   커널 모듈 로드/제거     → WARNING 알림
auditd 가 없으면 health=degraded 로 표시하고 기존 샘플링 방식이 폴백으로 남는다.
"""
import os
import pwd
import re
import shutil
import subprocess
import time

from alerts import raise_alert
from monitor.base import BaseMonitor, TailReader
from monitor.process_audit import TMP_DIRS, TOOL_NAMES

AUDIT_LOG = "/var/log/audit/audit.log"
RULES_PATH = "/etc/audit/rules.d/secdash.rules"

_REC_RE = re.compile(r"^type=(?P<type>\w+) msg=audit\((?P<ts>\d+\.\d+):(?P<serial>\d+)\):\s*(?P<body>.*)$")
_KV_RE = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)')
_HEX_RE = re.compile(r"^[0-9A-F]+$")
AUID_UNSET = 4294967295

WRITE_KEYS = {"secdash_identity": "WARNING", "secdash_sudo": "WARNING", "secdash_ssh": "WARNING", "secdash_persist": "INFO"}
WRITE_KEY_KO = {"secdash_identity": "계정 파일", "secdash_sudo": "sudo 정책", "secdash_ssh": "SSH 설정/키", "secdash_persist": "영속화 지점"}


_HEX_FIELDS = {"proctitle", "name", "cwd", "comm", "exe", "key", "path", "dir"}


def _decode(value: str, key: str = "", rec_type: str = "") -> str:
    """audit 필드 값: 따옴표 문자열이거나, 문자열 필드에 공백/특수문자가 있으면 16진수 인코딩.
    숫자 필드(auid=1001, a0=7ffd… 등)는 절대 디코딩하지 않는다."""
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    hexable = key in _HEX_FIELDS or (rec_type == "EXECVE" and re.fullmatch(r"a\d+(\[\d+\])?", key or ""))
    if hexable and _HEX_RE.match(value) and len(value) % 2 == 0 and len(value) >= 2:
        try:
            return bytes.fromhex(value).decode("utf-8", errors="replace").replace("\x00", " ").strip()
        except ValueError:
            return value
    return value


def parse_record(line: str) -> dict | None:
    m = _REC_RE.match(line.strip())
    if not m:
        return None
    rec_type = m.group("type")
    fields = {k: _decode(v, k, rec_type) for k, v in _KV_RE.findall(m.group("body"))}
    return {"type": m.group("type"), "ts": float(m.group("ts")), "serial": int(m.group("serial")), **fields}


def _name(uid: str | None) -> str | None:
    if uid is None:
        return None
    try:
        n = int(uid)
    except ValueError:
        return uid
    if n == AUID_UNSET:
        return None
    try:
        return pwd.getpwuid(n).pw_name
    except KeyError:
        return f"uid={n}"


def _user(auid: str | None, uid: str | None) -> str:
    """로그인 계정(auid) 우선. auid 가 없으면 대화형 세션이 아닌 시스템 프로세스다."""
    login = _name(auid)
    if login:
        return login
    eff = _name(uid)
    return f"시스템(자동, {eff})" if eff else "시스템(자동)"


class AuditEvent:
    """같은 serial 의 레코드 묶음."""

    def __init__(self, serial: int, ts: float):
        self.serial, self.ts = serial, ts
        self.syscall: dict = {}
        self.args: list[str] = []
        self.paths: list[tuple[str, str]] = []   # (name, nametype)
        self.cwd = ""
        self.proctitle = ""
        self.updated = time.time()

    def add(self, rec: dict):
        self.updated = time.time()
        t = rec["type"]
        if t == "SYSCALL":
            self.syscall = rec
        elif t == "EXECVE":
            try:
                argc = int(rec.get("argc", "0"))
            except ValueError:
                argc = 0
            self.args = [rec.get(f"a{i}", "") for i in range(argc)]
        elif t == "PATH":
            self.paths.append((rec.get("name", ""), rec.get("nametype", "")))
        elif t == "CWD":
            self.cwd = rec.get("cwd", "")
        elif t == "PROCTITLE":
            self.proctitle = rec.get("proctitle", "")

    @property
    def command(self) -> str:
        return " ".join(self.args) if self.args else self.proctitle


class AuditMonitor(BaseMonitor):
    name = "AuditMonitor"
    label = "명령 실행·파일 쓰기 감사 (auditd)"
    interval = 1
    FLUSH_AFTER = 2.0

    def __init__(self, log_path: str = AUDIT_LOG, rules_path: str = RULES_PATH):
        super().__init__()
        self.log_path = log_path
        self.rules_path = rules_path
        self.source = log_path
        self._reader: TailReader | None = None
        self._pending: dict[int, AuditEvent] = {}
        self._recent_writes: dict[tuple, float] = {}
        self.exec_count = 0

    # --- 상태 ---
    def _auditd_active(self) -> bool:
        if not shutil.which("systemctl"):
            return True
        try:
            return subprocess.run(["systemctl", "is-active", "auditd"], capture_output=True, text=True, timeout=5).stdout.strip() == "active"
        except Exception:
            return True

    def _try_open(self) -> bool:
        if not os.path.exists(self.log_path):
            self.set_health("degraded", "auditd 로그 없음 (auditd 미설치 또는 미실행). 프로세스 감사는 30초 샘플링으로 동작",
                            "sudo apt install auditd 후 deploy/update.sh 로 규칙(deploy/audit-secdash.rules)을 설치하세요.")
            return False
        if not os.path.exists(self.rules_path):
            self.set_health("degraded", "auditd 는 있으나 대시보드 규칙이 설치되지 않음",
                            f"sudo install -m 0640 deploy/audit-secdash.rules {self.rules_path} && sudo augenrules --load")
        try:
            r = TailReader(self.log_path)
            r.open(seek_end=True)
            self._reader = r
        except PermissionError:
            self.set_health("degraded", f"auditd 로그 읽기 권한 없음: {self.log_path}", "서비스에 CAP_DAC_READ_SEARCH 를 부여하세요 (deploy/secdash.service).")
            return False
        if os.path.exists(self.rules_path):
            if self._auditd_active():
                self.set_health("ok")
            else:
                self.set_health("degraded", "auditd 서비스가 실행 중이 아님", "sudo systemctl enable --now auditd")
        return True

    def setup(self):
        self._try_open()

    def tick(self):
        if self._reader is None:
            if not self._try_open():
                return
        for _ in range(5000):
            line = self._reader.readline()
            if not line:
                break
            self._ingest(line)
        self._flush_stale()

    # --- 레코드 묶기 ---
    def _ingest(self, line: str):
        rec = parse_record(line)
        if not rec:
            return
        if rec["type"] == "EOE":
            ev = self._pending.pop(rec["serial"], None)
            if ev:
                self._handle(ev)
            return
        ev = self._pending.get(rec["serial"])
        if ev is None:
            ev = self._pending[rec["serial"]] = AuditEvent(rec["serial"], rec["ts"])
        ev.add(rec)

    def _flush_stale(self):
        now = time.time()
        for serial in [s for s, e in self._pending.items() if now - e.updated > self.FLUSH_AFTER]:
            self._handle(self._pending.pop(serial))

    # --- 해석 ---
    def _handle(self, ev: AuditEvent):
        sc = ev.syscall
        if not sc:
            return
        key = sc.get("key", "")
        user = _user(sc.get("auid"), sc.get("uid"))
        exe = sc.get("exe", "")
        comm = sc.get("comm", "")
        success = sc.get("success", "yes") == "yes"
        if key == "secdash_exec":
            self._on_exec(ev, user, exe, comm)
        elif key in WRITE_KEYS:
            self._on_write(ev, key, user, exe, comm, success)
        elif key == "secdash_modules":
            self._on_module(ev, user, exe, comm, success)

    def _on_exec(self, ev: AuditEvent, user: str, exe: str, comm: str):
        self.exec_count += 1
        cmd = ev.command
        name = os.path.basename(ev.args[0]).lower() if ev.args else comm.lower()
        d = {"user": user, "exe": exe, "command": cmd[:300], "cwd": ev.cwd, "pid": sc_int(ev.syscall.get("pid")), "ppid": sc_int(ev.syscall.get("ppid"))}
        if exe.startswith(TMP_DIRS):
            sev = "CRITICAL" if user == "root" else "WARNING"
            d |= {"indicator": "exec_from_tmp", "indicator_ko": f"임시 디렉터리의 바이너리 실행 ({exe})", "name": name}
            self.log_event("PROCESS_INDICATOR", sev, f"exec_from_tmp: {cmd[:120]} (user {user})", d)
            raise_alert(
                "proc_exec_from_tmp", sev, f"exec from tmp: {exe} (user {user})",
                fingerprint=f"proc:exec_from_tmp:{exe}:{user}",
                title_ko=f"임시 디렉터리의 바이너리 실행 — {name} (사용자 {user})",
                summary_ko=f"명령: {cmd[:120]} · 작업 디렉터리 {ev.cwd}",
                action_ko=f"`sudo ls -l {exe}` 로 파일을 확인하고 출처를 모르면 보존한 채 실행 계정의 세션을 조사하세요.",
                evidence=cmd, details=d,
            )
            return
        if name in TOOL_NAMES or comm.lower() in TOOL_NAMES:
            tool = name if name in TOOL_NAMES else comm.lower()
            d |= {"tool": tool, "name": name, "parent": "", "cmdline": cmd[:300]}
            self.log_event("PROCESS_TOOL", "WARNING", f"Security tool '{tool}' executed by {user}: {cmd[:120]}", d)
            raise_alert(
                "security_tool", "WARNING", f"Security tool executed: {tool} (user {user})",
                fingerprint=f"security_tool:{tool}:{user}",
                title_ko=f"보안/공격 도구 '{tool}' 실행 (사용자 {user})",
                summary_ko=f"명령: {cmd[:160]} · 작업 디렉터리 {ev.cwd}",
                action_ko="관리자의 진단 작업이면 확인(ack) 처리하세요. 아니라면 해당 계정의 최근 로그인(`last <계정>`)과 세션을 확인하세요.",
                evidence=cmd, details=d,
            )

    def _on_write(self, ev: AuditEvent, key: str, user: str, exe: str, comm: str, success: bool):
        paths = sorted({p for p, t in ev.paths if p and t in ("CREATE", "DELETE", "NORMAL") and not p.endswith("/")})
        if not paths:
            paths = sorted({p for p, _t in ev.paths if p})[:3]
        dedup = (user, exe, tuple(paths))
        now = time.time()
        if now - self._recent_writes.get(dedup, 0) < 5:
            return
        self._recent_writes[dedup] = now
        for k in [k for k, t in self._recent_writes.items() if now - t > 60]:
            self._recent_writes.pop(k, None)
        d = {"user": user, "exe": exe, "comm": comm, "paths": paths, "success": success, "key": key, "kind_ko": WRITE_KEY_KO[key], "command": ev.proctitle[:200]}
        sev = WRITE_KEYS[key] if success else "WARNING"
        self.log_event("AUDIT_WRITE", sev, f"{user} wrote {', '.join(paths)[:150]} via {exe}" + ("" if success else " (denied)"), d)
        if any(p == "/etc/ld.so.preload" for p in paths):
            raise_alert(
                "ld_preload_write", "CRITICAL", f"/etc/ld.so.preload written by {user} via {exe}",
                fingerprint="ld_preload_write",
                title_ko=f"/etc/ld.so.preload 에 쓰기 발생 (사용자 {user}, {exe})",
                summary_ko="정상 시스템에는 보통 없는 파일입니다. 루트킷이 라이브러리를 주입하는 전형적인 경로입니다.",
                action_ko="`sudo cat /etc/ld.so.preload` 내용을 확인하고 알 수 없는 라이브러리면 즉시 비우고 격리하세요.",
                evidence=ev.proctitle, details=d,
            )

    def _on_module(self, ev: AuditEvent, user: str, exe: str, comm: str, success: bool):
        op = "제거" if ev.syscall.get("syscall") in ("176", "delete_module") else "로드"
        d = {"user": user, "exe": exe, "comm": comm, "command": ev.proctitle[:200], "op": op, "success": success}
        self.log_event("KERNEL_MODULE", "WARNING", f"kernel module {op} by {user}: {ev.proctitle[:120]}", d)
        raise_alert(
            "kernel_module", "WARNING", f"Kernel module {op} by {user}",
            fingerprint=f"kernel_module:{user}:{ev.proctitle[:60]}",
            title_ko=f"커널 모듈 {op} (사용자 {user})",
            summary_ko=f"명령: {ev.proctitle[:160]}",
            action_ko="`lsmod | head` 와 `dmesg | tail` 로 어떤 모듈인지 확인하세요. 드라이버 설치 작업이 아니면 루트킷을 의심하세요.",
            evidence=ev.proctitle, details=d,
        )


def sc_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
