"""
관리자 자신을 차단하지 않게 하는 보호 목록.

원격 서버에서 대시보드가 관리자 IP 를 차단하면 SSH 로 다시 들어올 수 없다. fail2ban 의 ignoreip 는
로그 분석으로 생긴 차단만 막고, `fail2ban-client set <jail> banip` 으로 직접 넣는 차단은 막지 않는다
(fail2ban 1.0 의 Actions.__checkBan 은 ignoreip 를 보지 않는다). 대시보드의 자동·수동 차단은 모두
그 명령을 쓰므로, 차단하기 전에 여기서 한 번 더 거른다.

보호하는 주소:
  1. 루프백
  2. SECDASH_F2B_IGNOREIP — 운영자가 적은 관리자 대역 (apply-host-config.sh 가 fail2ban 에도 넣는다)
  3. fail2ban 이 지금 쓰고 있는 ignoreip
  4. 로그인을 마치고 열려 있는 SSH 세션의 상대 주소

4번에서 "22번 포트에 연결돼 있는 주소"를 보호하지 않는 이유: 비밀번호를 찍어보는 공격자도 시도하는
순간에는 연결돼 있다. 그래서 인증을 마친 세션만 본다. OpenSSH 는 인증을 마친 세션의 프로세스 이름을
'sshd: 사용자@pts/0'(9.8 이후 'sshd-session: 사용자@pts/0')로 바꾸고, 인증 전 프로세스는
'sshd: 사용자 [priv]' · '[net]' · '[preauth]' 로 둔다.
"""
import ipaddress
import logging
import re

import config
from iplist import find_network, format_network, normalize_ip, parse_ip_list

logger = logging.getLogger("admin_guard")

_LOOPBACK = [ipaddress.ip_network("127.0.0.0/8"), ipaddress.ip_network("::1/128")]
_AUTHED_SSHD_RE = re.compile(r"^sshd(?:-session)?: (?P<user>[^\s@\[\]]+)@\S+")


def authenticated_ssh_peers(net_connections=None, cmdline_of=None) -> dict[str, str]:
    """{상대 주소: 사용자} — 인증을 마친 SSH 세션만. 볼 권한이 없으면 빈 dict."""
    import psutil

    if net_connections is None:
        def net_connections():
            return psutil.net_connections(kind="tcp")
    if cmdline_of is None:
        def cmdline_of(pid):
            return " ".join(psutil.Process(pid).cmdline())

    peers: dict[str, str] = {}
    try:
        conns = net_connections()
    except (psutil.Error, OSError) as e:
        logger.debug(f"SSH 세션 목록을 읽지 못함: {e}")
        return peers
    for c in conns:
        if c.status != "ESTABLISHED" or not c.raddr or not c.pid:
            continue
        if c.laddr.port not in config.SSH_PORTS:
            continue
        try:
            m = _AUTHED_SSHD_RE.match(cmdline_of(c.pid))
        except (psutil.Error, OSError):
            continue
        if m:
            addr = normalize_ip(c.raddr.ip)
            if addr is not None:
                peers[str(addr)] = m.group("user")
    return peers


def protection_reason(ip: str, client=None, peers_provider=authenticated_ssh_peers) -> dict | None:
    """차단하면 안 되는 주소면 {"kind", "text"}, 아니면 None."""
    addr = normalize_ip(ip)
    if addr is None:
        return None

    if find_network(ip, _LOOPBACK):
        return {"kind": "loopback", "text": "이 컴퓨터 자신(루프백) 주소"}

    admin_nets, _invalid = parse_ip_list(config.F2B_IGNOREIP)
    net = find_network(ip, admin_nets)
    if net:
        return {"kind": "admin_list",
                "text": f"관리자 주소로 지정됨 (SECDASH_F2B_IGNOREIP 의 {format_network(net)})"}

    live = client.ignore_list() if client is not None and hasattr(client, "ignore_list") else None
    if live:
        net = find_network(ip, parse_ip_list(" ".join(live))[0])
        if net:
            return {"kind": "fail2ban_ignoreip",
                    "text": f"fail2ban 차단 예외(ignoreip {format_network(net)})에 들어 있음"}

    peers = peers_provider()
    if str(addr) in peers:
        return {"kind": "ssh_session",
                "text": f"지금 이 주소에서 '{peers[str(addr)]}' 계정으로 로그인한 SSH 세션이 열려 있음"}
    return None
