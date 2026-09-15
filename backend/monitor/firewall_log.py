"""
방화벽 로그 감시(FirewallLogWatcher).

ufw 가 막은 패킷 기록(/var/log/ufw.log 의 [UFW BLOCK] 줄)으로 포트 스캔을 본다.
NetworkWatcher 의 소켓 표 휴리스틱은 닫힌 포트나 방화벽이 막은 포트로 오는 SYN 을 볼 수 없다
(소켓이 생기지 않는다). 커널이 막으면서 남긴 기록에는 그게 남는다.

원칙
  - 스캔 자체는 사실(이벤트)이다. 인터넷에 열린 서버는 하루에도 여러 번 스캔당한다. 그걸 전부 알림으로
    올리면 알림을 안 보게 된다. 그래서 스캔은 INFO 이벤트와 하루 요약으로만 남긴다.
  - 알림(경고)은 스캔 '다음에' 관련 행동이 이어졌을 때만 올린다.
      a) 스캔한 IP 가 SSH 로그인을 시도하거나 성공했다       (AuthLogWatcher 가 note_auth_activity 로 알린다)
      b) 스캔한 IP 가 이 서버의 리스닝 포트에 실제로 연결했다 (NetworkWatcher 가 note_connection 으로 알린다)
      c) 내부망(사설 대역) 주소가 스캔했다 — 같은 네트워크의 기기가 감염됐을 수 있어 스캔만으로 경고한다
    '실패 후 로그인 성공'은 AuthLogWatcher 가 이미 긴급으로 올린다. 여기서 또 올리지 않고 그 알림에 스캔 정황만 붙인다.
  - 차단하지 않는다. 판단 근거와 명령만 준다.
  - ufw 는 차단 기록을 속도 제한해 남긴다(logging low~high: 분당 3건, 한 번에 10건까지 — 모든 IP 합산).
    숫자는 모두 '최소치'이고, 동시에 여러 곳에서 두드리면 스캔을 놓칠 수도 있다.

스캔한 IP 목록(ScanRegistry)은 이 프로세스 안에서 세 모니터가 함께 본다. 재시작하면 DB 의 FIREWALL_SCAN
이벤트로 되찾는다. 시작할 때는 AuthLogWatcher 와 같이 파일 끝에서 읽기 시작하고(지난 기록은 읽지 않는다),
로테이션된 새 파일은 처음부터 읽는다.
"""
import ipaddress
import json
import logging
import os
import re
import threading
import time
from collections import Counter, OrderedDict, deque
from datetime import date, datetime, timedelta, timezone

import config
from alerts import raise_alert
from database import Alert, Event, SessionLocal, utcnow
from iplist import find_network, normalize_ip, parse_ip_list
from monitor.base import BaseMonitor, TailReader

logger = logging.getLogger("firewall_log")

LOWER_BOUND_KO = ("ufw 는 차단 기록을 속도 제한해 남기므로(분당 3건, 한 번에 10건까지) "
                  "숫자는 실제보다 적을 수 있는 최소치입니다.")
NOT_BLOCKED_KO = "대시보드는 이 IP 를 자동으로 차단하지 않았습니다."

# --- 줄 파서 ----------------------------------------------------------------
_MONTHS = {m: i for i, m in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}
_TRAD_TS_RE = re.compile(r"^(?P<mon>[A-Z][a-z]{2})\s+(?P<day>\d{1,2})\s+(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2})\s")
_ISO_TS_RE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s")
_UFW_TAG_RE = re.compile(r"\[UFW (?P<action>[A-Z][A-Z ]*?)\]")
_KV_RE = re.compile(r"^(?P<k>[A-Z0-9]+)=(?P<v>\S*)$")
TCP_FLAGS = frozenset(("CWR", "ECE", "URG", "ACK", "PSH", "RST", "SYN", "FIN"))


def _local_to_utc(naive: datetime, tz=None) -> datetime | None:
    if tz is not None:
        return naive.replace(tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)
    try:
        epoch = time.mktime(naive.timetuple()) + naive.microsecond / 1e6
    except (OverflowError, ValueError):
        return None
    return datetime.fromtimestamp(epoch, timezone.utc).replace(tzinfo=None)


def parse_timestamp(line: str, now: datetime | None = None, tz=None) -> datetime | None:
    """줄 앞의 syslog 시각 → naive UTC. 못 읽으면 None.

    RFC3339(2026-09-15T20:28:01.123456+09:00)은 시간대가 들어 있어 그대로 바꾼다.
    전통 형식(Sep 15 20:28:01)에는 연도와 시간대가 없다. 이 컴퓨터의 시간대(tz 를 주면 그것)로 읽고,
    연도는 올해로 두되 그러면 하루 넘게 미래가 되는 경우(12월 기록을 1월에 읽을 때)만 작년으로 본다.
    """
    now = now or utcnow()
    m = _ISO_TS_RE.match(line)
    if m:
        text = m.group("ts")
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        if dt.tzinfo is None:
            return _local_to_utc(dt, tz)
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    m = _TRAD_TS_RE.match(line)
    if not m or m.group("mon") not in _MONTHS:
        return None
    parts = (_MONTHS[m.group("mon")], int(m.group("day")), int(m.group("h")), int(m.group("m")), int(m.group("s")))
    try:
        dt = _local_to_utc(datetime(now.year, *parts), tz)
        if dt is not None and dt - now > timedelta(days=1):
            dt = _local_to_utc(datetime(now.year - 1, *parts), tz)
    except ValueError:      # 2월 29일을 평년으로 읽는 경우 등
        return None
    return dt


def parse_ufw_line(line: str, now: datetime | None = None, tz=None) -> dict | None:
    """[UFW BLOCK] 한 줄 → 구조. BLOCK 이 아니거나 필수 값(SRC·PROTO)이 없으면 None.

    ICMP 오류 패킷은 원래 패킷을 '[SRC=… DST=… DPT=… ]' 로 한 번 더 싣는다. 대괄호로 시작하는 토큰에서
    읽기를 멈추고, 같은 키는 처음 것만 쓴다.
    """
    tag = _UFW_TAG_RE.search(line)
    if not tag or tag.group("action") != "BLOCK":
        return None
    fields: dict[str, str] = {}
    flags: list[str] = []
    for tok in line[tag.end():].split():
        if tok.startswith("["):
            break           # ICMP 오류가 실은 원래 패킷(또는 끝의 [SIMULATION]) — 여기부터는 이 패킷의 값이 아니다
        kv = _KV_RE.match(tok)
        if kv:
            fields.setdefault(kv.group("k"), kv.group("v"))
        elif tok in TCP_FLAGS:
            flags.append(tok)
    src = normalize_ip(fields["SRC"]) if fields.get("SRC") else None
    proto = fields.get("PROTO", "").upper()
    if src is None or not proto:
        return None
    dst = normalize_ip(fields["DST"]) if fields.get("DST") else None

    def _port(key):
        v = fields.get(key, "")
        return int(v) if v.isdigit() and int(v) <= 65535 else None

    return {
        "ts": parse_timestamp(line, now, tz),
        "src": str(src), "dst": str(dst) if dst else "",
        "proto": proto, "spt": _port("SPT"), "dpt": _port("DPT"), "flags": flags,
        "in": fields.get("IN", ""), "out": fields.get("OUT", ""),
        # 들어오는 패킷만 스캔으로 본다 (IN 이 있고 OUT 이 없음). 나가는·전달되는 차단은 세지 않는다.
        "inbound": bool(fields.get("IN")) and not fields.get("OUT"),
        "simulation": "[SIMULATION]" in line,
    }


def scan_port_key(p: dict) -> str | None:
    """스캔 판정에 세는 목적지 포트. TCP 는 SYN 만(ACK 없음), UDP 는 전부. 나머지는 None.

    ACK·FIN·RST 만 달린 TCP 는 끝난 정상 연결의 늦은 패킷이 막힌 경우가 흔해서 세지 않는다
    (그래서 FIN/NULL/Xmas 스캔은 스캔으로 잡지 않는다 — 차단 건수에는 들어간다).
    """
    if p.get("dpt") is None:
        return None
    if p["proto"] == "UDP":
        return f"{p['dpt']}/udp"
    if p["proto"] == "TCP" and "SYN" in p["flags"] and "ACK" not in p["flags"]:
        return f"{p['dpt']}/tcp"
    return None


def target_key(p: dict) -> str:
    """하루 요약에서 '어느 포트를 두드렸나'를 세는 키."""
    if p.get("dpt") is not None:
        return f"{p['dpt']}/{p['proto'].lower()}"
    return p["proto"].lower()


# --- 주소 분류 ----------------------------------------------------------------
_LOOPBACK = [ipaddress.ip_network("127.0.0.0/8"), ipaddress.ip_network("::1/128")]
# '내부망'은 실제로 LAN 에 쓰이는 대역만. ipaddress.is_private 는 문서용 대역(192.0.2.0/24 등)까지 사설로 보므로 쓰지 않는다.
# 100.64.0.0/10 은 통신사 CGNAT 과 Tailscale 이 쓴다 — 이 서버에 닿았다면 같은 망 안쪽이다.
_INTERNAL = [ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "169.254.0.0/16", "fc00::/7", "fe80::/10")]


def is_internal_ip(ip: str) -> bool:
    return find_network(ip, _INTERNAL) is not None


# --- 스캔한 IP 목록 (세 모니터가 함께 본다) ---------------------------------------
class ScanEpisode:
    """한 IP 의 스캔 한 차례. 마지막 기록 뒤 EPISODE_GAP 동안 조용하면 끝난 것으로 본다."""
    PORT_SAMPLE = 30
    PORT_CAP = 4096

    def __init__(self, ip: str, first_seen: datetime, last_seen: datetime, ports=(), packets: int = 0,
                 internal: bool = False, simulation: bool = False, port_count: int | None = None):
        self.ip = ip
        self.first_seen = first_seen
        self.last_seen = last_seen
        self._ports: dict[str, None] = {}
        for k in ports:
            self.add_port(k)
        self._port_floor = port_count or 0     # DB 에서 되찾을 때 표본보다 많았던 개수
        self.packets = packets
        self.internal = internal
        self.simulation = simulation
        self.notified: set[str] = set()         # 이번 차례에 이미 올린 후속 알림 (중복 억제)

    def add_port(self, key: str | None):
        if key and key not in self._ports and len(self._ports) < self.PORT_CAP:
            self._ports[key] = None

    @property
    def port_count(self) -> int:
        return max(len(self._ports), self._port_floor)

    def ports_sample(self) -> list[str]:
        def order(k):
            head = k.split("/", 1)[0]
            return (int(head) if head.isdigit() else 70000, k)
        return sorted(self._ports, key=order)[:self.PORT_SAMPLE]

    def as_dict(self) -> dict:
        return {
            "ip": self.ip, "port_count": self.port_count, "ports": self.ports_sample(), "packets": self.packets,
            "first_seen": self.first_seen.isoformat(), "last_seen": self.last_seen.isoformat(),
            "internal": self.internal, "simulation": self.simulation,
        }


class ScanRegistry:
    """IP → 최근 스캔 차례. 크기 상한을 넘으면 가장 오래 조용한 것부터 버린다."""

    def __init__(self, max_entries: int = 5000):
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self._eps: OrderedDict[str, ScanEpisode] = OrderedDict()

    def get(self, ip: str) -> ScanEpisode | None:
        with self._lock:
            return self._eps.get(ip)

    def put(self, ep: ScanEpisode):
        with self._lock:
            self._eps[ep.ip] = ep
            self._eps.move_to_end(ep.ip)
            while len(self._eps) > self.max_entries:
                self._eps.popitem(last=False)

    def touch(self, ip: str, ts: datetime, key: str | None) -> ScanEpisode | None:
        with self._lock:
            ep = self._eps.get(ip)
            if ep is None:
                return None
            ep.last_seen = max(ep.last_seen, ts)
            ep.packets += 1
            ep.add_port(key)
            self._eps.move_to_end(ip)
            return ep

    def recent(self, ip: str, now: datetime, within: timedelta) -> ScanEpisode | None:
        with self._lock:
            ep = self._eps.get(ip)
            return ep if ep is not None and now - ep.last_seen <= within else None

    def claim(self, ip: str, key: str) -> bool:
        """이번 차례에 key 알림을 처음 올리는 것이면 True (그리고 표시해 둔다)."""
        with self._lock:
            ep = self._eps.get(ip)
            if ep is None or key in ep.notified:
                return False
            ep.notified.add(key)
            return True

    def release(self, ip: str, key: str):
        with self._lock:
            ep = self._eps.get(ip)
            if ep is not None:
                ep.notified.discard(key)

    def expire(self, now: datetime, within: timedelta) -> int:
        with self._lock:
            old = [ip for ip, ep in self._eps.items() if now - ep.last_seen > within]
            for ip in old:
                del self._eps[ip]
            return len(old)

    def episodes(self) -> list[ScanEpisode]:
        with self._lock:
            return list(self._eps.values())

    def clear(self):
        with self._lock:
            self._eps.clear()

    def __len__(self):
        with self._lock:
            return len(self._eps)


REGISTRY = ScanRegistry()


def _followup(hours: int | None = None) -> timedelta:
    return timedelta(hours=config.SCAN_FOLLOWUP_HOURS if hours is None else hours)


def scan_context(ip: str, now: datetime | None = None, registry: ScanRegistry | None = None,
                 followup_hours: int | None = None) -> dict | None:
    """이 IP 가 최근(후속 확인 시간 안)에 스캔했으면 그 요약, 아니면 None. 다른 알림에 정황으로 붙인다."""
    reg = REGISTRY if registry is None else registry
    addr = normalize_ip(ip)
    if addr is None:
        return None
    ep = reg.recent(str(addr), now or utcnow(), _followup(followup_hours))
    return ep.as_dict() if ep else None


def _scan_sentence(ctx: dict) -> str:
    sample = ", ".join(ctx["ports"][:8]) + (" 등" if ctx["port_count"] > 8 else "")
    return (f"{ctx['ip']} 은(는) 앞서 이 서버의 방화벽에 막힌 포트 {ctx['port_count']}개 이상을 두드렸습니다"
            f"(막힌 기록 {ctx['packets']}건 이상, 포트: {sample}).")


def _scan_evidence(ctx: dict, extra: str = "") -> str:
    lines = [f"스캔 첫 기록 {ctx['first_seen']} UTC, 마지막 기록 {ctx['last_seen']} UTC",
             f"두드린 포트(일부): {', '.join(ctx['ports'])}"]
    if extra:
        lines.append(extra)
    return "\n".join(lines)


def _raise(reg: ScanRegistry, ip: str, claim_key: str, **kwargs) -> bool:
    if not reg.claim(ip, claim_key):
        return False
    try:
        raise_alert(**kwargs)
    except Exception as e:
        reg.release(ip, claim_key)
        logger.error(f"scan follow-up alert failed for {ip}: {e}")
        return False
    return True


def note_auth_activity(ip: str, kind: str, *, user: str = "", raw: str = "", is_simulation: bool = False,
                       registry: ScanRegistry | None = None, now: datetime | None = None,
                       followup_hours: int | None = None) -> bool:
    """AuthLogWatcher 가 SSH 인증 시도(auth_failure·invalid_user·auth_success)를 볼 때 부른다.

    스캔한 IP 의 시도면 경고를 올리고 True. 실패는 차례당 한 번(브루트포스 규칙이 횟수를 센다),
    성공은 계정마다 한 번. '실패 후 성공'은 호출하는 쪽이 이미 긴급으로 올리므로 부르지 않는다.
    """
    reg = REGISTRY if registry is None else registry
    addr = normalize_ip(ip)
    if addr is None:
        return False
    ip = str(addr)
    ep = reg.recent(ip, now or utcnow(), _followup(followup_hours))
    if ep is None:
        return False
    ctx = ep.as_dict()
    sim = is_simulation or ep.simulation
    details = {"ip": ip, "user": user, "kind": kind, "scan": ctx, "lower_bound": True}
    if kind == "auth_success":
        return _raise(
            reg, ip, f"auth_success:{user}",
            rule="scan_then_auth", severity="WARNING",
            title=f"SSH login for {user} from {ip} after it port-scanned this host",
            fingerprint=f"scan_then_auth:{ip}:login:{user}",
            title_ko=f"포트 스캔한 IP 에서 SSH 로그인 성공: {ip} ('{user}' 계정)",
            summary_ko=(f"{_scan_sentence(ctx)} 그 뒤 '{user}' 계정 로그인이 성공했습니다. 본인이나 동료가 점검 도구를 "
                        f"돌린 뒤 접속한 것이 아니라면 계정 정보가 새어 나갔을 수 있습니다. {LOWER_BOUND_KO} {NOT_BLOCKED_KO}"),
            action_ko=(f"본인의 접속이면 확인(ack)하세요. 아니라면 `who` 와 `last -a | head` 로 세션을 확인하고, "
                       f"`sudo pkill -KILL -u {user}` 로 끊은 뒤 비밀번호와 authorized_keys 를 점검하세요. "
                       f"이 IP 차단도 검토하세요: `sudo fail2ban-client set {config.FAIL2BAN_JAIL} banip {ip}`"),
            evidence=_scan_evidence(ctx, raw), details=details, is_simulation=sim,
        )
    return _raise(
        reg, ip, "auth_failure",
        rule="scan_then_auth", severity="WARNING",
        title=f"SSH login attempt from {ip} after it port-scanned this host",
        fingerprint=f"scan_then_auth:{ip}:attempt",
        title_ko=f"포트 스캔 뒤 SSH 로그인 시도: {ip}",
        summary_ko=(f"{_scan_sentence(ctx)} 그 뒤 SSH 로그인을 시도했습니다('{user or '?'}' 계정, 실패). "
                    f"열린 문을 찾은 다음 들어오려는 흐름일 수 있습니다. {LOWER_BOUND_KO} {NOT_BLOCKED_KO}"),
        action_ko=(f"IP 차단 패널에서 fail2ban 이 이미 막았는지 보세요. 계속 시도하면 차단을 검토하세요: "
                   f"`sudo fail2ban-client set {config.FAIL2BAN_JAIL} banip {ip}`. 근거의 포트 목록에 실제로 열어 둔 "
                   f"서비스가 있는지 `sudo ss -ltnp` 로 확인하고, SSH 는 비밀번호 로그인을 끄고 키 인증만 허용했는지 점검하세요."),
        evidence=_scan_evidence(ctx, raw), details=details, is_simulation=sim,
    )


def note_connection(ip: str, local_port: int, *, process_info=None, is_simulation: bool = False,
                    registry: ScanRegistry | None = None, now: datetime | None = None,
                    followup_hours: int | None = None) -> bool:
    """NetworkWatcher 가 리스닝 포트로 들어온 ESTABLISHED 연결을 볼 때 부른다. 스캔한 IP 면 경고, 포트마다 한 번."""
    reg = REGISTRY if registry is None else registry
    addr = normalize_ip(ip)
    if addr is None:
        return False
    ip = str(addr)
    ep = reg.recent(ip, now or utcnow(), _followup(followup_hours))
    if ep is None or f"conn:{local_port}" in ep.notified:
        return False
    info = {}
    if callable(process_info):
        try:
            info = process_info() or {}
        except Exception:
            info = {}
    proc = info.get("process") or "알 수 없는 프로세스"
    ctx = ep.as_dict()
    if local_port in config.SSH_PORTS:
        close_hint = "SSH 포트는 닫지 말고(원격 접속이 끊깁니다) 비밀번호 로그인을 끄고 키 인증만 허용했는지 점검하세요."
    else:
        close_hint = (f"그 서비스가 인터넷에 열려 있어야 하는지 따져 보고, 아니라면 127.0.0.1 에만 바인딩하거나 "
                      f"방화벽에서 닫으세요(`sudo ufw delete allow {local_port}` 또는 `sudo ufw deny {local_port}`).")
    return _raise(
        reg, ip, f"conn:{local_port}",
        rule="scan_then_connection", severity="WARNING",
        title=f"{ip} connected to local port {local_port} after port-scanning this host",
        fingerprint=f"scan_then_connection:{ip}:{local_port}",
        title_ko=f"포트 스캔 뒤 실제 연결: {ip} → 이 서버 {local_port}번 포트 ({proc})",
        summary_ko=(f"{_scan_sentence(ctx)} 그 뒤 이 서버의 {local_port}번 포트({proc})에 연결이 맺어졌습니다. "
                    f"스캔으로 찾은 열린 서비스에 접속한 것일 수 있습니다. 연결은 15초마다 확인하므로 짧은 연결은 놓칠 수 있습니다. "
                    f"{LOWER_BOUND_KO} {NOT_BLOCKED_KO}"),
        action_ko=(f"`sudo ss -tnp | grep '{ip}'` 로 연결이 남아 있는지, 어느 프로그램인지 확인하세요. {close_hint} "
                   f"이 IP 차단도 검토하세요: `sudo fail2ban-client set {config.FAIL2BAN_JAIL} banip {ip}`"),
        evidence=_scan_evidence(ctx, f"연결: {ip} → :{local_port} ({proc}, pid {info.get('pid', '?')})"),
        details={"ip": ip, "local_port": local_port, "process": info.get("process"), "scan": ctx, "lower_bound": True},
        is_simulation=is_simulation or ep.simulation,
    )


def _raise_internal_scan(reg: ScanRegistry, ep: ScanEpisode, window_sec: int) -> bool:
    ctx = ep.as_dict()
    return _raise(
        reg, ep.ip, "internal_scan",
        rule="internal_scan", severity="WARNING",
        title=f"Port scan from internal address {ep.ip}",
        fingerprint=f"internal_scan:{ep.ip}",
        title_ko=f"내부망 주소의 포트 스캔: {ep.ip} (감염된 기기일 수 있음)",
        summary_ko=(f"같은 네트워크 안쪽 주소 {ep.ip} 이(가) {window_sec}초 안에 이 서버의 방화벽에 막힌 포트 "
                    f"{ctx['port_count']}개 이상을 두드렸습니다. 그 기기가 악성코드에 감염돼 주변을 훑고 있을 수 있습니다. "
                    f"네트워크 점검 도구, NAS·프린터의 기기 찾기일 수도 있습니다. {LOWER_BOUND_KO} {NOT_BLOCKED_KO}"),
        action_ko=(f"`ip neigh | grep '{ep.ip}'` 로 그 주소의 MAC 주소를 보고, 공유기 관리 화면의 기기 목록에서 어떤 기기인지 "
                   f"찾으세요. 모르는 기기이거나 스캔할 이유가 없는 기기면 네트워크에서 분리하고 점검하세요. "
                   f"일부러 돌린 점검이면 확인(ack)하세요."),
        evidence=_scan_evidence(ctx),
        details={"ip": ep.ip, "window_sec": window_sec, "scan": ctx, "lower_bound": True},
        is_simulation=ep.simulation,
    )


# --- 하루 집계 ----------------------------------------------------------------
class DailyTally:
    """하루치 차단 집계. 키 수에 상한을 두고, 넘으면 적게 나온 것부터 버린다(truncated 로 알린다)."""
    MAX_KEYS = 20000

    def __init__(self, day: date, since: datetime, partial: bool):
        self.day = day
        self.since = since
        self.partial = partial
        self.total = 0
        self.by_src: Counter = Counter()
        self.by_port: Counter = Counter()
        self.by_pair: Counter = Counter()
        self.scanners: set[str] = set()
        self.truncated = False
        self.log_unavailable = False

    def _bump(self, counter: Counter, key):
        counter[key] += 1
        if len(counter) > self.MAX_KEYS:
            keep = counter.most_common(self.MAX_KEYS // 2)
            counter.clear()
            counter.update(dict(keep))
            self.truncated = True

    def add(self, ip: str, target: str):
        self.total += 1
        self._bump(self.by_src, ip)
        self._bump(self.by_port, target)
        self._bump(self.by_pair, (ip, target))

    def add_scanner(self, ip: str):
        if len(self.scanners) < self.MAX_KEYS:
            self.scanners.add(ip)
        else:
            self.truncated = True

    def summary(self, top_n: int = 10) -> dict:
        top_sources = []
        for ip, n in self.by_src.most_common(top_n):
            pairs = [(t, c) for (i, t), c in self.by_pair.items() if i == ip]
            top_port = max(pairs, key=lambda x: x[1])[0] if pairs else ""
            top_sources.append({"ip": ip, "packets": n, "top_port": top_port, "scanned": ip in self.scanners})
        return {
            "date": self.day.isoformat(), "since": self.since.isoformat(), "partial": self.partial,
            "total_blocked": self.total, "scanning_ips": len(self.scanners),
            "top_sources": top_sources,
            "top_ports": [{"port": p, "packets": n} for p, n in self.by_port.most_common(top_n)],
            "truncated": self.truncated, "log_unavailable": self.log_unavailable, "lower_bound": True,
        }


class _Tracker:
    """한 IP 의 최근 window 초 동안 스캔 판정용 기록."""
    __slots__ = ("hits", "ports", "latest")

    def __init__(self):
        self.hits: deque = deque()     # (ts, port_key)
        self.ports: Counter = Counter()
        self.latest: datetime | None = None

    def add(self, ts: datetime, key: str, window: timedelta, max_hits: int):
        self.hits.append((ts, key))
        self.ports[key] += 1
        self.latest = ts if self.latest is None else max(self.latest, ts)
        cutoff = self.latest - window
        while self.hits and (self.hits[0][0] < cutoff or len(self.hits) > max_hits):
            _, old = self.hits.popleft()
            self.ports[old] -= 1
            if self.ports[old] <= 0:
                del self.ports[old]


# --- 모니터 -------------------------------------------------------------------
class FirewallLogWatcher(BaseMonitor):
    name = "FirewallLogWatcher"
    label = "방화벽 로그 감시 (포트 스캔)"
    interval = 2
    MAX_LINES_PER_TICK = 5000
    MAX_TRACKED_IPS = 4096
    MAX_HITS_PER_IP = 512
    EPISODE_GAP = timedelta(hours=1)
    TOP_N = 10
    UFW_CONF = "/etc/ufw/ufw.conf"
    CONF_CHECK_SEC = 300
    HOUSEKEEPING_SEC = 60
    QUIET_HOURS = 24
    AUTH_EVENT_TYPES = ("AUTH_FAILURE", "INVALID_USER", "AUTH_SUCCESS")

    def __init__(self, log_path: str | None = None, *, window_sec: int | None = None, port_threshold: int | None = None,
                 followup_hours: int | None = None, admin_ips: str | None = None, registry: ScanRegistry | None = None,
                 ufw_conf: str | None = None, max_tracked: int | None = None, interval: int | None = None):
        super().__init__(interval)
        self.log_path = log_path or config.UFW_LOG_PATH
        self.source = self.log_path
        self.window_sec = max(1, window_sec if window_sec is not None else config.SCAN_WINDOW_SEC)
        self.window = timedelta(seconds=self.window_sec)
        self.threshold = max(2, port_threshold if port_threshold is not None else config.SCAN_PORTS)
        self.followup_hours = config.SCAN_FOLLOWUP_HOURS if followup_hours is None else followup_hours
        self.registry = REGISTRY if registry is None else registry
        self.ufw_conf = ufw_conf or self.UFW_CONF
        self.max_tracked = max_tracked or self.MAX_TRACKED_IPS
        self._admin_nets, _invalid = parse_ip_list(config.F2B_IGNOREIP if admin_ips is None else admin_ips)
        self._reader: TailReader | None = None
        self._trackers: OrderedDict[str, _Tracker] = OrderedDict()
        self._lock = threading.Lock()
        self._log_problem: tuple[str, str] | None = None
        self._conf_problem: tuple[str, str] | None = None
        self.ufw_conf_state = "unknown"
        self._last_conf_check = 0.0
        self._last_housekeeping = time.monotonic()
        self._created = utcnow()
        self.last_block_at: datetime | None = None
        self.stats = Counter()
        self.daily = DailyTally(self._local_date(), utcnow(), partial=True)

    # --- 수명 주기 ---
    def setup(self):
        self._seed_registry()
        self._check_ufw_conf()
        self._try_open()

    def _local_date(self) -> date:
        return datetime.now().date()

    def _try_open(self) -> bool:
        try:
            reader = TailReader(self.log_path)
            reader.open(seek_end=True)
            self._reader = reader
            self._log_problem = None
        except FileNotFoundError:
            self._reader = None
            self._log_problem = (
                f"ufw 로그 파일 없음: {self.log_path} — 방화벽이 막은 포트 스캔을 볼 수 없음",
                "ufw 로그를 켜세요: sudo ufw logging low (파일은 rsyslog 가 /etc/rsyslog.d/20-ufw.conf 로 만듭니다). "
                "경로가 다르면 SECDASH_UFW_LOG 로 지정하세요.")
        except PermissionError:
            self._reader = None
            self._log_problem = (
                f"ufw 로그 파일 읽기 권한 없음: {self.log_path}",
                "서비스 계정을 adm 그룹에 넣으세요: sudo usermod -aG adm secdash && sudo systemctl restart secdash "
                "(로그가 syslog:adm 0640 인지도 확인: ls -l /var/log/ufw.log)")
        except Exception as e:
            self._reader = None
            self._log_problem = (f"ufw 로그 파일 열기 실패: {e}", "")
        self._refresh_health()
        return self._reader is not None

    def _check_ufw_conf(self):
        """ufw 가 켜져 있는지 sudo 없이 싸게 본다: /etc/ufw/ufw.conf 는 누구나 읽을 수 있다.

        설정 파일 기준이다(부팅 시 켤지). 지금 이 순간 규칙이 올라가 있는지는 `ufw status` 가 필요하고
        그건 root 권한이라 여기서 보지 않는다. 파일을 못 읽으면 판단하지 않는다(unknown).
        """
        self._last_conf_check = time.monotonic()
        try:
            with open(self.ufw_conf, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            self.ufw_conf_state, self._conf_problem = "unknown", None
            self._refresh_health()
            return
        vals = {k: v.strip().strip('"').lower() for k, v in re.findall(r"^\s*([A-Z_]+)\s*=\s*(.*)$", text, re.M)}
        if vals.get("ENABLED") == "no":
            self.ufw_conf_state = "disabled"
            self._conf_problem = (
                f"ufw 가 꺼져 있음 ({self.ufw_conf} ENABLED=no) — 막힌 기록이 생기지 않음",
                "SSH 허용 규칙을 먼저 넣고 켜세요: sudo ufw allow OpenSSH && sudo ufw enable "
                "(순서를 바꾸면 원격 접속이 끊길 수 있습니다)")
        elif vals.get("LOGLEVEL") == "off":
            self.ufw_conf_state = "logging_off"
            self._conf_problem = ("ufw 로그가 꺼져 있음 (LOGLEVEL=off) — 막힌 기록이 남지 않음", "sudo ufw logging low")
        else:
            self.ufw_conf_state = "enabled" if vals.get("ENABLED") == "yes" else "unknown"
            self._conf_problem = None
        self._refresh_health()

    def _refresh_health(self):
        if self._log_problem:
            self.set_health("degraded", *self._log_problem)
            self.daily.log_unavailable = True
        elif self._conf_problem:
            self.set_health("degraded", *self._conf_problem)
            self.daily.log_unavailable = True
        else:
            self.set_health("ok")

    def tick(self):
        self._maybe_roll_day()
        if time.monotonic() - self._last_conf_check >= self.CONF_CHECK_SEC:
            self._check_ufw_conf()
        if self._reader is None and not self._try_open():
            return
        try:
            for _ in range(self.MAX_LINES_PER_TICK):
                line = self._reader.readline()
                if not line:
                    break
                self.process_line(line)
        except PermissionError:
            # 로테이션 뒤 새 파일의 권한이 바뀐 경우
            self._reader = None
            self._try_open()
        if time.monotonic() - self._last_housekeeping >= self.HOUSEKEEPING_SEC:
            self._housekeeping()

    def _housekeeping(self):
        self._last_housekeeping = time.monotonic()
        now = utcnow()
        for ip in [ip for ip, tr in self._trackers.items() if tr.latest is None or now - tr.latest > self.window]:
            self._trackers.pop(ip, None)
        self.registry.expire(now, max(self.EPISODE_GAP, _followup(self.followup_hours)))
        # 열어 둔 파일이 지워지고 다시 생기지 않으면 readline 은 조용히 빈 줄만 준다 → 직접 확인
        if self._reader is not None:
            try:
                os.stat(self.log_path)
                if self._log_problem and "없음" in self._log_problem[0]:
                    self._log_problem = None
                    self._refresh_health()
            except FileNotFoundError:
                self._log_problem = (f"ufw 로그 파일 없음: {self.log_path} (지워졌거나 로테이션 뒤 다시 생기지 않음)",
                                     "sudo ufw logging low 로 로그를 다시 켜고 rsyslog 를 확인하세요: sudo systemctl status rsyslog")
                self._refresh_health()
            except OSError:
                pass

    # --- 처리 ---
    def process_line(self, line: str):
        self.stats["lines"] += 1
        parsed = parse_ufw_line(line)
        if parsed is None:
            if "[UFW BLOCK]" in line:
                self.stats["malformed"] += 1
                n = self.stats["malformed"]
                if n in (1, 10, 100) or n % 1000 == 0:
                    self.log.debug(f"malformed UFW BLOCK line #{n}: {line.strip()[:200]}")
            return
        self.handle(parsed)

    def _is_excluded(self, ip: str) -> bool:
        return find_network(ip, _LOOPBACK) is not None or find_network(ip, self._admin_nets) is not None

    def handle(self, p: dict):
        now = utcnow()
        ts = p["ts"] or now
        if ts - now > timedelta(minutes=5):       # 시계가 어긋난 기록이 창을 망치지 않게
            ts = now
        self.stats["blocked"] += 1
        if not p["inbound"]:
            self.stats["not_inbound"] += 1
            return
        ip = p["src"]
        if self._is_excluded(ip):
            self.stats["excluded"] += 1
            return
        sim = p["simulation"]
        key = scan_port_key(p)
        if not sim:
            with self._lock:
                self.daily.add(ip, target_key(p))
            self.last_block_at = ts if self.last_block_at is None else max(self.last_block_at, ts)

        ep = self.registry.get(ip)
        if ep is not None and ts - ep.last_seen <= self.EPISODE_GAP:
            self.registry.touch(ip, ts, key)
            return
        if key is None:
            return
        tr = self._track(ip)
        tr.add(ts, key, self.window, self.MAX_HITS_PER_IP)
        if len(tr.ports) >= self.threshold:
            self._start_episode(ip, tr, sim)

    def _track(self, ip: str) -> _Tracker:
        tr = self._trackers.get(ip)
        if tr is not None:
            self._trackers.move_to_end(ip)
            return tr
        tr = self._trackers[ip] = _Tracker()
        while len(self._trackers) > self.max_tracked:
            self._trackers.popitem(last=False)
            self.stats["evicted"] += 1
        return tr

    def _start_episode(self, ip: str, tr: _Tracker, sim: bool):
        ep = ScanEpisode(ip, first_seen=tr.hits[0][0], last_seen=tr.latest, ports=list(tr.ports),
                         packets=len(tr.hits), internal=is_internal_ip(ip), simulation=sim)
        self.registry.put(ep)
        self._trackers.pop(ip, None)
        self.stats["episodes"] += 1
        if not sim:
            with self._lock:
                self.daily.add_scanner(ip)
        d = ep.as_dict() | {"window_sec": self.window_sec, "threshold": self.threshold, "lower_bound": True}
        self.log_event("FIREWALL_SCAN", "INFO",
                       f"ufw blocked a port scan from {ip}: {ep.port_count} ports within {self.window_sec}s", d,
                       is_simulation=sim)
        if ep.internal:
            _raise_internal_scan(self.registry, ep, self.window_sec)
        self._backcheck_auth(ep)

    def _backcheck_auth(self, ep: ScanEpisode):
        """스캔이 임계치를 넘기 전(첫 기록 이후)에 이미 처리된 SSH 시도를 되짚는다.

        두 로그는 다른 스레드가 1~2초 간격으로 읽는다. 스캔 도중에 들어온 로그인 시도가 스캔 판정보다
        먼저 처리되면 훅 호출 시점엔 아직 '스캔한 IP' 가 아니다. 그 순서 차이로 알림을 놓치지 않게 한다.
        """
        db = SessionLocal()
        try:
            rows = (db.query(Event)
                    .filter(Event.timestamp >= ep.first_seen, Event.event_type.in_(self.AUTH_EVENT_TYPES),
                            Event.details.like(f'%"ip": "{ep.ip}"%'))
                    .order_by(Event.id).limit(200).all())
            items = [(e.event_type, e.details_dict(), bool(e.is_simulation)) for e in rows]
            login_alerts = (db.query(Alert)
                            .filter(Alert.rule == "login_after_failures", Alert.status.in_(["OPEN", "ACKED"]),
                                    Alert.fingerprint.like(f"login_after_failures:{ep.ip}:%"))
                            .all())
            if login_alerts:
                for a in login_alerts:
                    a.details = json.dumps(a.details_dict() | {"prior_scan": ep.as_dict()}, ensure_ascii=False)
                db.commit()
            login_users = {a.fingerprint.rsplit(":", 1)[-1] for a in login_alerts}
        except Exception as e:
            db.rollback()
            self.log.error(f"auth back-check failed for {ep.ip}: {e}")
            return
        finally:
            db.close()
        for event_type, d, sim in items:
            if str(normalize_ip(d.get("ip", "")) or "") != ep.ip:
                continue
            if event_type == "AUTH_SUCCESS":
                if d.get("user") in login_users:
                    continue       # 이미 '실패 후 성공' 긴급 알림이 있다 — 정황만 붙였다
                note_auth_activity(ep.ip, "auth_success", user=d.get("user", ""), is_simulation=sim,
                                   registry=self.registry, followup_hours=self.followup_hours)
            else:
                note_auth_activity(ep.ip, "auth_failure", user=d.get("user", ""), is_simulation=sim,
                                   registry=self.registry, followup_hours=self.followup_hours)

    def _seed_registry(self):
        """재시작해도 '최근에 스캔한 IP' 를 잊지 않게 DB 의 FIREWALL_SCAN 이벤트로 되찾는다."""
        db = SessionLocal()
        try:
            since = utcnow() - _followup(self.followup_hours)
            rows = (db.query(Event)
                    .filter(Event.event_type == "FIREWALL_SCAN", Event.timestamp >= since,
                            Event.is_simulation == False)  # noqa: E712
                    .order_by(Event.id).all())
            for e in rows:
                d = e.details_dict()
                ip = str(normalize_ip(d.get("ip", "")) or "")
                if not ip:
                    continue
                try:
                    first = datetime.fromisoformat(d["first_seen"])
                    last = datetime.fromisoformat(d["last_seen"])
                except (KeyError, TypeError, ValueError):
                    first = last = e.timestamp
                old = self.registry.get(ip)
                if old is not None and old.last_seen >= last:
                    continue
                self.registry.put(ScanEpisode(ip, first, last, ports=d.get("ports") or [], packets=int(d.get("packets") or 0),
                                              internal=bool(d.get("internal")), port_count=int(d.get("port_count") or 0)))
        except Exception as ex:
            self.log.error(f"seed scan registry failed: {ex}")
        finally:
            db.close()

    # --- 하루 요약 ---
    def _maybe_roll_day(self):
        today = self._local_date()
        if today == self.daily.day:
            return
        with self._lock:
            summary = self.daily.summary(self.TOP_N)
            self.daily = DailyTally(today, utcnow(), partial=False)
            if self._log_problem or self._conf_problem:
                self.daily.log_unavailable = True
        self.log_event("FIREWALL_DAILY", "INFO",
                       f"ufw daily summary {summary['date']}: {summary['total_blocked']} blocked, "
                       f"{summary['scanning_ips']} scanning IPs", summary)

    def quiet_note(self) -> str:
        now = utcnow()
        ref = self.last_block_at or self._created
        if now - ref < timedelta(hours=self.QUIET_HOURS):
            return ""
        return (f"{self.QUIET_HOURS}시간 넘게 막힌 기록이 없습니다. 막을 일이 없었을 수도 있고, ufw 로그 설정이 바뀌었을 수도 "
                f"있습니다(정보일 뿐 문제로 보지는 않습니다). 확인: sudo ufw status verbose")

    def status_payload(self) -> dict:
        now = utcnow()
        with self._lock:
            today = self.daily.summary(self.TOP_N)
        eps = sorted(self.registry.episodes(), key=lambda e: e.last_seen, reverse=True)[:50]
        return {
            "available": True,
            "health": self.health, "health_reason": self.health_reason, "fix_hint": self.fix_hint,
            "log_path": self.log_path, "ufw_conf": self.ufw_conf_state,
            "settings": {"window_sec": self.window_sec, "port_threshold": self.threshold,
                         "followup_hours": self.followup_hours, "episode_gap_min": int(self.EPISODE_GAP.total_seconds() // 60)},
            "today": today,
            "episodes": [ep.as_dict() | {"active": now - ep.last_seen <= self.EPISODE_GAP} for ep in eps],
            "tracked_ips": len(self._trackers),
            "stats": dict(self.stats),
            "last_block_at": self.last_block_at.isoformat() if self.last_block_at else None,
            "note_ko": self.quiet_note(),
            "lower_bound_note_ko": LOWER_BOUND_KO,
        }
