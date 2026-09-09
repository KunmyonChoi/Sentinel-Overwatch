"""
방화벽(ufw / iptables) 상태 조회. "어떤 포트가 외부에서 열려 있는가" 의 진실 원천이다.

ufw 조회에는 root 권한이 필요하므로, root 가 아니면 sudo -n 으로 호출한다.
deploy/sudoers-secdash 에 허용 명령을 정의해 두어야 한다 (fail2ban-client 와 같은 방식).

원칙: 조용히 실패하지 않는다.
방화벽을 못 읽었을 때 빈 규칙 목록을 돌려주면 "아무것도 열려 있지 않다" 로 오해된다.
그런 경우 available=False 와 함께 사유/해결 힌트를 반드시 채운다.
"""
import logging
import os
import re
import shutil
import subprocess

logger = logging.getLogger("firewall")

UFW_BIN = "/usr/sbin/ufw"
IPTABLES_BIN = "/usr/sbin/iptables"

_ENV = {"LANG": "C", "LC_ALL": "C", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"}
_TIMEOUT = 10

# 포트 범위를 개별 포트로 펼치는 한계. 이보다 넓으면 '전체 포트'(None) 로 본다.
# 과소 보고(닫힌 것처럼 보이기) 보다 과대 보고가 안전하기 때문이다.
_MAX_RANGE_EXPAND = 1024

# ufw 애플리케이션 프로파일 중 확실한 것만 포트로 환원한다. 나머지는 port=None + raw 보존.
_APP_PROFILES: dict[str, list[tuple[int, str]]] = {
    "openssh": [(22, "tcp")],
    "ssh": [(22, "tcp")],
    "www": [(80, "tcp")],
    "www full": [(80, "tcp"), (443, "tcp")],
    "www secure": [(443, "tcp")],
    "nginx http": [(80, "tcp")],
    "nginx https": [(443, "tcp")],
    "nginx full": [(80, "tcp"), (443, "tcp")],
    "apache": [(80, "tcp")],
    "apache full": [(80, "tcp"), (443, "tcp")],
    "apache secure": [(443, "tcp")],
}

# "22/tcp   ALLOW IN   Anywhere (v6)" 에서 액션 토큰을 찾는다.
_ACTION_RE = re.compile(r"\b(ALLOW|DENY|REJECT|LIMIT)(?:\s+(IN|OUT|FWD))?\b")
_DEFAULT_RE = re.compile(r"\b(deny|allow|reject|disabled)\s*\(incoming\)", re.IGNORECASE)
_STATUS_RE = re.compile(r"^Status:\s*(\S+)", re.IGNORECASE)
_NUM_PREFIX_RE = re.compile(r"^\[\s*\d+\s*\]\s*")


# --- 순수 파싱 (subprocess 와 분리해 테스트 가능하게 둔다) ---
def _norm_proto(proto: str) -> str:
    p = proto.strip().lower()
    return p if p in ("tcp", "udp") else "any"


def _norm_action(action: str) -> str:
    a = action.strip().upper()
    # LIMIT 은 속도 제한이 붙은 허용이다. 도달 가능하다는 점에서 ALLOW 로 본다 (원문은 raw 에 남는다).
    if a in ("ALLOW", "LIMIT", "ACCEPT"):
        return "ALLOW"
    if a in ("DENY", "DROP"):
        return "DENY"
    if a == "REJECT":
        return "REJECT"
    return a


def _parse_port_token(token: str) -> list[tuple[int | None, str]]:
    """'22/tcp' → [(22,'tcp')], '6000:6007/tcp' → 범위 전개, 'OpenSSH' → 프로파일 환원, 그 외 → [(None, proto)]"""
    token = (token or "").strip()
    if not token:
        return [(None, "any")]
    proto = "any"
    base = token
    if "/" in token:
        head, _, tail = token.rpartition("/")
        if _norm_proto(tail) != "any":
            base, proto = head, _norm_proto(tail)
    base = base.strip()

    out: list[tuple[int | None, str]] = []
    for part in [p.strip() for p in base.split(",") if p.strip()]:
        if part.isdigit():
            out.append((int(part), proto))
            continue
        m = re.fullmatch(r"(\d+):(\d+)", part)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if 0 < lo <= hi <= 65535 and (hi - lo + 1) <= _MAX_RANGE_EXPAND:
                out.extend((p, proto) for p in range(lo, hi + 1))
            else:
                # 너무 넓은 범위는 '전체 포트' 로 취급한다
                out.append((None, proto))
            continue
        ports = _APP_PROFILES.get(part.lower())
        if ports:
            out.extend((p, pr if proto == "any" else proto) for p, pr in ports)
        else:
            # 숫자로 환원할 수 없는 이름 있는 서비스 → port None, raw 는 보존된다
            out.append((None, proto))
    return out or [(None, proto)]


def _mk_rules(to_field: str, action: str, from_field: str, raw: str) -> list[dict]:
    v6 = "(v6)" in to_field or "(v6)" in from_field
    to_clean = to_field.replace("(v6)", "").strip()
    from_clean = from_field.strip() or "Anywhere"
    return [
        {"port": port, "proto": proto, "action": action, "from": from_clean,
         "to": to_clean, "v6": v6, "raw": raw}
        for port, proto in _parse_port_token(to_clean)
    ]


def parse_ufw_status(text: str) -> dict:
    """`ufw status verbose` 출력 파싱."""
    result: dict = {"active": False, "default_incoming": "", "rules": []}
    for raw_line in (text or "").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        m = _STATUS_RE.match(stripped)
        if m:
            result["active"] = m.group(1).lower() == "active"
            continue
        if stripped.lower().startswith("default:"):
            d = _DEFAULT_RE.search(stripped)
            if d:
                val = d.group(1).lower()
                # disabled (routed) 같은 값은 incoming 정책이 아니므로 걸러진다
                result["default_incoming"] = val if val in ("deny", "allow", "reject") else ""
            continue
        if stripped.lower().startswith(("logging:", "new profiles:")):
            continue
        # 헤더("To  Action  From") 와 구분선("--  ------  ----")
        if re.match(r"^-+\s+-+", stripped) or re.match(r"^To\s+Action\s+From$", stripped, re.IGNORECASE):
            continue

        body = _NUM_PREFIX_RE.sub("", stripped)  # `ufw status numbered` 의 "[ 1]" 접두사 제거
        m = _ACTION_RE.search(body)
        if not m:
            continue
        direction = (m.group(2) or "IN").upper()
        if direction != "IN":
            continue  # OUT/FWD 규칙은 외부 도달성과 무관하다
        to_field = body[:m.start()].strip()
        from_field = body[m.end():].strip()
        if not to_field:
            continue
        result["rules"].extend(_mk_rules(to_field, _norm_action(m.group(1)), from_field, stripped))
    return result


def parse_iptables_save(text: str) -> dict:
    """`iptables-save` 또는 `iptables -S` 출력에서 INPUT 정책과 허용 포트만 뽑는다 (ufw 가 없을 때 폴백)."""
    result: dict = {"default_incoming": "", "rules": []}
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        # 기본 정책: ":INPUT DROP [0:0]" (iptables-save) 또는 "-P INPUT DROP" (iptables -S)
        m = re.match(r"^(?::INPUT|-P\s+INPUT)\s+(ACCEPT|DROP|REJECT)\b", line)
        if m:
            policy = m.group(1).upper()
            result["default_incoming"] = "allow" if policy == "ACCEPT" else "deny"
            continue

        if not re.match(r"^-A\s+INPUT\b", line):
            continue
        # 루프백 허용과 기존 연결(ESTABLISHED) 허용은 '외부에서 새로 도달 가능한 포트' 가 아니다
        if re.search(r"(?:-i|--in-interface)\s+lo\b", line) or "ESTABLISHED" in line:
            continue
        t = re.search(r"-j\s+(ACCEPT|DROP|REJECT)\b", line)
        if not t:
            continue
        action = _norm_action(t.group(1))
        p = re.search(r"-p\s+(\S+)", line)
        proto = _norm_proto(p.group(1)) if p else "any"
        s = re.search(r"(?:-s|--source)\s+(\S+)", line)
        from_field = s.group(1) if s else "Anywhere"

        d = re.search(r"--dports?\s+(\S+)", line)
        if d:
            token = d.group(1)  # multiport 는 "22,80", 범위는 "6000:6007"
            entries = _parse_port_token(f"{token}/{proto}" if proto != "any" else token)
        else:
            entries = [(None, proto)]
        result["rules"].extend(
            {"port": port, "proto": pr, "action": action, "from": from_field,
             "to": "Anywhere" if port is None else str(port), "v6": False, "raw": line}
            for port, pr in entries
        )
    return result


def _allowed_ports(rules: list[dict]) -> list[dict]:
    """규칙을 위에서부터 적용해 (포트, 프로토콜) 별 첫 판정을 취한다. 허용된 것만 돌려준다."""
    decided: dict[tuple[int, str], str] = {}
    for rule in rules:
        port = rule.get("port")
        if port is None:
            continue  # 전체 포트 규칙은 개별 포트 목록으로 환원하지 않는다 (port_reachable 이 처리)
        protos = ("tcp", "udp") if rule.get("proto") == "any" else (rule.get("proto"),)
        for proto in protos:
            if proto not in ("tcp", "udp"):
                continue
            decided.setdefault((int(port), proto), rule.get("action", ""))
    return [{"port": p, "proto": pr} for (p, pr), act in sorted(decided.items()) if act == "ALLOW"]


def port_reachable(snapshot: dict, port: int, proto: str = "tcp") -> bool | None:
    """True=허용됨, False=차단됨, None=판단 불가(방화벽 상태를 못 읽음)."""
    if not snapshot or not snapshot.get("available"):
        return None
    proto = _norm_proto(proto)
    if snapshot.get("backend") == "ufw" and not snapshot.get("active"):
        return True  # ufw 가 꺼져 있으면 필터링이 없다
    rules = snapshot.get("rules") or []
    # 포트를 명시한 규칙을 먼저 본다. port=None(전체 포트 / 숫자로 환원 못 한 서비스)은
    # 불확실한 규칙이므로, 해당 포트를 정확히 가리키는 규칙이 있으면 그쪽을 따른다.
    for concrete_only in (True, False):
        for rule in rules:
            r_port = rule.get("port")
            if concrete_only and r_port is None:
                continue
            r_proto = rule.get("proto", "any")
            if r_proto != "any" and proto != "any" and r_proto != proto:
                continue
            if r_port is not None and int(r_port) != int(port):
                continue
            return rule.get("action") == "ALLOW"  # 같은 등급에서는 먼저 매치되는 규칙이 이긴다
    # rules 를 싣지 않은 요약 스냅샷(API 로 내보내는 형태는 allowed 만 갖는다)도 판정할 수 있게 한다.
    for entry in snapshot.get("allowed") or []:
        try:
            if int(entry.get("port")) != int(port):
                continue
        except (TypeError, ValueError):
            continue
        e_proto = _norm_proto(entry.get("proto", "any"))
        if e_proto == "any" or proto == "any" or e_proto == proto:
            return True
    default = (snapshot.get("default_incoming") or "").lower()
    if default in ("deny", "reject"):
        return False
    if default == "allow":
        return True
    return None  # 기본 정책조차 못 읽었으면 단정하지 않는다


class FirewallClient:
    def __init__(self, use_sudo: bool | None = None, ufw_bin: str = UFW_BIN, iptables_bin: str = IPTABLES_BIN):
        # root 가 아니면 sudo -n 으로 호출한다 (deploy/sudoers-secdash 참고)
        self.use_sudo = (os.geteuid() != 0) if use_sudo is None else use_sudo
        self.ufw_bin = ufw_bin
        self.iptables_bin = iptables_bin
        self._last_error = ""

    # --- 저수준 실행 ---
    def _cmd(self, *args: str) -> list[str]:
        if self.use_sudo:
            return ["sudo", "-n", *args]
        return list(args)

    def _which(self, path: str, name: str) -> str:
        return shutil.which(path) or shutil.which(name) or ""

    def _run(self, *args: str, timeout: int = _TIMEOUT) -> tuple[int, str]:
        try:
            proc = subprocess.run(
                self._cmd(*args), capture_output=True, text=True, timeout=timeout, env=_ENV,
            )
        except FileNotFoundError as e:
            self._last_error = str(e)
            return 127, ""
        except subprocess.TimeoutExpired:
            self._last_error = "방화벽 명령 응답 시간 초과"
            return 124, ""
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            self._last_error = out.strip().splitlines()[-1] if out.strip() else f"rc={proc.returncode}"
        return proc.returncode, out

    def _classify(self, tool: str, err: str, sudoers_cmd: str) -> tuple[str, str]:
        """(사유, 해결 힌트). fail2ban.py 의 availability() 와 같은 방식으로 실패 원인을 구분한다."""
        hint_sudoers = (f"deploy/sudoers-secdash 에 {sudoers_cmd} 를 추가해 sudo -n 으로 허용하고, "
                        "systemd 유닛의 권한 설정을 확인하세요.")
        if "password is required" in err or "sudo:" in err:
            return f"{tool} 조회 권한 없음 (sudo 실패: {err[:120]})", hint_sudoers
        if "You need to be root" in err or "root 권한" in err or "must be root" in err.lower():
            return f"{tool} 조회에 root 권한이 필요함", hint_sudoers
        if "Permission denied" in err:
            return f"{tool} 접근 권한 없음", hint_sudoers
        if "No such file or directory" in err or "command not found" in err:
            return f"{tool} 명령을 실행할 수 없음 ({err[:120]})", f"{tool} 설치 경로를 확인하세요."
        return f"{tool} 오류: {err}", hint_sudoers

    # --- 상태 ---
    def _probe(self) -> tuple[str, str, str, str]:
        """(backend, 출력, 사유, 해결 힌트). backend 가 빈 문자열이면 읽기 실패."""
        ufw = self._which(self.ufw_bin, "ufw")
        ufw_reason, ufw_hint = "", ""
        if ufw:
            rc, out = self._run(ufw, "status", "verbose")
            if rc == 0 and "Status:" in out:
                return "ufw", out, "", ""
            ufw_reason, ufw_hint = self._classify(
                "ufw", self._last_error, f"{ufw} status verbose")
        else:
            ufw_reason = "ufw 미설치"
            ufw_hint = "sudo apt install ufw 후 sudo ufw enable 로 활성화하세요."

        # ufw 를 못 쓰면 iptables 로 폴백한다
        iptables = self._which(self.iptables_bin, "iptables")
        if not iptables:
            hint = ufw_hint or "sudo apt install ufw 후 sudo ufw enable 로 활성화하세요."
            return "", "", f"{ufw_reason} / iptables 도 없음", hint
        rc, out = self._run(iptables, "-S")
        if rc == 0 and out.strip():
            return "iptables", out, "", ""
        ipt_reason, ipt_hint = self._classify("iptables", self._last_error, f"{iptables} -S")
        if ufw:
            # ufw 는 설치돼 있는데 못 읽은 경우 → ufw 쪽 사유가 더 유용하다
            return "", "", ufw_reason, ufw_hint
        return "", "", ipt_reason, ipt_hint

    def availability(self) -> tuple[bool, str, str]:
        """(사용 가능 여부, 사유, 해결 힌트)"""
        backend, _out, reason, hint = self._probe()
        return bool(backend), reason, hint

    def snapshot(self) -> dict:
        """JSON 직렬화 가능한 방화벽 상태 스냅샷."""
        result: dict = {
            "available": False, "backend": "", "active": False, "default_incoming": "",
            "rules": [], "allowed": [], "reason": "", "fix_hint": "",
        }
        backend, out, reason, hint = self._probe()
        if not backend:
            # 규칙을 못 읽었을 때 빈 목록을 '아무것도 열려 있지 않음' 으로 오해하지 않도록 사유를 남긴다
            result["reason"] = reason or "방화벽 상태를 읽을 수 없음"
            result["fix_hint"] = hint
            logger.warning(f"방화벽 상태 조회 실패: {result['reason']}")
            return result

        if backend == "ufw":
            parsed = parse_ufw_status(out)
            result["active"] = bool(parsed["active"])
        else:
            parsed = parse_iptables_save(out)
            result["active"] = True  # iptables 는 활성/비활성 개념이 없다. 정책이 곧 상태다.
        result["available"] = True
        result["backend"] = backend
        result["default_incoming"] = parsed.get("default_incoming", "")
        result["rules"] = parsed.get("rules", [])
        result["allowed"] = _allowed_ports(result["rules"])

        if backend == "ufw" and not result["active"]:
            result["reason"] = "ufw 방화벽이 비활성 상태 (모든 포트가 외부에 열려 있음)"
            result["fix_hint"] = "sudo ufw default deny incoming && sudo ufw allow OpenSSH && sudo ufw enable"
        elif result["default_incoming"] == "allow":
            result["reason"] = "들어오는 연결의 기본 정책이 allow (거부 규칙이 없는 포트는 모두 열림)"
            result["fix_hint"] = "sudo ufw default deny incoming 으로 기본 정책을 거부로 바꾸세요."
        return result
