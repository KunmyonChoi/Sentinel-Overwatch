"""
노출 면 감시 (ExposureMonitor).

NetworkWatcher 는 '새로 열린 포트'(변화)를 본다. 이 모니터는 '지금 외부에서 도달 가능한 포트'(상태)를 본다.
기동 시점에 이미 열려 있던 리스너는 NetworkWatcher 가 기준선으로 삼아 조용히 넘어가므로,
잘못된 바인딩이 계속 방치돼도 아무도 알리지 않는다. 그 빈틈을 메우는 것이 이 모니터의 존재 이유다.

판정은 바인딩 주소만으로 하지 않는다. 방화벽 규칙과 대조해야 실제 도달성이 나온다.
  loopback              → 외부 도달 불가 (정상)
  외부 바인딩 + 방화벽 허용 → 도달 가능. 의도한 포트가 아니면 알림
  외부 바인딩 + 방화벽 차단 → 지금은 못 오지만 방화벽 규칙 하나에만 의존하는 상태. 정보로만 남긴다
  방화벽을 못 읽음        → '판단 불가'. 안전하다고도, 뚫렸다고도 단정하지 않는다

컨테이너가 게시한 포트는 호스트 방화벽으로 막히지 않는다(Docker 가 iptables 에 직접 규칙을 넣는다).
그쪽은 ContainerAudit 이 따로 본다.
"""
import psutil

import config
from alerts import auto_resolve, raise_alert
from integrations.firewall import FirewallClient, port_reachable
from monitor.base import BaseMonitor
from monitor.intrusion import _proc_info


def is_loopback(addr: str) -> bool:
    a = (addr or "").strip()
    if a.startswith("127.") or a in ("::1", "localhost"):
        return True
    return False


def parse_expected(spec: str) -> set[tuple[int, str]]:
    """'22/tcp,443/tcp' → {(22,'tcp'), (443,'tcp')}. 프로토콜을 안 적으면 tcp 로 본다."""
    out: set[tuple[int, str]] = set()
    for token in (spec or "").split(","):
        token = token.strip().lower()
        if not token:
            continue
        port, _, proto = token.partition("/")
        try:
            out.add((int(port), proto or "tcp"))
        except ValueError:
            continue
    return out


def classify(addr: str, port: int, proto: str, fw: dict, expected: set[tuple[int, str]]) -> dict:
    """리스너 하나의 노출 상태를 판정한다."""
    if is_loopback(addr):
        return {"state": "loopback", "state_ko": "루프백 전용", "reachable": False, "severity": "INFO"}
    reachable = port_reachable(fw, port, proto)
    if (port, proto) in expected:
        return {"state": "expected", "state_ko": "의도된 공개", "reachable": reachable, "severity": "INFO"}
    if reachable is None:
        return {"state": "unknown", "state_ko": "판단 불가 (방화벽 상태 못 읽음)", "reachable": None, "severity": "WARNING"}
    if reachable:
        return {"state": "exposed", "state_ko": "외부 도달 가능", "reachable": True, "severity": "WARNING"}
    return {"state": "firewalled", "state_ko": "방화벽이 막는 중 (바인딩은 전체)", "reachable": False, "severity": "INFO"}


def collect_listeners() -> tuple[list[dict], bool]:
    """(리스너 목록, 프로세스 귀속 누락 여부). 권한이 없으면 다른 계정의 프로세스는 알 수 없다."""
    rows: list[dict] = []
    missing_pid = False
    for c in psutil.net_connections(kind="inet"):
        if c.status != psutil.CONN_LISTEN or not c.laddr:
            continue
        if c.pid is None:
            missing_pid = True
        proto = "udp" if c.type == 2 else "tcp"  # SOCK_DGRAM == 2
        info = _proc_info(c.pid)
        rows.append({
            "address": c.laddr.ip, "port": c.laddr.port, "proto": proto,
            "process": info.get("process"), "user": info.get("user"), "exe": info.get("exe"), "pid": c.pid,
        })
    # UDP 는 psutil 이 LISTEN 상태를 주지 않으므로 따로 모은다 (bound = 수신 대기)
    for c in psutil.net_connections(kind="udp"):
        if not c.laddr or c.raddr:
            continue
        if c.pid is None:
            missing_pid = True
        info = _proc_info(c.pid)
        row = {
            "address": c.laddr.ip, "port": c.laddr.port, "proto": "udp",
            "process": info.get("process"), "user": info.get("user"), "exe": info.get("exe"), "pid": c.pid,
        }
        if row not in rows:
            rows.append(row)
    rows.sort(key=lambda r: (r["proto"], r["port"], r["address"]))
    return rows, missing_pid


class ExposureMonitor(BaseMonitor):
    name = "ExposureMonitor"
    label = "노출 면 감시 (리스닝 포트 × 방화벽)"
    interval = 300  # 5분

    def __init__(self, interval: int | None = None, firewall: FirewallClient | None = None, expected: str | None = None):
        super().__init__(interval)
        self.firewall = firewall or FirewallClient()
        self.expected = parse_expected(config.EXPECTED_EXPOSED_PORTS if expected is None else expected)
        self.source = "psutil 소켓 목록 + 방화벽 규칙"
        self.listeners: list[dict] = []
        self.fw: dict = {"available": False}
        self._open: set[str] = set()
        self._prev_keys: set[str] = set()

    # --- 수집 ---
    def snapshot(self) -> dict:
        rows, missing_pid = collect_listeners()
        self.fw = self.firewall.snapshot()
        for r in rows:
            r.update(classify(r["address"], r["port"], r["proto"], self.fw, self.expected))
        self.listeners = rows
        exposed = [r for r in rows if r["state"] == "exposed"]
        unknown = [r for r in rows if r["state"] == "unknown"]
        return {
            "listeners": rows,
            "firewall": {k: self.fw.get(k) for k in ("available", "backend", "active", "default_incoming", "allowed", "reason", "fix_hint")},
            "missing_process_info": missing_pid,
            "counts": {
                "total": len(rows),
                "loopback": sum(1 for r in rows if r["state"] == "loopback"),
                "external_bind": sum(1 for r in rows if r["state"] != "loopback"),
                "exposed": len(exposed),
                "unknown": len(unknown),
                "expected": sum(1 for r in rows if r["state"] == "expected"),
            },
        }

    # --- 수명 주기 ---
    def setup(self):
        self.tick()

    def tick(self):
        snap = self.snapshot()
        if snap["missing_process_info"]:
            self.set_health("degraded", "다른 계정 프로세스의 소켓은 프로세스를 알 수 없음",
                            "정확한 귀속을 위해 deploy/secdash.service 처럼 CAP_NET_ADMIN 을 부여하세요.")
        elif not self.fw.get("available"):
            self.set_health("degraded", f"방화벽 상태를 읽지 못해 도달성을 판단할 수 없음: {self.fw.get('reason', '')}",
                            self.fw.get("fix_hint", ""))
        else:
            self.set_health("ok")

        current: set[str] = set()
        keys: set[str] = set()
        for r in self.listeners:
            key = f"{r['proto']}/{r['address']}:{r['port']}"
            keys.add(key)
            if r["state"] not in ("exposed", "unknown"):
                continue
            fp = f"exposure:{r['proto']}:{r['port']}"
            current.add(fp)
            if fp in self._open:
                continue
            self._open.add(fp)
            proc = r.get("process") or "알 수 없는 프로세스"
            d = {**r, "message_ko": f"{r['proto'].upper()} {r['port']} ({proc}) — {r['state_ko']}"}
            self.log_event("PORT_EXPOSURE", r["severity"], f"{r['state']}: {r['proto']}/{r['port']} on {r['address']} ({proc})", d)
            if r["state"] == "exposed":
                summary_ko = (f"{r['address']} 에 바인딩되어 있고 방화벽도 이 포트를 허용합니다. "
                              f"실행 파일 {r.get('exe') or '?'}, 사용자 {r.get('user') or '?'}.")
                action_ko = (f"의도한 공개면 SECDASH_EXPECTED_EXPOSED 에 `{r['port']}/{r['proto']}` 를 추가하세요. "
                             f"아니라면 서비스를 127.0.0.1 에 바인딩하도록 고치거나 "
                             f"`sudo ufw delete allow {r['port']}/{r['proto']}` 로 방화벽을 닫으세요.")
            else:
                summary_ko = (f"{r['address']} 에 바인딩되어 있으나 방화벽 규칙을 읽을 수 없어 실제 도달 여부를 확정하지 못했습니다. "
                              f"실행 파일 {r.get('exe') or '?'}.")
                action_ko = (f"`sudo ufw status verbose` 로 {r['port']}/{r['proto']} 허용 여부를 직접 확인하세요. "
                             f"대시보드가 자동 판단하게 하려면 {self.fw.get('fix_hint') or 'sudo 권한을 부여하세요.'}")
            raise_alert(
                "exposed_port", r["severity"], f"{r['state']}: {r['proto']}/{r['port']} ({proc})",
                fingerprint=fp,
                title_ko=f"{r['proto'].upper()} {r['port']} 포트가 {r['state_ko']} — {proc}",
                summary_ko=summary_ko,
                action_ko=action_ko,
                evidence=f"{r['address']}:{r['port']}/{r['proto']} pid={r.get('pid')} exe={r.get('exe')}",
                details=d,
            )

        for fp in sorted(self._open - current):
            auto_resolve(fp, "포트가 닫혔거나 루프백으로 축소됨")
            self._open.discard(fp)

        # 닫힌 포트는 알림이 아니라 사실 기록으로 남긴다 (조치의 결과를 확인할 수 있게)
        for key in sorted(self._prev_keys - keys):
            self.log_event("PORT_CLOSED", "INFO", f"listener closed: {key}", {"key": key, "message_ko": f"리스닝 포트 닫힘: {key}"})
        self._prev_keys = keys

    def status_payload(self) -> dict:
        return {
            "health": self.health, "health_reason": self.health_reason, "fix_hint": self.fix_hint,
            "expected": sorted(f"{p}/{pr}" for p, pr in self.expected),
            **self.snapshot(),
        }
