"""
IP·네트워크 목록 해석.

표준 라이브러리만 쓴다 — deploy/fail2ban_ignoreip.py 가 설치 스크립트(시스템 python3)에서
이 모듈을 그대로 가져다 쓰기 때문이다. 백엔드와 설치 스크립트가 같은 규칙으로 목록을 읽어야
"대시보드는 보호하는데 fail2ban 에는 안 들어간" 주소가 생기지 않는다.
"""
import ipaddress
import re


def normalize_ip(ip: str):
    """문자열 → ip_address. IPv4-mapped IPv6(::ffff:1.2.3.4)는 IPv4 로 바꾼다. 해석 못 하면 None."""
    try:
        addr = ipaddress.ip_address(str(ip).strip().split("%", 1)[0])
    except ValueError:
        return None
    if addr.version == 6 and addr.ipv4_mapped:
        return addr.ipv4_mapped
    return addr


def parse_ip_list(text: str):
    """공백·쉼표로 구분한 IP/CIDR 목록 → (networks, invalid).

    호스트 비트가 선 CIDR(10.0.0.5/24)도 받아 네트워크로 바꾼다. 해석할 수 없는 항목
    (호스트 이름, 오타)은 버리지 않고 invalid 로 돌려준다 — 조용히 무시하면 운영자는
    보호된 줄 알고 있게 된다.
    """
    networks, invalid = [], []
    for token in re.split(r"[\s,]+", (text or "").strip()):
        if not token:
            continue
        try:
            networks.append(ipaddress.ip_network(token, strict=False))
        except ValueError:
            invalid.append(token)
    return networks, invalid


def find_network(ip: str, networks):
    """ip 가 속한 첫 네트워크. 없거나 ip 를 해석할 수 없으면 None."""
    addr = normalize_ip(ip)
    if addr is None:
        return None
    for net in networks:
        if addr.version == net.version and addr in net:
            return net
    return None


def format_network(net) -> str:
    """단일 주소(/32, /128)는 주소만, 대역은 CIDR 로."""
    if net.prefixlen == net.max_prefixlen:
        return str(net.network_address)
    return str(net)
