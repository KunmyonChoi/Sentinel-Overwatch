"""
계정 상태 조회: 잠김/만료, 권한 그룹, 마지막 로그인, SSH 키 보유.
/etc/shadow 는 서비스의 CAP_DAC_READ_SEARCH 로 읽는다. 읽을 수 없으면 shadow 항목은 None 으로 표시한다.
"""
import datetime
import grp
import os
import re
import shutil
import subprocess

PRIVILEGED_GROUPS = ("sudo", "wheel", "admin", "root", "docker", "adm", "lxd", "disk", "shadow")
UID_MIN, UID_MAX = 1000, 60000
NOLOGIN_SHELLS = ("/usr/sbin/nologin", "/sbin/nologin", "/bin/false", "/usr/bin/false")


def _parse_passwd(path: str) -> list[dict]:
    rows = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                p = line.rstrip("\n").split(":")
                if len(p) < 7:
                    continue
                try:
                    uid = int(p[2])
                except ValueError:
                    continue
                rows.append({"name": p[0], "uid": uid, "gid": p[3], "gecos": p[4].split(",")[0], "home": p[5], "shell": p[6]})
    except OSError:
        pass
    return rows


def _parse_shadow(path: str) -> dict[str, dict] | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            out = {}
            for line in f:
                p = line.rstrip("\n").split(":")
                if len(p) < 8:
                    continue
                hashv = p[1]
                out[p[0]] = {
                    "password_locked": hashv.startswith("!") or hashv in ("*", "!!", "!*", ""),
                    "no_password": hashv == "" or hashv in ("*", "!!", "!*"),
                    "expire_days": int(p[7]) if p[7].strip().isdigit() else None,
                    "max_days": int(p[4]) if p[4].strip().isdigit() else None,
                }
            return out
    except OSError:
        return None


def _groups_of(name: str, primary_gid: str) -> list[str]:
    groups = set()
    try:
        groups.add(grp.getgrgid(int(primary_gid)).gr_name)
    except (KeyError, ValueError):
        pass
    for g in grp.getgrall():
        if name in g.gr_mem:
            groups.add(g.gr_name)
    return sorted(groups)


_LASTLOG_RE = re.compile(r"^(?P<user>\S+)\s+(?P<tty>\S+)?\s*(?P<host>\S+)?\s+(?P<when>\*\*Never logged in\*\*|[A-Z][a-z]{2}\s+[A-Z][a-z]{2}\s+\d+\s+[\d:]+\s+\S+\s+\d{4})")


def lastlog_all() -> dict[str, dict]:
    """lastlog 출력 파싱 → {user: {when, host}}"""
    if not shutil.which("lastlog"):
        return {}
    try:
        out = subprocess.run(["lastlog"], capture_output=True, text=True, timeout=10, env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"}).stdout
    except Exception:
        return {}
    result = {}
    for line in out.splitlines()[1:]:
        parts = line.split()
        if not parts:
            continue
        user = parts[0]
        if "Never logged in" in line:
            result[user] = {"when": None, "host": None}
            continue
        # 형식: user tty host Mon Sep 15 15:38:38 +0900 2025  (tty/host 는 없을 수 있음)
        m = re.search(r"([A-Z][a-z]{2}\s+[A-Z][a-z]{2}\s+\d+\s+[\d:]+\s+[+-]\d{4}\s+\d{4})$", line)
        when = None
        if m:
            try:
                when = datetime.datetime.strptime(m.group(1), "%a %b %d %H:%M:%S %z %Y").isoformat()
            except ValueError:
                when = m.group(1)
        middle = parts[1:-6] if m else parts[1:]
        host = middle[-1] if len(middle) >= 2 else None
        result[user] = {"when": when, "host": host}
    return result


def list_accounts(passwd_path: str = "/etc/passwd", shadow_path: str = "/etc/shadow", lastlog: dict | None = None) -> dict:
    shadow = _parse_shadow(shadow_path)
    lastlog = lastlog_all() if lastlog is None else lastlog
    today = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)).days
    accounts = []
    for row in _parse_passwd(passwd_path):
        is_root = row["uid"] == 0
        human = UID_MIN <= row["uid"] < UID_MAX
        if not (is_root or human):
            continue
        sh = (shadow or {}).get(row["name"])
        expired = bool(sh and sh["expire_days"] is not None and sh["expire_days"] <= today)
        locked = bool(sh and sh["password_locked"])
        if sh is None:
            state, state_ko = "unknown", "확인 불가"
        elif expired:
            state, state_ko = "locked", "잠김 (만료)"
        elif locked and row["shell"] in NOLOGIN_SHELLS:
            state, state_ko = "disabled", "로그인 불가"
        elif locked:
            state, state_ko = "locked", "잠김"
        else:
            state, state_ko = "active", "활성"
        keys = os.path.join(row["home"], ".ssh", "authorized_keys")
        try:
            has_keys = os.path.getsize(keys) > 0
        except OSError:
            has_keys = False
        groups = _groups_of(row["name"], row["gid"])
        ll = lastlog.get(row["name"], {})
        accounts.append({
            "name": row["name"], "uid": row["uid"], "gecos": row["gecos"], "shell": row["shell"],
            "state": state, "state_ko": state_ko, "password_locked": locked, "expired": expired,
            "privileged_groups": [g for g in groups if g in PRIVILEGED_GROUPS],
            "groups": groups,
            "has_ssh_keys": has_keys,
            "last_login": ll.get("when"), "last_login_host": ll.get("host"),
            "password_max_days": sh["max_days"] if sh else None,
            "commands": {
                "lock": f"sudo usermod -L -e 1 {row['name']}",
                "unlock": f"sudo usermod -U -e '' {row['name']}",
            },
        })
    accounts.sort(key=lambda a: (a["uid"] != 0, a["state"] != "active", a["name"]))
    return {"shadow_readable": shadow is not None, "accounts": accounts}
