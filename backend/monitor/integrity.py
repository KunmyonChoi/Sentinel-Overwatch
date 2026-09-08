"""
파일 무결성(IntegrityMonitor)과 영속화 지점(PersistenceMonitor) 감시.

- 기준선은 DB 에 저장되어 재시작 후에도 유지된다. 시작 시 저장된 기준선과 비교해
  서비스가 꺼져 있던 동안의 변경도 잡아낸다.
- 권한 문제로 읽을 수 없는 파일은 '정상' 으로 취급하지 않고 health=degraded 로 노출한다.
- 비밀이 아닌 파일은 내용을 저장해 변경 시 diff 를 알림에 첨부한다.
"""
import difflib
import glob
import hashlib
import os
import re
import stat
from pathlib import Path

from alerts import raise_alert, recent_admin_context, recent_package_activity
from integrations import apt
from database import IntegrityBaseline, SessionLocal
from monitor.base import BaseMonitor

UNREADABLE = "__UNREADABLE__"
SNAPSHOT_LIMIT = 200_000   # bytes


def sha256_file(path: str) -> str | None:
    """파일 해시. 없으면 None, 읽을 수 없으면 UNREADABLE."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except FileNotFoundError:
        return None
    except PermissionError:
        return UNREADABLE
    except IsADirectoryError:
        return None
    except OSError:
        return UNREADABLE


def read_text(path: str) -> str | None:
    try:
        with open(path, "rb") as f:
            data = f.read(SNAPSHOT_LIMIT)
        return data.decode("utf-8", errors="replace")
    except OSError:
        return None


def unified_diff(old: str | None, new: str | None, path: str, limit: int = 4000) -> str:
    lines = difflib.unified_diff((old or "").splitlines(), (new or "").splitlines(), fromfile=f"{path} (이전)", tofile=f"{path} (현재)", lineterm="", n=1)
    out = "\n".join(lines)
    return out[:limit] + ("\n… (생략)" if len(out) > limit else "")


# --- 파일별 의미 있는 요약 --------------------------------------------------
def summarize_passwd(old: str | None, new: str | None) -> str:
    o = {l.split(":")[0]: l for l in (old or "").splitlines() if ":" in l}
    n = {l.split(":")[0]: l for l in (new or "").splitlines() if ":" in l}
    parts = []
    for u in sorted(set(n) - set(o)):
        f = n[u].split(":")
        parts.append(f"사용자 추가: {u} (uid {f[2] if len(f) > 2 else '?'}, 셸 {f[6] if len(f) > 6 else '?'})")
    for u in sorted(set(o) - set(n)):
        parts.append(f"사용자 삭제: {u}")
    for u in sorted(set(o) & set(n)):
        if o[u] != n[u]:
            of, nf = o[u].split(":"), n[u].split(":")
            if len(of) > 2 and len(nf) > 2 and of[2] != nf[2]:
                parts.append(f"{u} 의 UID 변경 {of[2]} → {nf[2]}" + (" (root 권한!)" if nf[2] == "0" else ""))
            elif len(of) > 6 and len(nf) > 6 and of[6] != nf[6]:
                parts.append(f"{u} 의 셸 변경 {of[6]} → {nf[6]}")
            else:
                parts.append(f"{u} 항목 변경")
    return "; ".join(parts) or "내용 변경"


def _key_fingerprint(line: str) -> str:
    parts = line.split()
    if len(parts) < 2:
        return line[:40]
    try:
        import base64
        raw = base64.b64decode(parts[1])
        fp = base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
        return f"{parts[0]} SHA256:{fp[:16]}… {' '.join(parts[2:])[:40]}"
    except Exception:
        return f"{parts[0]} {parts[1][:16]}… {' '.join(parts[2:])[:40]}"


def summarize_authorized_keys(old: str | None, new: str | None) -> str:
    o = {l.strip() for l in (old or "").splitlines() if l.strip() and not l.startswith("#")}
    n = {l.strip() for l in (new or "").splitlines() if l.strip() and not l.startswith("#")}
    parts = [f"키 추가: {_key_fingerprint(k)}" for k in sorted(n - o)]
    parts += [f"키 삭제: {_key_fingerprint(k)}" for k in sorted(o - n)]
    return "; ".join(parts) or "내용 변경"


def summarize_sudoers(old: str | None, new: str | None) -> str:
    o = {l.strip() for l in (old or "").splitlines() if l.strip() and not l.startswith("#")}
    n = {l.strip() for l in (new or "").splitlines() if l.strip() and not l.startswith("#")}
    parts = [f"추가: {l[:80]}" for l in sorted(n - o)] + [f"삭제: {l[:80]}" for l in sorted(o - n)]
    return "; ".join(parts) or "내용 변경"


def summarize_generic(old: str | None, new: str | None) -> str:
    o = {l.strip() for l in (old or "").splitlines()}
    n = {l.strip() for l in (new or "").splitlines()}
    return f"{len(n - o)}줄 추가, {len(o - n)}줄 삭제"


ALWAYS_ALERT_MARKERS = ("sudoers", "sshd_config", "authorized_keys", "ld.so.preload", "/etc/shadow", "/etc/passwd", "/etc/group")


def package_context(path: str) -> tuple[str | None, str | None]:
    """(소유 패키지, 최근 그 패키지의 설치/업그레이드 설명). 패키지 작업의 부산물이면 둘 다 값이 있다."""
    owner = apt.package_owner(path)
    if not owner:
        return None, None
    return owner, recent_package_activity(owner)


WATCH_FILES = {
    # path: (severity, secret?, summarizer, 한국어 설명)
    "/etc/passwd": ("WARNING", False, summarize_passwd, "사용자 계정 목록"),
    "/etc/group": ("WARNING", False, summarize_generic, "그룹 목록"),
    "/etc/shadow": ("WARNING", True, None, "비밀번호 해시"),
    "/etc/sudoers": ("CRITICAL", False, summarize_sudoers, "sudo 권한 정책"),
    "/etc/ssh/sshd_config": ("CRITICAL", False, summarize_generic, "SSH 서버 설정"),
    "/etc/hosts": ("WARNING", False, summarize_generic, "호스트 이름 매핑"),
    "/etc/ld.so.preload": ("CRITICAL", False, summarize_generic, "라이브러리 프리로드 (루트킷 기법)"),
    "/etc/crontab": ("WARNING", False, summarize_generic, "시스템 크론"),
}
WATCH_GLOBS = {
    "/etc/sudoers.d/*": ("CRITICAL", False, summarize_sudoers, "sudo 권한 정책 (drop-in)"),
    "/etc/ssh/sshd_config.d/*.conf": ("CRITICAL", False, summarize_generic, "SSH 서버 설정 (drop-in)"),
    "/root/.ssh/authorized_keys": ("CRITICAL", False, summarize_authorized_keys, "root SSH 공개키"),
    "/home/*/.ssh/authorized_keys": ("CRITICAL", False, summarize_authorized_keys, "SSH 공개키"),
    "/etc/modprobe.d/*.conf": ("WARNING", False, summarize_generic, "커널 모듈 정책 (usb-storage 차단 등)"),
    "/etc/sysctl.d/*.conf": ("WARNING", False, summarize_generic, "커널 파라미터"),
}


def _expand_watch() -> dict[str, tuple]:
    files = dict(WATCH_FILES)
    for pattern, spec in WATCH_GLOBS.items():
        for p in glob.glob(pattern):
            if os.path.basename(p) == "README":
                continue
            files.setdefault(p, spec)
    home_keys = str(Path.home() / ".ssh" / "authorized_keys")
    files.setdefault(home_keys, WATCH_GLOBS["/home/*/.ssh/authorized_keys"])
    return files


class _BaselineStore:
    """IntegrityBaseline 테이블 접근을 감싼다."""

    def __init__(self, prefix: str):
        self.prefix = prefix

    def load(self) -> dict[str, tuple[str | None, str | None]]:
        db = SessionLocal()
        try:
            rows = db.query(IntegrityBaseline).filter(IntegrityBaseline.key.like(f"{self.prefix}:%")).all()
            return {r.key[len(self.prefix) + 1:]: (r.digest, r.snapshot) for r in rows}
        finally:
            db.close()

    def save(self, path: str, digest: str | None, snapshot: str | None):
        db = SessionLocal()
        try:
            key = f"{self.prefix}:{path}"
            row = db.query(IntegrityBaseline).filter(IntegrityBaseline.key == key).first()
            if row:
                row.digest, row.snapshot = digest, snapshot
            else:
                db.add(IntegrityBaseline(key=key, digest=digest, snapshot=snapshot))
            db.commit()
        finally:
            db.close()


class IntegrityMonitor(BaseMonitor):
    name = "IntegrityMonitor"
    label = "핵심 파일 무결성"
    interval = 60

    def __init__(self, interval: int | None = None, watch: dict | None = None):
        super().__init__(interval)
        self.watch = watch if watch is not None else _expand_watch()
        self.source = f"sha256 of {len(self.watch)} files"
        self.store = _BaselineStore("file")
        self.baselines: dict[str, tuple[str | None, str | None]] = {}
        self.unreadable: set[str] = set()

    def setup(self):
        self.baselines = self.store.load()
        first_run = not self.baselines
        for path, spec in self.watch.items():
            digest = sha256_file(path)
            if digest == UNREADABLE:
                self.unreadable.add(path)
                continue
            snapshot = None if spec[1] else (read_text(path) if digest else None)
            if path not in self.baselines:
                self.baselines[path] = (digest, snapshot)
                self.store.save(path, digest, snapshot)
                if not first_run and digest:
                    self.log.info(f"baseline added for new watch path {path}")
            elif self.baselines[path][0] != digest:
                # 서비스가 꺼져 있던 동안 바뀜
                self._report_change(path, spec, self.baselines[path], (digest, snapshot), offline=True)
                self.baselines[path] = (digest, snapshot)
                self.store.save(path, digest, snapshot)
        self._update_health()

    def _update_health(self):
        if self.unreadable:
            names = ", ".join(sorted(self.unreadable))
            self.set_health("degraded", f"읽을 수 없어 감시하지 못하는 파일: {names}",
                            "deploy/secdash.service 처럼 CAP_DAC_READ_SEARCH 를 부여하거나 서비스 계정을 shadow 그룹에 추가하세요.")
        else:
            self.set_health("ok")

    def tick(self):
        # 새로 생긴 홈 디렉터리의 authorized_keys 등 glob 대상 갱신
        if self.watch is not None and any(k.startswith("/home/") for k in self.watch):
            for p, spec in _expand_watch().items():
                if p not in self.watch:
                    self.watch[p] = spec
        for path, spec in list(self.watch.items()):
            digest = sha256_file(path)
            if digest == UNREADABLE:
                if path not in self.unreadable:
                    self.unreadable.add(path)
                    self._update_health()
                continue
            if path in self.unreadable:
                self.unreadable.discard(path)
                self._update_health()
            old = self.baselines.get(path, (None, None))
            if old[0] == digest:
                continue
            snapshot = None if spec[1] else (read_text(path) if digest else None)
            self._report_change(path, spec, old, (digest, snapshot), offline=False)
            self.baselines[path] = (digest, snapshot)
            self.store.save(path, digest, snapshot)

    def _report_change(self, path: str, spec: tuple, old: tuple, new: tuple, offline: bool):
        severity, secret, summarizer, desc_ko = spec
        old_digest, old_snap = old
        new_digest, new_snap = new
        if old_digest is None:
            change_ko, change = "새로 생성됨", "created"
        elif new_digest is None:
            change_ko, change = "삭제됨", "deleted"
        else:
            change_ko, change = "변경됨", "modified"
        when = " (서비스 중지 중)" if offline else ""
        summary = summarizer(old_snap, new_snap) if (summarizer and change == "modified") else change_ko
        diff = "" if secret else unified_diff(old_snap, new_snap, path)
        try:
            st = os.stat(path)
            meta = f"mode {stat.filemode(st.st_mode)}, uid {st.st_uid}, mtime {int(st.st_mtime)}"
        except OSError:
            meta = ""
        d = {"path": path, "change": change, "change_ko": change_ko + when, "summary": summary, "meta": meta, "offline": offline, "desc_ko": desc_ko}
        if not any(m in path for m in ALWAYS_ALERT_MARKERS):
            owner, activity = package_context(path)
            if owner and activity:
                d |= {"package": owner, "package_activity": activity, "change_ko": f"{change_ko} (패키지 {owner} 작업의 일부)"}
                self.log_event("FILE_INTEGRITY", "INFO", f"{path} {change} by package {owner}: {activity}", d)
                return
        self.log_event("FILE_INTEGRITY", severity, f"{path} {change}{' while service was down' if offline else ''}: {summary}", d)
        raise_alert(
            "integrity_change", severity, f"{path} {change}: {summary}",
            fingerprint=f"integrity:{path}:{new_digest or 'deleted'}",
            title_ko=f"{desc_ko} {change_ko}{when}: {path}",
            summary_ko=summary + (f" [{meta}]" if meta else ""),
            action_ko=self._action_for(path, change),
            evidence=(diff or f"sha256 {old_digest} → {new_digest}") + "\n\n" + recent_admin_context(),
            details=d,
        )

    @staticmethod
    def _action_for(path: str, change: str) -> str:
        if "authorized_keys" in path:
            return "본인이 추가한 키가 아니면 즉시 해당 줄을 제거하고(`sudoedit` 권장) 현재 SSH 세션을 `who`/`ss -tnp` 로 확인해 종료하세요. 키 추가 시각과 로그인 기록(`last -a`)을 대조하세요."
        if "sudoers" in path:
            return "`sudo visudo -c` 로 문법을 확인하고 추가된 줄을 검토하세요. 예정된 변경이 아니면 즉시 되돌리고 변경한 계정의 세션을 조사하세요."
        if "sshd_config" in path:
            return "`sudo sshd -T | grep -E 'permitrootlogin|passwordauthentication|authorizedkeysfile'` 로 실제 적용 값을 확인하세요. 의도치 않은 변경이면 되돌리고 `sudo systemctl reload ssh` 하세요."
        if path in ("/etc/passwd", "/etc/group"):
            return "추가된 계정/그룹이 예정된 것인지 확인하세요. UID 0 계정이 추가되었다면 즉시 제거하세요."
        if path == "/etc/shadow":
            return "비밀번호 변경이 예정된 것인지 확인하세요. 예정에 없다면 `sudo passwd -S <계정>` 으로 상태를 보고 해당 계정을 잠그세요(`sudo usermod -L`)."
        if "/etc/modprobe.d/" in path:
            return "usb-storage 나 프로토콜 차단 줄이 지워졌다면 누가 해제했는지 '최근 관리자 활동' 으로 확인하세요. 의도한 해제면 확인(ack), 아니면 harden.sh --apply --disable-usb-storage 로 복구하세요."
        if "ld.so.preload" in path:
            return "정상 시스템에는 보통 이 파일이 없습니다. 내용을 확인하고 알 수 없는 라이브러리라면 루트킷을 의심해 격리하세요."
        if change == "deleted":
            return "파일 삭제는 흔치 않습니다. 백업에서 복원하고 삭제 주체를 조사하세요."
        return "변경 내용(diff)을 확인하고 예정된 작업이면 확인(ack) 처리하세요."


# --- 영속화 지점 ------------------------------------------------------------
CRON_DIRS = ["/etc/cron.d", "/etc/cron.hourly", "/etc/cron.daily", "/etc/cron.weekly", "/etc/cron.monthly", "/var/spool/cron/crontabs"]
SYSTEMD_DIRS = ["/etc/systemd/system", "/etc/systemd/user", "/usr/local/lib/systemd/system"]
SUID_DIRS = ["/usr/bin", "/usr/sbin", "/usr/local/bin", "/usr/local/sbin", "/bin", "/sbin", "/opt", "/tmp", "/var/tmp", "/dev/shm", "/home"]
SUID_MAX_DEPTH = 3


def list_files(dirs: list[str], patterns: tuple[str, ...] = ()) -> list[str]:
    out = []
    for d in dirs:
        try:
            for entry in os.scandir(d):
                if entry.is_file(follow_symlinks=True) or entry.is_symlink():
                    if not patterns or entry.name.endswith(patterns):
                        out.append(entry.path)
        except (FileNotFoundError, PermissionError, NotADirectoryError):
            continue
    return sorted(out)


def find_suid(dirs: list[str], max_depth: int = SUID_MAX_DEPTH) -> tuple[set[str], set[str]]:
    """(SUID/SGID 파일 집합, 접근 거부 디렉터리 집합)"""
    found: set[str] = set()
    denied: set[str] = set()

    def walk(path: str, depth: int):
        try:
            it = os.scandir(path)
        except PermissionError:
            denied.add(path)
            return
        except (FileNotFoundError, NotADirectoryError):
            return
        with it:
            for entry in it:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if depth < max_depth:
                            walk(entry.path, depth + 1)
                    elif entry.is_file(follow_symlinks=False):
                        mode = entry.stat(follow_symlinks=False).st_mode
                        if mode & (stat.S_ISUID | stat.S_ISGID):
                            found.add(entry.path)
                except (PermissionError, FileNotFoundError):
                    continue
    for d in dirs:
        walk(d, 0)
    return found, denied


class PersistenceMonitor(BaseMonitor):
    name = "PersistenceMonitor"
    label = "영속화 지점 감시 (cron/systemd/SUID)"
    interval = 300

    def __init__(self, interval: int | None = None, cron_dirs=None, systemd_dirs=None, suid_dirs=None):
        super().__init__(interval)
        self.cron_dirs = cron_dirs if cron_dirs is not None else CRON_DIRS
        self.systemd_dirs = systemd_dirs if systemd_dirs is not None else SYSTEMD_DIRS + self._user_systemd_dirs()
        self.suid_dirs = suid_dirs if suid_dirs is not None else SUID_DIRS
        self.source = "cron 디렉터리, systemd 유닛, SUID/SGID 바이너리"
        self.stores = {"cron": _BaselineStore("cron"), "systemd": _BaselineStore("systemd"), "suid": _BaselineStore("suid")}
        self.baselines: dict[str, dict[str, tuple]] = {}

    @staticmethod
    def _user_systemd_dirs() -> list[str]:
        return [p for p in glob.glob("/home/*/.config/systemd/user") + [str(Path.home() / ".config/systemd/user")] if os.path.isdir(p)]

    def setup(self):
        for kind in ("cron", "systemd", "suid"):
            self.baselines[kind] = self.stores[kind].load()
        first = {k: not v for k, v in self.baselines.items()}
        self._check("cron", first["cron"])
        self._check("systemd", first["systemd"])
        self._check_suid(first["suid"])

    def tick(self):
        self._check("cron", False)
        self._check("systemd", False)
        self._check_suid(False)

    def _current_files(self, kind: str) -> list[str]:
        if kind == "cron":
            return list_files(self.cron_dirs)
        return list_files(self.systemd_dirs, (".service", ".timer", ".socket", ".path", ".mount", ".automount"))

    def _check(self, kind: str, first_run: bool):
        base = self.baselines[kind]
        store = self.stores[kind]
        current = self._current_files(kind)
        kind_ko = {"cron": "크론 작업", "systemd": "systemd 유닛"}[kind]
        seen = set()
        for path in current:
            seen.add(path)
            digest = sha256_file(path)
            if digest == UNREADABLE:
                continue
            snap = read_text(path)
            if path not in base:
                base[path] = (digest, snap)
                store.save(path, digest, snap)
                if not first_run:
                    self._report(kind, kind_ko, path, "created", None, snap)
            elif base[path][0] != digest:
                old_snap = base[path][1]
                base[path] = (digest, snap)
                store.save(path, digest, snap)
                self._report(kind, kind_ko, path, "modified", old_snap, snap)
        for path in list(base):
            if path not in seen and base[path][0] is not None:
                old_snap = base[path][1]
                base[path] = (None, None)
                store.save(path, None, None)
                self._report(kind, kind_ko, path, "deleted", old_snap, None)

    def _report(self, kind: str, kind_ko: str, path: str, change: str, old: str | None, new: str | None):
        change_ko = {"created": "새로 생성됨", "modified": "변경됨", "deleted": "삭제됨"}[change]
        content = (new or old or "")
        base = os.path.basename(path)
        # 1) systemctl mask 가 만든 /dev/null 링크
        if kind == "systemd" and change != "deleted" and os.path.islink(path) and os.path.realpath(path) == "/dev/null":
            d = {"kind": kind, "kind_ko": kind_ko, "path": path, "change": "masked", "change_ko": "마스크됨 (/dev/null 링크)"}
            self.log_event("PERSISTENCE", "INFO", f"{kind} unit masked: {path}", d)
            return
        # 2) snapd 가 관리하는 mount 유닛 (snap 갱신마다 바뀜)
        if kind == "systemd" and base.startswith("snap-") and base.endswith(".mount"):
            d = {"kind": kind, "kind_ko": kind_ko, "path": path, "change": change, "change_ko": change_ko + " (snapd 관리)"}
            self.log_event("PERSISTENCE", "INFO", f"{kind} snap mount unit {change}: {path}", d)
            return
        # 3) 패키지 설치/업그레이드가 만든 파일
        if change != "deleted":
            owner, activity = package_context(path)
            if owner and activity:
                d = {"kind": kind, "kind_ko": kind_ko, "path": path, "change": change, "change_ko": f"{change_ko} (패키지 {owner} 작업의 일부)", "package": owner, "package_activity": activity}
                self.log_event("PERSISTENCE", "INFO", f"{kind} {change} by package {owner}: {path}", d)
                return
        suspicious = bool(re.search(r"(curl|wget)\s.*\|\s*(ba)?sh|/dev/tcp/|base64\s+-d|nc\s+-e|python[23]?\s+-c", content))
        severity = "CRITICAL" if suspicious else "WARNING"
        d = {"kind": kind, "kind_ko": kind_ko, "path": path, "change": change, "change_ko": change_ko, "suspicious": suspicious}
        self.log_event("PERSISTENCE", severity, f"{kind} {change}: {path}", d)
        raise_alert(
            f"persistence_{kind}", severity, f"{kind_ko} {change}: {path}",
            fingerprint=f"persistence:{kind}:{path}:{change}:{hashlib.sha256((new or '').encode()).hexdigest()[:12]}",
            title_ko=f"{kind_ko} {change_ko}: {os.path.basename(path)}" + (" (의심 패턴 포함)" if suspicious else ""),
            summary_ko=f"경로 {path}" + (" — 원격 스크립트 실행/리버스 셸 패턴이 있습니다." if suspicious else ""),
            action_ko="예정된 배포/설정 변경이면 확인(ack) 처리하세요. 아니라면 파일을 비활성화(systemctl disable / 파일 이동)하고 생성 주체를 `ls -l --time-style=full-iso` 와 auth.log 에서 대조하세요.",
            evidence=(unified_diff(old, new, path) if change == "modified" else content[:3000]) + "\n\n" + recent_admin_context(),
            details=d,
        )

    def _check_suid(self, first_run: bool):
        base = self.baselines["suid"]
        store = self.stores["suid"]
        found, denied = find_suid(self.suid_dirs)
        # /sbin → /usr/sbin 같은 merged-usr 경로는 실제 경로 하나로 합친다
        found = {os.path.realpath(p) for p in found}
        if denied and self.health != "down":
            self.set_health("degraded", f"SUID 스캔에서 접근 거부된 디렉터리 {len(denied)}개 (예: {sorted(denied)[0]})",
                            "완전한 스캔을 위해 CAP_DAC_READ_SEARCH 권한을 부여하세요.")
        for path in sorted(found):
            if path not in base:
                base[path] = ("suid", None)
                store.save(path, "suid", None)
                if first_run:
                    continue
                d = {"kind": "suid", "kind_ko": "SUID/SGID 바이너리", "path": path, "change": "created", "change_ko": "새로 생성됨"}
                owner, activity = package_context(path)
                if owner and activity:
                    d |= {"package": owner, "package_activity": activity, "change_ko": f"새로 생성됨 (패키지 {owner} 설치의 일부)"}
                    self.log_event("PERSISTENCE", "INFO", f"SUID/SGID binary from package {owner}: {path}", d)
                    continue
                self.log_event("PERSISTENCE", "CRITICAL", f"New SUID/SGID binary: {path}", d)
                raise_alert(
                    "persistence_suid", "CRITICAL", f"New SUID/SGID binary: {path}",
                    fingerprint=f"persistence:suid:{path}",
                    title_ko=f"새 SUID/SGID 바이너리: {path}",
                    summary_ko="setuid 비트가 있는 실행 파일이 새로 생겼습니다. 패키지 설치가 아니라면 권한 상승 백도어일 수 있습니다.",
                    action_ko=f"`dpkg -S {path}` 로 패키지 소유인지 확인하세요. 아니라면 `sudo chmod u-s,g-s {path}` 로 비트를 제거하고 파일을 보존한 채 조사하세요.",
                    details=d,
                )
        for path in list(base):
            if path not in found and base[path][0] is not None:
                base[path] = (None, None)
                store.save(path, None, None)
                d = {"kind": "suid", "kind_ko": "SUID/SGID 바이너리", "path": path, "change": "deleted", "change_ko": "제거됨"}
                self.log_event("PERSISTENCE", "INFO", f"SUID/SGID binary removed: {path}", d)
