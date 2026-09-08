#!/bin/bash
# 호스트 도구 설정을 반영한다 (root). install.sh / update.sh 가 호출하며 단독 실행도 가능.
#   sudo deploy/apply-host-config.sh [소스 디렉터리]
# 1) fail2ban: jail.d/secdash.conf (ignoreip, bantime.increment, recidive)
# 2) auditd  : rules.d/secdash.rules → augenrules --load
# 3) lynis   : cron.d/secdash-lynis (매일 04:15)
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 1; }
SRC="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
changed=""

install_if_changed() {  # src dst mode
    if ! cmp -s "$1" "$2"; then install -m "$3" -o root -g root "$1" "$2"; changed="$changed $2"; return 0; fi
    return 1
}

# 1) fail2ban
if command -v fail2ban-client >/dev/null; then
    if install_if_changed "$SRC/deploy/fail2ban-secdash.conf" /etc/fail2ban/jail.d/secdash.conf 0644; then
        fail2ban-client reload >/dev/null && echo "   fail2ban reloaded (jails: $(fail2ban-client status | grep -o 'Jail list:.*' | cut -d: -f2 | xargs))"
    fi
fi

# 2) auditd
if command -v augenrules >/dev/null; then
    mkdir -p /etc/audit/rules.d
    if install_if_changed "$SRC/deploy/audit-secdash.rules" /etc/audit/rules.d/secdash.rules 0640; then
        augenrules --load >/dev/null 2>&1 && echo "   audit rules loaded ($(auditctl -l 2>/dev/null | grep -c secdash) secdash rules)" || echo "   !! augenrules --load 실패: auditctl -l 로 확인하세요"
    fi
else
    echo "   auditd 미설치: 명령 실행 감사는 30초 샘플링으로 동작합니다 (sudo apt install auditd)"
fi

# 3) lynis
if command -v lynis >/dev/null || [ -x /usr/sbin/lynis ]; then
    install_if_changed "$SRC/deploy/cron-secdash-lynis" /etc/cron.d/secdash-lynis 0644 && echo "   lynis cron installed (daily 04:15)"
    if [ ! -f /var/log/lynis-report.dat ]; then
        echo "   첫 Lynis 감사를 지금 실행합니다 (1~2분)..."
        nice -n 10 /usr/sbin/lynis audit system --cronjob --quiet >/dev/null 2>&1 || true
    fi
else
    echo "   lynis 미설치: sudo apt install lynis"
fi
[ -n "$changed" ] && echo "   updated:$changed" || echo "   host config unchanged"
