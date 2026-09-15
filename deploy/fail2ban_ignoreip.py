#!/usr/bin/env python3
"""fail2ban-secdash.conf 의 ignoreip 줄을 secdash.env 의 SECDASH_F2B_IGNOREIP 로 채워 출력한다.

    python3 deploy/fail2ban_ignoreip.py <template> [env_file] [--client <지금 접속한 주소>]

apply-host-config.sh 가 부른다. 관리자 대역을 /etc/fail2ban/jail.d/secdash.conf 에 직접 적으면
update.sh 가 저장소 파일로 덮어써 지워진다 — 그래서 대역은 업데이트가 건드리지 않는 secdash.env 에 두고
설정을 만들 때마다 여기서 합친다.

해석할 수 없는 항목이 있으면 아무것도 출력하지 않고 2 로 끝난다. 틀린 설정을 fail2ban 이 읽게 하지 않는다.
관리자 대역이 비어 있으면 경고를 stderr 로 내고, 출력은 기본값(루프백)만으로 정상 진행한다.
iplist 는 백엔드와 같은 모듈을 쓴다 — 대시보드와 fail2ban 이 같은 규칙으로 목록을 읽게 하려고.
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from iplist import format_network, parse_ip_list  # noqa: E402

BASE = ["127.0.0.1/8", "::1"]
KEY = "SECDASH_F2B_IGNOREIP"


def read_env_value(path: str, key: str = KEY) -> str:
    """KEY=VALUE 파일에서 마지막 값을 읽는다. 따옴표는 벗긴다. 파일이나 키가 없으면 ""."""
    value = ""
    try:
        lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in lines:
        m = re.match(rf"^\s*(?:export\s+)?{key}\s*=\s*(.*?)\s*$", line)
        if m:
            value = m.group(1).strip().strip("'\"")
    return value


def render(template: str, admin_value: str):
    """(렌더된 설정, 해석 못 한 항목, 관리자 항목 목록)."""
    nets, invalid = parse_ip_list(admin_value)
    entries = []
    for item in BASE + [format_network(n) for n in nets]:
        if item not in entries:
            entries.append(item)
    admin = [e for e in entries if e not in BASE]
    pattern = re.compile(r"^ignoreip\s*=.*$", re.M)
    if len(pattern.findall(template)) != 1:
        raise ValueError("템플릿에 ignoreip 줄이 정확히 한 개 있어야 한다")
    return pattern.sub("ignoreip = " + " ".join(entries), template), invalid, admin


def main(argv: list[str]) -> int:
    args = [a for a in argv if a != "--client"]
    client = ""
    if "--client" in argv:
        i = argv.index("--client")
        client = argv[i + 1] if i + 1 < len(argv) else ""
        args = argv[:i] + argv[i + 2:]
    if not args:
        print(__doc__, file=sys.stderr)
        return 1
    template = pathlib.Path(args[0]).read_text(encoding="utf-8")
    env_file = args[1] if len(args) > 1 else "/etc/secdash/secdash.env"
    text, invalid, admin = render(template, read_env_value(env_file))
    if invalid:
        print(f"   !! {KEY} 에서 해석할 수 없는 항목: {' '.join(invalid)} — IP 또는 CIDR 만 쓸 수 있습니다", file=sys.stderr)
        return 2
    if not admin:
        hint = client or "<관리자 IP 또는 대역>"
        print(f"   [주의] 관리자 주소가 차단 예외에 없습니다. 비밀번호를 몇 번 틀린 관리자도 차단될 수 있습니다.\n"
              f"          {env_file} 에 {KEY}={hint} 를 적고 이 스크립트를 다시 실행하세요.", file=sys.stderr)
    else:
        print(f"   fail2ban·대시보드 차단 예외(관리자): {' '.join(admin)}", file=sys.stderr)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
