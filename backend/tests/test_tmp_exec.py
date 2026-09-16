"""
임시 디렉터리 실행 판정.

운영에서 이 규칙의 오탐이 알림 대부분을 차지했다. 오탐의 정체는 AppImage 가 $TMPDIR 아래에
자기를 읽기 전용으로 마운트하고 그 안의 실행 파일로 도는 것이었다(예: orca-ide,
chrome_crashpad_handler). 아래 마운트 표는 실제 호스트의 /proc/self/mountinfo 에서 확인한
모양을 예시 값으로 옮긴 것이다.
"""
from contextlib import contextmanager

import config
from database import Alert, Event
from monitor import process_audit
from monitor.audit import AuditMonitor
from monitor.process_audit import ProcessAudit, exec_origin, normalize_exe, read_mounts

# AppImage 자기 마운트: $TMPDIR 아래, 읽기 전용 fuse
APPIMG = "/tmp/user/1000/.mount_appimg-AbC123"
MOUNTS = [
    ("/", "ext4", False),
    ("/tmp", "ext4", False),
    ("/dev/shm", "tmpfs", False),
    (APPIMG, "fuse.example-app.AppImage", True),
    ("/snap/example-app/42", "squashfs", True),
]


class FakeProc:
    def __init__(self, pid, name, cmdline=None, exe="", user="example", parent="bash", cwd="/home/example"):
        self.pid, self._name, self._cmdline, self._exe = pid, name, cmdline or [name], exe
        self._user, self._parent, self._cwd = user, parent, cwd

    @contextmanager
    def oneshot(self):
        yield

    def name(self): return self._name
    def cmdline(self): return self._cmdline
    def exe(self): return self._exe
    def username(self): return self._user
    def cwd(self): return self._cwd
    def parent(self):
        class P:
            def name(_): return self._parent
        return P()


# --- 판정 함수 ---

def test_appimage_self_mount_is_not_suspicious():
    """orca-ide 와 chrome_crashpad_handler 가 걸렸던 모양. 읽기 전용이라 떨어뜨릴 수 없다."""
    for exe in (f"{APPIMG}/orca-ide", f"{APPIMG}/chrome_crashpad_handler"):
        v = exec_origin(exe, mounts=MOUNTS, allow=[])
        assert v is not None and v["suspicious"] is False
        assert v["kind"] == "readonly_mount" and v["fstype"].startswith("fuse.")
        assert v["mount"] == APPIMG


def test_payload_dropped_in_writable_tmp_is_still_caught():
    """이 규칙이 존재하는 이유. 하나도 놓치지 않는다."""
    for exe in ("/tmp/payload", "/dev/shm/.x/kworker", "/var/tmp/a.out", "/run/shm/x"):
        v = exec_origin(exe, mounts=MOUNTS, allow=[])
        assert v is not None and v["suspicious"] is True and v["kind"] == "writable", exe


def test_deleted_payload_in_tmp_is_caught():
    v = exec_origin("/tmp/payload (deleted)", mounts=MOUNTS, allow=[], isdir=lambda p: True)
    assert v["suspicious"] is True and v["kind"] == "deleted" and v["path"] == "/tmp/payload"


def test_appimage_path_after_unmount_is_not_an_alert():
    """새 버전으로 교체되면 예전 프로세스의 경로가 '지워진 파일' 로 보인다."""
    exe = f"{APPIMG}/orca-ide (deleted)"
    gone = exec_origin(exe, mounts=[("/", "ext4", False)], allow=[], isdir=lambda p: False)
    assert gone["suspicious"] is False and gone["kind"] == "readonly_mount_gone"
    # 디렉터리가 그대로 남아 있으면 넘기지 않는다
    stays = exec_origin(exe, mounts=[("/", "ext4", False)], allow=[], isdir=lambda p: True)
    assert stays["suspicious"] is True


def test_paths_outside_tmp_are_not_this_rule():
    # 패키지·snap 이 소유한 경로는 애초에 임시 디렉터리가 아니다 (snap 판 crashpad 헬퍼 포함)
    assert exec_origin("/usr/bin/python3", mounts=MOUNTS, allow=[]) is None
    assert exec_origin("/snap/example-app/42/chrome_crashpad_handler", mounts=MOUNTS, allow=[]) is None
    assert exec_origin("/home/example/Applications/example.AppImage (deleted)", mounts=MOUNTS, allow=[]) is None
    assert exec_origin("", mounts=MOUNTS, allow=[]) is None


def test_mountinfo_unreadable_falls_back_to_suspicious():
    """판단 근거가 없으면 조용히 안전하다고 하지 않는다."""
    assert read_mounts("/nonexistent/mountinfo") == []
    v = exec_origin(f"{APPIMG}/orca-ide", mounts=[], allow=[])
    assert v["suspicious"] is True


def test_real_host_mountinfo_parses():
    mounts = read_mounts()
    assert mounts and all(m[0].startswith("/") and m[1] for m in mounts)


def test_allowlist(monkeypatch):
    exe = "/tmp/build-cache/runner"
    assert exec_origin(exe, mounts=MOUNTS, allow=[])["suspicious"] is True
    v = exec_origin(exe, mounts=MOUNTS, allow=["/tmp/build-cache/*"])
    assert v["suspicious"] is False and v["kind"] == "allowlist"
    monkeypatch.setattr(config, "TMP_EXEC_ALLOW", ["/tmp/build-cache/*"])
    assert exec_origin(exe, mounts=MOUNTS)["kind"] == "allowlist"


def test_fingerprint_is_per_executable_not_per_launch():
    a = normalize_exe("/tmp/user/1000/.mount_appimg-AbC123/orca-ide")
    b = normalize_exe("/tmp/user/1000/.mount_appimg-ZzY987/orca-ide")
    assert a == b == "/tmp/user/1000/.mount_*/orca-ide"
    assert normalize_exe("/tmp/tmp.AbCdEf1234/payload") == "/tmp/tmp.*/payload"
    assert normalize_exe("/tmp/payload") == "/tmp/payload"


# --- 30초 샘플링 (ProcessAudit) ---

def _iter(monkeypatch, procs):
    monkeypatch.setattr(process_audit, "read_mounts", lambda *a, **k: MOUNTS)
    monkeypatch.setattr(process_audit.psutil, "process_iter", lambda: list(procs))


def test_process_audit_notes_benign_once_and_never_alerts(db, monkeypatch):
    _iter(monkeypatch, [FakeProc(11, "orca-ide", exe=f"{APPIMG}/orca-ide"),
                        FakeProc(12, "chrome_crashpad", exe=f"{APPIMG}/chrome_crashpad_handler")])
    m = ProcessAudit()
    m.tick()
    m.tick()
    assert db.query(Alert).count() == 0
    evs = db.query(Event).filter(Event.event_type == "PROCESS_INDICATOR").all()
    assert len(evs) == 2 and all(e.severity == "INFO" for e in evs)
    assert all(e.details_dict()["origin"] == "readonly_mount" for e in evs)


def test_process_audit_alerts_on_dropped_payload(db, monkeypatch):
    _iter(monkeypatch, [FakeProc(21, "payload", exe="/tmp/payload", user="root")])
    m = ProcessAudit()
    m.tick()
    m.tick()
    a = db.query(Alert).one()
    assert a.rule == "proc_exec_from_tmp" and a.severity == "CRITICAL"
    assert a.fingerprint == "proc:exec_from_tmp:/tmp/payload:root"
    assert a.count == 1   # 같은 프로세스를 다시 세지 않는다


# --- auditd (AuditMonitor) ---

def _exec_lines(serial, exe, argv0):
    stamp = f"1725800000.{serial:03d}:{serial}"
    return [
        f'type=SYSCALL msg=audit({stamp}): arch=c000003e syscall=59 success=yes exit=0 ppid=100 '
        f'pid={200 + serial} auid=4294967295 uid=0 comm="{argv0[:15]}" exe="{exe}" key="secdash_exec"',
        f'type=EXECVE msg=audit({stamp}): argc=1 a0="{argv0}"',
        f'type=CWD msg=audit({stamp}): cwd="/home/example"',
    ]


def _feed(m, lines):
    for line in lines:
        m._ingest(line)
    for ev in list(m._pending.values()):
        m._handle(ev)
    m._pending.clear()


def _monitor(monkeypatch):
    monkeypatch.setattr(process_audit, "read_mounts", lambda *a, **k: MOUNTS)
    return AuditMonitor(log_path="/nonexistent", rules_path="/nonexistent")


def test_audit_exec_ignores_readonly_self_mount(db, monkeypatch):
    m = _monitor(monkeypatch)
    for serial in range(3):
        _feed(m, _exec_lines(serial, f"{APPIMG}/orca-ide", "orca-ide"))
    assert db.query(Alert).count() == 0
    ev = db.query(Event).filter(Event.event_type == "PROCESS_INDICATOR").one()
    assert ev.severity == "INFO" and ev.details_dict()["origin"] == "readonly_mount"


def test_audit_exec_count_does_not_explode(db, monkeypatch):
    """실행마다 같은 지문을 다시 올리면 한 알림의 횟수가 수십만이 된다."""
    monkeypatch.setattr(config, "EXEC_DEDUP_SEC", 60)
    m = _monitor(monkeypatch)
    for serial in range(50):
        _feed(m, _exec_lines(serial, "/tmp/payload", "payload"))
    a = db.query(Alert).filter(Alert.rule == "proc_exec_from_tmp").one()
    assert a.count == 1
    assert db.query(Event).filter(Event.event_type == "PROCESS_INDICATOR").count() == 1


def test_audit_exec_dedup_window_can_be_turned_off(db, monkeypatch):
    monkeypatch.setattr(config, "EXEC_DEDUP_SEC", 0)
    m = _monitor(monkeypatch)
    for serial in range(3):
        _feed(m, _exec_lines(serial, "/tmp/payload", "payload"))
    a = db.query(Alert).filter(Alert.rule == "proc_exec_from_tmp").one()
    assert a.count == 3


def test_audit_exec_fingerprint_survives_relaunch(db, monkeypatch):
    """켤 때마다 마운트 이름이 바뀌어도 알림은 하나다 (예전에는 켤 때마다 새 알림이었다)."""
    monkeypatch.setattr(config, "EXEC_DEDUP_SEC", 0)
    m = _monitor(monkeypatch)
    # 읽기 전용 마운트가 아닌 자리다 (쓰기 가능 → 수상). 디렉터리 이름만 매번 다르다.
    _feed(m, _exec_lines(1, "/tmp/.mount_evil-AaA111/payload", "payload"))
    _feed(m, _exec_lines(2, "/tmp/.mount_evil-BbB222/payload", "payload"))
    a = db.query(Alert).filter(Alert.rule == "proc_exec_from_tmp").one()
    assert a.count == 2 and ".mount_*" in a.fingerprint


def test_audit_tool_exec_is_also_rate_limited(db, monkeypatch):
    monkeypatch.setattr(config, "EXEC_DEDUP_SEC", 60)
    m = _monitor(monkeypatch)
    for serial in range(10):
        _feed(m, _exec_lines(serial, "/usr/bin/nmap", "nmap"))
    a = db.query(Alert).filter(Alert.rule == "security_tool").one()
    assert a.count == 1
