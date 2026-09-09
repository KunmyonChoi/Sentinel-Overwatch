"""
인증 로그 감시(AuthLogWatcher)와 네트워크 감시(NetworkWatcher).

AuthLogWatcher 는 로그 한 줄을 구조화(계정, IP, 방식)해 원시 이벤트로 남기고,
아래 상관 규칙에 해당할 때만 알림(Alert)을 올린다.
  - 브루트포스: 같은 IP 의 실패가 창(window) 안에서 임계치 이상
  - 실패 후 성공: 실패 이력이 있는 IP 에서 로그인 성공 (CRITICAL)
  - 처음 보는 공인 IP 에서 로그인 성공
  - root 직접 SSH 로그인
  - sudo 실패, 계정/그룹 변경
로그 파일을 읽을 수 없으면 테스트 파일로 대체하지 않고 health=down 으로 알린다.
"""
import ipaddress
import json
import logging
import os
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta

import psutil

import config
from alerts import raise_alert
from database import Event, KnownListener, KnownLoginIP, SessionLocal, utcnow
from integrations.accounts import PRIVILEGED_GROUPS
from monitor.base import BaseMonitor, TailReader

logger = logging.getLogger("intrusion_monitor")

# --- syslog 줄 파서 -------------------------------------------------------
_SYSLOG_RE = re.compile(
    r"^(?P<ts>(?:[A-Z][a-z]{2}\s+\d{1,2}\s+[\d:]{8})|(?:\d{4}-\d{2}-\d{2}T[\d:.+\-Z]+))\s+"
    r"(?P<host>\S+)\s+(?P<prog>[^\s\[:]+)(?:\[(?P<pid>\d+)\])?:\s?(?P<msg>.*)$"
)
_IP_RE = r"(?P<ip>(?:\d{1,3}\.){3}\d{1,3}|[0-9a-fA-F:]+:[0-9a-fA-F:]*)"
_FAILED_RE = re.compile(r"Failed (?P<method>password|publickey|keyboard-interactive/pam|none) for (?P<invalid>invalid user )?(?P<user>\S+) from " + _IP_RE)
_INVALID_RE = re.compile(r"Invalid user (?P<user>\S*) from " + _IP_RE)
_ACCEPTED_RE = re.compile(r"Accepted (?P<method>\S+) for (?P<user>\S+) from " + _IP_RE + r" port \d+ ssh2(?::\s*(?P<key>.+))?")
_MAXAUTH_RE = re.compile(r"maximum authentication attempts exceeded for (?P<invalid>invalid user )?(?P<user>\S+) from " + _IP_RE)
# TTY= 는 서비스 계정(비대화형)에서는 빠진다
_SUDO_CMD_RE = re.compile(r"^\s*(?P<user>\S+)\s*:\s*(?P<fail>[^;]*?)\s*;?\s*(?:TTY=(?P<tty>\S*)\s*;\s*)?PWD=(?P<pwd>[^;]*);\s*USER=(?P<target>\S+)\s*;\s*(?:ENV=[^;]*;\s*)?COMMAND=(?P<command>.*)$")
# "by kunmyon(uid=1001)" 또는 로그인 이름이 없는 "by (uid=997)"
_SESSION_RE = re.compile(r"session opened for user (?P<user>[^\s(]+)(?:\(uid=\d+\))? by (?P<by>[^\s(]*)(?:\(uid=(?P<by_uid>\d+)\))?")


def _resolve_by(m) -> str:
    by = m.group("by") or ""
    if by:
        return by
    uid = m.group("by_uid")
    if uid is None:
        return "?"
    try:
        import pwd
        return pwd.getpwuid(int(uid)).pw_name
    except (KeyError, ValueError):
        return f"uid={uid}"
_USERADD_RE = re.compile(r"new user: name=(?P<user>[^,]+)")
_USERDEL_RE = re.compile(r"delete user '(?P<user>[^']+)'")
_USERMOD_RE = re.compile(r"add '(?P<user>[^']+)' to (?:shadow )?group '(?P<group>[^']+)'")
_USERMOD_DEL_RE = re.compile(r"remove '(?P<user>[^']+)' from (?:shadow )?group '(?P<group>[^']+)'")
# gpasswd 는 usermod 와 다른 문장을 남긴다 (shadow-utils gpasswd.c)
#   user kim added by root to group docker / user kim removed by root from group docker
_GPASSWD_ADD_RE = re.compile(r"user '?(?P<user>[^' ]+)'? added by \S+ to group '?(?P<group>[^' ]+)'?")
_GPASSWD_DEL_RE = re.compile(r"user '?(?P<user>[^' ]+)'? removed by \S+ from group '?(?P<group>[^' ]+)'?")
_GROUPADD_RE = re.compile(r"new group: name=(?P<group>[^,]+)")
_GROUPDEL_RE = re.compile(r"group '(?P<group>[^']+)' removed from")
_PASSWD_RE = re.compile(r"password changed for (?P<user>\S+)")

SHELL_NAMES = {"bash", "sh", "zsh", "dash", "fish", "su"}


def is_interactive_shell(command: str) -> bool:
    """대화형 셸 획득만 WARNING 으로 본다. `sh -c '<스크립트>'` 같은 스크립트 실행은 INFO."""
    toks = command.split()
    if not toks:
        return False
    import os as _os
    name = _os.path.basename(toks[0])
    if name == "su":
        return True
    if name in SHELL_NAMES:
        return len(toks) == 1 or any(t in ("-i", "-l", "--login") for t in toks[1:])
    return any(t in ("-i", "--login") for t in toks[1:]) and name in ("sudo", "login")


def parse_line(line: str) -> dict | None:
    """auth.log 한 줄을 구조화한다. 알 수 없는 줄은 None."""
    m = _SYSLOG_RE.match(line.strip())
    if not m:
        return None
    prog, msg = m.group("prog"), m.group("msg")
    sim = "[SIMULATION]" in line
    base = {"prog": prog, "raw": line.strip(), "simulation": sim}

    if prog in ("sshd", "sshd-session"):
        mm = _FAILED_RE.search(msg)
        if mm:
            return {**base, "kind": "invalid_user" if mm.group("invalid") else "auth_failure",
                    "user": mm.group("user"), "ip": mm.group("ip"), "method": mm.group("method")}
        mm = _INVALID_RE.search(msg)
        if mm:
            return {**base, "kind": "invalid_user", "user": mm.group("user") or "(빈 이름)", "ip": mm.group("ip"), "method": "unknown"}
        mm = _ACCEPTED_RE.search(msg)
        if mm:
            return {**base, "kind": "auth_success", "user": mm.group("user"), "ip": mm.group("ip"),
                    "method": mm.group("method"), "key": (mm.group("key") or "").strip()}
        mm = _MAXAUTH_RE.search(msg)
        if mm:
            return {**base, "kind": "auth_failure", "user": mm.group("user"), "ip": mm.group("ip"), "method": "max-attempts"}
        return None

    if prog == "sudo":
        mm = _SUDO_CMD_RE.match(msg)
        if mm:
            fail = mm.group("fail").strip()
            d = {**base, "user": mm.group("user"), "target": mm.group("target"), "command": mm.group("command").strip(), "tty": mm.group("tty"), "pwd": mm.group("pwd").strip()}
            if fail and ("incorrect password" in fail or "NOT in sudoers" in fail or "command not allowed" in fail or "not allowed" in fail):
                return {**d, "kind": "sudo_failure", "reason": fail}
            return {**d, "kind": "sudo_command"}
        mm = _SESSION_RE.search(msg)
        if mm and mm.group("user") == "root":
            return {**base, "kind": "root_session", "by": _resolve_by(mm), "via": "sudo"}
        return None

    if prog == "su":
        mm = _SESSION_RE.search(msg)
        if mm and mm.group("user") == "root":
            return {**base, "kind": "root_session", "by": _resolve_by(mm), "via": "su"}
        mm = re.search(r"\(to (?P<target>\S+)\) (?P<by>\S+) on", msg)
        if mm and mm.group("target") == "root":
            return {**base, "kind": "root_session", "by": mm.group("by"), "via": "su"}
        return None

    if prog in ("useradd", "userdel", "usermod", "gpasswd", "groupadd", "groupmod", "groupdel", "passwd", "chsh", "chage"):
        # direction: 권한 그룹에 '추가'는 침입 신호일 수 있고 '제거'는 대개 정리 작업이라 등급을 다르게 본다
        for rx, fmt, direction in (
            (_USERADD_RE, "새 사용자 생성: {user}", ""),
            (_USERDEL_RE, "사용자 삭제: {user}", ""),
            (_USERMOD_RE, "'{user}' 를 그룹 '{group}' 에 추가", "add"),
            (_USERMOD_DEL_RE, "'{user}' 를 그룹 '{group}' 에서 제거", "remove"),
            (_GPASSWD_ADD_RE, "'{user}' 를 그룹 '{group}' 에 추가", "add"),
            (_GPASSWD_DEL_RE, "'{user}' 를 그룹 '{group}' 에서 제거", "remove"),
            (_GROUPADD_RE, "새 그룹 생성: {group}", ""),
            (_GROUPDEL_RE, "그룹 삭제: {group}", ""),
            (_PASSWD_RE, "비밀번호 변경: {user}", ""),
        ):
            mm = rx.search(msg)
            if mm:
                gd = mm.groupdict()
                return {**base, "kind": "account_change", "user": gd.get("user"), "group": gd.get("group"),
                        "direction": direction,
                        "change": fmt.format(**{k: (v or "?") for k, v in gd.items()})}
        return None

    if prog in ("login", "gdm-password", "lightdm"):
        mm = _SESSION_RE.search(msg)
        if mm and mm.group("user") == "root":
            return {**base, "kind": "root_session", "by": _resolve_by(mm), "via": prog}
    return None


def is_private_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.replace("::ffff:", "") if ip.startswith("::ffff:") else ip)
    except ValueError:
        return False
    return addr.is_private or addr.is_loopback or addr.is_link_local


class AuthLogWatcher(BaseMonitor):
    name = "AuthLogWatcher"
    label = "SSH/인증 로그 감시"
    interval = 1

    def __init__(self, log_path: str | None = None, ban_manager_factory=None):
        super().__init__()
        self.log_path = log_path or config.AUTH_LOG_PATH
        self.source = self.log_path
        self._reader: TailReader | None = None
        self._failures: dict[str, deque] = defaultdict(deque)   # ip -> deque[(datetime, user)]
        self._ban_factory = ban_manager_factory
        self.window = timedelta(minutes=config.BRUTE_FORCE_WINDOW_MIN)
        self.threshold = config.BRUTE_FORCE_THRESHOLD

    # --- 수명 주기 ---
    def setup(self):
        self._seed_failures()
        self._try_open()

    def _try_open(self) -> bool:
        try:
            reader = TailReader(self.log_path)
            reader.open(seek_end=True)
            self._reader = reader
            self.set_health("ok")
            return True
        except FileNotFoundError:
            self._reader = None
            self.set_health("down", f"로그 파일 없음: {self.log_path}",
                            "rsyslog 가 설치되어 있는지 확인하거나 SECDASH_AUTH_LOG 로 경로를 지정하세요.")
        except PermissionError:
            self._reader = None
            self.set_health("down", f"로그 파일 읽기 권한 없음: {self.log_path}",
                            "서비스 계정을 adm 그룹에 추가하세요: sudo usermod -aG adm <계정> (재로그인 필요)")
        except Exception as e:
            self._reader = None
            self.set_health("down", f"로그 파일 열기 실패: {e}")
        return False

    def tick(self):
        if self._reader is None:
            if not self._try_open():
                return
        for _ in range(2000):   # 한 번에 너무 오래 잡지 않도록 상한
            line = self._reader.readline()
            if not line:
                break
            self.process_line(line)

    # --- 처리 ---
    def process_line(self, line: str):
        parsed = parse_line(line)
        if not parsed:
            return
        kind = parsed["kind"]
        sim = parsed["simulation"]
        handler = getattr(self, f"_on_{kind}", None)
        if handler:
            handler(parsed, sim)

    def _on_auth_failure(self, p: dict, sim: bool):
        d = {"user": p["user"], "ip": p["ip"], "method": p.get("method", "")}
        self.log_event("AUTH_FAILURE", "INFO", f"Failed {d['method']} for {d['user']} from {d['ip']}", d, is_simulation=sim)
        self._record_failure(p["ip"], p["user"], sim)

    def _on_invalid_user(self, p: dict, sim: bool):
        d = {"user": p["user"], "ip": p["ip"]}
        self.log_event("INVALID_USER", "INFO", f"Invalid user {d['user']} from {d['ip']}", d, is_simulation=sim)
        self._record_failure(p["ip"], p["user"], sim)

    def _record_failure(self, ip: str, user: str, sim: bool):
        now = utcnow()
        q = self._failures[ip]
        q.append((now, user))
        cutoff = now - self.window
        while q and q[0][0] < cutoff:
            q.popleft()
        count = len(q)
        if count < self.threshold:
            return
        users = sorted({u for _, u in q})
        raise_alert(
            "brute_force", "WARNING",
            f"Brute force from {ip}: {count} failures in {config.BRUTE_FORCE_WINDOW_MIN} min",
            fingerprint=f"brute_force:{ip}",
            title_ko=f"브루트포스 의심: {ip} 에서 {config.BRUTE_FORCE_WINDOW_MIN}분 내 {count}회 로그인 실패",
            summary_ko=f"시도한 계정: {', '.join(users[:10])}{' 외' if len(users) > 10 else ''}",
            action_ko="fail2ban 차단 여부를 차단 목록에서 확인하세요. 차단되지 않았다면 '차단 권고' 이벤트의 명령을 실행하세요. 시도된 계정이 실제 존재하면 해당 계정의 비밀번호 인증을 끄고 키 인증만 허용하는 것을 검토하세요.",
            evidence="\n".join(f"{t.strftime('%H:%M:%S')} {u}" for t, u in list(q)[-10:]),
            details={"ip": ip, "count": count, "users": users, "window_min": config.BRUTE_FORCE_WINDOW_MIN},
            is_simulation=sim,
        )
        if count == self.threshold or count % 25 == 0:
            self._ban(ip, f"브루트포스: {config.BRUTE_FORCE_WINDOW_MIN}분 내 {count}회 실패", sim)

    def _ban(self, ip: str, reason: str, sim: bool):
        try:
            from ban_manager import BanManager
            db = SessionLocal()
            try:
                manager = self._ban_factory(db) if self._ban_factory else BanManager(db)
                manager.ban_ip(ip, reason, is_simulation=sim)
            finally:
                db.close()
        except Exception as e:
            self.log.error(f"ban failed for {ip}: {e}")

    def _on_auth_success(self, p: dict, sim: bool):
        ip, user = p["ip"], p["user"]
        d = {"user": user, "ip": ip, "method": p.get("method", ""), "key": p.get("key", "")}
        self.log_event("AUTH_SUCCESS", "INFO", f"Accepted {d['method']} for {user} from {ip}", d, is_simulation=sim)

        # 규칙 1: 실패 이력이 있는 IP 에서 성공
        prior = [x for x in self._failures.get(ip, ()) if x[0] >= utcnow() - self.window]
        if prior:
            raise_alert(
                "login_after_failures", "CRITICAL",
                f"Successful login for {user} from {ip} after {len(prior)} failures",
                fingerprint=f"login_after_failures:{ip}:{user}",
                title_ko=f"실패 후 로그인 성공: {ip} 에서 {len(prior)}회 실패 뒤 '{user}' 로그인 성공",
                summary_ko=f"브루트포스가 성공했을 가능성이 있습니다. 인증 방식: {d['method']}",
                action_ko=f"즉시 해당 세션을 확인하세요: `who`, `last -a | head`. 본인이 아니면 `sudo pkill -KILL -u {user}` 후 비밀번호를 바꾸고 authorized_keys 를 점검하세요.",
                evidence=p["raw"],
                details=d | {"failures": len(prior)},
                is_simulation=sim,
            )

        # 규칙 2: root 직접 로그인
        if user == "root":
            raise_alert(
                "root_ssh_login", "WARNING", f"Direct root SSH login from {ip}",
                fingerprint=f"root_ssh_login:{ip}",
                title_ko=f"root 계정으로 SSH 직접 로그인 ({ip})",
                summary_ko="root 직접 로그인은 감사 추적을 어렵게 합니다.",
                action_ko="sshd_config 에 PermitRootLogin no (또는 prohibit-password) 를 설정하고 개인 계정 + sudo 를 사용하세요.",
                evidence=p["raw"], details=d, is_simulation=sim,
            )

        # 규칙 3: 처음 보는 IP
        if not sim:
            self._check_known_ip(ip, user, p["raw"], d)

    def _check_known_ip(self, ip: str, user: str, raw: str, d: dict):
        db = SessionLocal()
        try:
            row = db.query(KnownLoginIP).filter(KnownLoginIP.ip_address == ip).first()
            now = utcnow()
            if row:
                users = set(filter(None, (row.users or "").split(",")))
                users.add(user)
                row.users, row.last_seen, row.login_count = ",".join(sorted(users)), now, (row.login_count or 0) + 1
                db.commit()
                return
            db.add(KnownLoginIP(ip_address=ip, users=user, first_seen=now, last_seen=now, login_count=1))
            db.commit()
        finally:
            db.close()
        if is_private_ip(ip):
            return
        raise_alert(
            "new_login_ip", "WARNING", f"First login from new IP {ip} ({user})",
            fingerprint=f"new_login_ip:{ip}",
            title_ko=f"처음 보는 IP 에서 로그인 성공: {ip} ('{user}')",
            summary_ko="이 서버에 처음 로그인한 공인 IP 입니다. 본인 또는 동료의 접속인지 확인하세요.",
            action_ko="본인의 접속이면 확인(ack) 처리하세요. 아니라면 `who` 로 세션을 확인하고 즉시 종료 후 인증 정보를 교체하세요.",
            evidence=raw, details=d,
        )

    def _is_self(self, user: str, command: str = "") -> bool:
        """대시보드 자신의 fail2ban-client 호출은 이벤트로 남기지 않는다 (30초마다 발생)."""
        if not config.SELF_USER or user != config.SELF_USER:
            return False
        return (not command) or "fail2ban-client" in command

    def _on_sudo_command(self, p: dict, sim: bool):
        cmd = p["command"]
        if self._is_self(p["user"], cmd):
            self.log.debug(f"self sudo suppressed: {cmd[:80]}")
            return
        d = {"user": p["user"], "target": p["target"], "command": cmd, "tty": p.get("tty") or "", "pwd": p.get("pwd", "")}
        sev = "WARNING" if is_interactive_shell(cmd) else "INFO"
        self.log_event("SUDO_COMMAND", sev, f"sudo by {d['user']} as {d['target']}: {cmd}", d, is_simulation=sim)

    def _on_sudo_failure(self, p: dict, sim: bool):
        d = {"user": p["user"], "reason": p["reason"], "command": p.get("command", "")}
        self.log_event("SUDO_FAILURE", "WARNING", f"sudo failure for {d['user']}: {d['reason']}", d, is_simulation=sim)
        raise_alert(
            "sudo_failure", "WARNING", f"sudo failure: {d['user']} ({d['reason']})",
            fingerprint=f"sudo_failure:{d['user']}",
            title_ko=f"sudo 실패: '{d['user']}' — {d['reason']}",
            summary_ko=f"명령: {d['command'] or '(없음)'}",
            action_ko="해당 계정 사용자에게 본인 시도인지 확인하세요. 아니라면 계정이 탈취되었을 수 있으니 세션을 종료하고 비밀번호를 교체하세요.",
            evidence=p["raw"], details=d, is_simulation=sim,
        )

    def _on_root_session(self, p: dict, sim: bool):
        if p["via"] == "sudo" and self._is_self(p["by"]):
            return
        d = {"by": p["by"], "via": p["via"]}
        sev = "WARNING" if p["via"] == "su" else "INFO"
        self.log_event("ROOT_SESSION", sev, f"root session via {p['via']} by {p['by']}", d, is_simulation=sim)

    def _on_account_change(self, p: dict, sim: bool):
        group = p.get("group") or ""
        direction = p.get("direction", "")
        d = {"change": p["change"], "user": p.get("user"), "group": p.get("group"), "prog": p["prog"], "direction": direction}
        self.log_event("ACCOUNT_CHANGE", "WARNING", f"Account change ({p['prog']}): {p['change']}", d, is_simulation=sim)
        privileged = group in PRIVILEGED_GROUPS
        # 권한 그룹에서 '빼는' 것은 대개 정리 작업이다. 긴급으로 올리는 것은 '넣는' 경우뿐.
        escalation = privileged and direction != "remove"
        if escalation:
            summary_ko = f"'{group}' 는 root 와 동등한 권한을 가진 그룹입니다. 계획된 작업이 아니면 권한 상승입니다."
            action_ko = f"예정된 작업이면 확인(ack) 처리하세요. 아니라면 `sudo gpasswd -d {p.get('user') or '<계정>'} {group}` 으로 되돌리고, 누가 실행했는지 sudo 이벤트에서 확인하세요."
        elif privileged:
            summary_ko = f"권한 그룹 '{group}' 에서 제외되었습니다. 권한 축소 방향의 변경입니다."
            action_ko = "의도한 정리 작업이면 확인(ack) 처리하세요. 아니라면 해당 계정의 작업이 중단되지 않는지 확인하세요."
        else:
            summary_ko = "예정된 관리 작업인지 확인하세요."
            action_ko = "예정된 작업이면 확인(ack) 처리하세요. 아니라면 `sudo userdel -r <계정>` 또는 `sudo gpasswd -d <계정> <그룹>` 으로 되돌리고 원인을 조사하세요."
        raise_alert(
            "account_change", "CRITICAL" if escalation else "WARNING", f"Account change: {p['change']}",
            fingerprint=f"account_change:{p['prog']}:{p.get('user') or p.get('group')}:{direction or 'na'}",
            title_ko=f"계정 변경: {p['change']}",
            summary_ko=summary_ko,
            action_ko=action_ko,
            evidence=p["raw"], details=d, is_simulation=sim,
        )

    # --- 시작 시 최근 실패 이력 복원 ---
    def _seed_failures(self):
        db = SessionLocal()
        try:
            since = utcnow() - self.window
            rows = db.query(Event).filter(
                Event.event_type.in_(["AUTH_FAILURE", "INVALID_USER"]),
                Event.timestamp >= since,
                Event.is_simulation == False,  # noqa: E712
            ).all()
            for e in rows:
                d = e.details_dict()
                if d.get("ip"):
                    self._failures[d["ip"]].append((e.timestamp, d.get("user", "?")))
        except Exception as ex:
            self.log.error(f"seed failures failed: {ex}")
        finally:
            db.close()


# --- 네트워크 감시 ---------------------------------------------------------
# 대형 CDN/클라우드 경로. /8 단위 화이트리스트는 공격자 VM 도 숨기므로 쓰지 않는다.
_CLOUD_CIDRS = [
    "142.250.0.0/15", "142.251.0.0/16", "172.217.0.0/16", "216.239.32.0/19", "74.125.0.0/16",
    "140.82.112.0/20", "143.55.64.0/20",                     # GitHub
    "104.16.0.0/13", "104.24.0.0/14", "162.158.0.0/15",     # Cloudflare
    "151.101.0.0/16", "146.75.0.0/16",                       # Fastly
    "185.125.188.0/22",                                      # Canonical
    "99.84.0.0/16", "13.224.0.0/14", "52.84.0.0/15",         # CloudFront
]
_CLOUD_NETWORKS = [ipaddress.ip_network(c) for c in _CLOUD_CIDRS]


def is_cloud_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in _CLOUD_NETWORKS)
    except ValueError:
        return False


def _proc_info(pid: int | None) -> dict:
    if not pid:
        return {"process": None, "exe": None, "user": None}
    try:
        p = psutil.Process(pid)
        with p.oneshot():
            info = {"process": p.name(), "user": None, "exe": None, "pid": pid}
            try:
                info["user"] = p.username()
            except Exception:
                pass
            try:
                info["exe"] = p.exe()
            except Exception:
                info["exe"] = " ".join(p.cmdline()[:3]) if p.cmdline() else None
            return info
    except Exception:
        return {"process": None, "exe": None, "user": None, "pid": pid}


class NetworkWatcher(BaseMonitor):
    name = "NetworkWatcher"
    label = "네트워크 연결 감시"
    interval = 15
    SCAN_THRESHOLD = 5
    EPHEMERAL_START = 32768

    def __init__(self, interval: int | None = None):
        super().__init__(interval)
        self.source = "psutil.net_connections (/proc/net)"
        self.known_listeners: set[str] = set()
        self.seen_remote_ips: set[str] = set()
        self._scan_tracker: dict[str, set[int]] = {}
        self._scan_alerted: set[str] = set()

    def setup(self):
        db = SessionLocal()
        try:
            self.known_listeners = {r.key for r in db.query(KnownListener).all()}
        finally:
            db.close()
        # 시작 시점의 리스너는 기준선으로 조용히 등록
        try:
            conns = psutil.net_connections(kind="inet")
        except psutil.AccessDenied:
            self.set_health("degraded", "소켓 목록 접근 거부", "서비스를 root 또는 CAP_NET_ADMIN 권한으로 실행하세요.")
            return
        missing_pid = False
        for c in conns:
            if c.status == "LISTEN" and c.laddr:
                if c.pid is None:
                    missing_pid = True
                self._remember_listener(c, silent=True)
            elif c.status == "ESTABLISHED" and c.raddr:
                self.seen_remote_ips.add(c.raddr.ip)
        if missing_pid and os.geteuid() != 0:
            self.set_health("degraded", "다른 사용자 프로세스의 소켓은 프로세스 정보를 알 수 없음",
                            "정확한 프로세스 귀속을 위해 deploy/secdash.service 처럼 CAP_NET_ADMIN/CAP_SYS_PTRACE 를 부여하세요.")

    @staticmethod
    def _listener_key(c, info: dict) -> str:
        return f"{c.laddr.ip}:{c.laddr.port}/{info.get('process') or '?'}"

    def _remember_listener(self, c, silent: bool):
        info = _proc_info(c.pid)
        key = self._listener_key(c, info)
        if key in self.known_listeners:
            return
        self.known_listeners.add(key)
        db = SessionLocal()
        try:
            if not db.query(KnownListener).filter(KnownListener.key == key).first():
                db.add(KnownListener(key=key, port=c.laddr.port, address=c.laddr.ip, process=info.get("process")))
                db.commit()
        finally:
            db.close()
        if silent:
            return
        loopback = c.laddr.ip in ("127.0.0.1", "::1")
        d = {"address": c.laddr.ip, "port": c.laddr.port, **info}
        if loopback:
            self.log_event("NETWORK_LISTENER", "INFO", f"New loopback listener {c.laddr.ip}:{c.laddr.port} ({info.get('process')})", d)
            return
        self.log_event("NETWORK_LISTENER", "WARNING", f"New listener {c.laddr.ip}:{c.laddr.port} ({info.get('process')}, user {info.get('user')})", d)
        raise_alert(
            "new_listener", "WARNING", f"New listening port {c.laddr.port} ({info.get('process') or 'unknown'})",
            fingerprint=f"listener:{c.laddr.port}:{info.get('process') or '?'}",
            title_ko=f"새 리스닝 포트 {c.laddr.port} 열림 ({info.get('process') or '알 수 없는 프로세스'})",
            summary_ko=f"바인드 주소 {c.laddr.ip}, 실행 파일 {info.get('exe') or '?'}, 사용자 {info.get('user') or '?'}",
            action_ko=f"의도한 서비스면 확인(ack) 처리하세요. 아니라면 `sudo ss -ltnp | grep :{c.laddr.port}` 로 프로세스를 확인하고 종료한 뒤 방화벽에서 포트를 막으세요.",
            details=d,
        )

    def tick(self):
        try:
            conns = psutil.net_connections(kind="inet")
        except psutil.AccessDenied:
            self.set_health("degraded", "소켓 목록 접근 거부", "root 또는 CAP_NET_ADMIN 권한이 필요합니다.")
            return
        scan_now: dict[str, set[int]] = defaultdict(set)
        for c in conns:
            if c.status == "LISTEN" and c.laddr:
                self._remember_listener(c, silent=False)
                continue
            if not c.raddr:
                continue
            rip = c.raddr.ip.replace("::ffff:", "")
            if is_private_ip(rip):
                continue
            lport = c.laddr.port if c.laddr else 0
            if c.status in ("SYN_RECV", "ESTABLISHED") and lport < self.EPHEMERAL_START:
                scan_now[rip].add(lport)
            if c.status == "ESTABLISHED" and rip not in self.seen_remote_ips:
                self.seen_remote_ips.add(rip)
                info = _proc_info(c.pid)
                d = {"ip": rip, "port": c.raddr.port, "local_port": lport, **info}
                desc = f"New external connection {rip}:{c.raddr.port} by {info.get('process') or 'unknown'}"
                if (info.get("process") or "").lower() in config.NETWORK_IGNORE_PROCESSES:
                    self.log.info(f"[ignored-process] {desc}")
                elif is_cloud_ip(rip):
                    self.log.info(f"[cloud] {desc}")
                else:
                    self.log_event("NETWORK_CONN", "INFO", desc, d)

        for rip, ports in scan_now.items():
            combined = self._scan_tracker.get(rip, set()) | ports
            if len(combined) >= self.SCAN_THRESHOLD and rip not in self._scan_alerted:
                self._scan_alerted.add(rip)
                d = {"ip": rip, "port_count": len(combined), "ports": sorted(combined)}
                self.log_event("PORT_SCAN", "WARNING", f"Possible port scan from {rip}: {sorted(combined)}", d)
                raise_alert(
                    "port_scan", "WARNING", f"Possible port scan from {rip}",
                    fingerprint=f"port_scan:{rip}",
                    title_ko=f"포트 스캔 의심: {rip} 이(가) 서비스 포트 {len(combined)}개 접촉",
                    summary_ko=f"접촉 포트: {sorted(combined)}. ESTABLISHED/SYN_RECV 기반 휴리스틱이라 신뢰도는 낮습니다.",
                    action_ko="정상 클라이언트(모니터링, 로드밸런서)일 수 있습니다. 아니라면 fail2ban 으로 차단하세요.",
                    details=d,
                )
            self._scan_tracker[rip] = combined
        # 이번 주기에 보이지 않은 IP 는 추적 해제
        for rip in list(self._scan_tracker):
            if rip not in scan_now:
                self._scan_tracker.pop(rip, None)
                self._scan_alerted.discard(rip)
