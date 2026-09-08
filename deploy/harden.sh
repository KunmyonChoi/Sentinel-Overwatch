#!/bin/bash
# Lynis 결과 중 부작용이 낮은 항목을 적용한다. 기본은 dry-run (무엇을 바꿀지 출력만).
#   sudo deploy/harden.sh                 # 점검 + 변경 예정 목록
#   sudo deploy/harden.sh --apply         # 실제 적용
#   sudo deploy/harden.sh --apply --disable-usb-storage   # USB 저장장치 드라이버까지 차단 (물리 접근 가능한 서버)
#   추가 플래그: --remove-nginx (미운영 nginx 제거)  --disable-cups (인쇄 불필요 시 CUPS 중지·마스크)
#               --grub-password-hash '<grub.pbkdf2.sha512...>'  (BOOT-5122; 해시는 grub-mkpasswd-pbkdf2 로 생성)
# 적용 항목: AUTH-9216 점검, DEB-0831/needrestart, PKGS-7410 옛 커널, LOGG-2190, HOME-9304, KRNL-6000 sysctl,
#           AUTH-9328/9230/9286 login.defs, KRNL-5820 코어 덤프, NETW-3200 모듈, BANN-7126/7130, DEB-0280/PKGS-7370/7394, PKGS-7346
# 건드리지 않음: rp_filter/ip_forward (docker), 컴파일러 제한(HRDN-7222), GRUB 비밀번호(BOOT-5122), nginx/CUPS 판단 항목
set -uo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 1; }
APPLY=0; USB=0; NGINX=0; CUPS=0; GRUB_HASH=""
while [ $# -gt 0 ]; do
    case "$1" in
        --apply) APPLY=1;; --disable-usb-storage) USB=1;; --remove-nginx) NGINX=1;; --disable-cups) CUPS=1;;
        --grub-password-hash) GRUB_HASH="$2"; shift;;
        *) echo "unknown arg $1"; exit 1;;
    esac; shift
done
MODE=$([ $APPLY -eq 1 ] && echo "APPLY" || echo "DRY-RUN")
changes=0
say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
plan() { printf '   [%s] %s\n' "$MODE" "$*"; changes=$((changes+1)); }
run()  { plan "$*"; if [ $APPLY -eq 1 ]; then eval "$@"; fi; return 0; }
# 파일에 key value 를 보장 (없으면 추가, 다르면 교체)
ensure_line() { # file regex line
    local f=$1 re=$2 line=$3
    if grep -Eq "$re" "$f" 2>/dev/null; then
        grep -Fxq "$line" "$f" || run "sed -i -E 's|$re|$line|' '$f'"
    else
        run "printf '%s\n' '$line' >> '$f'"
    fi
}
write_if_diff() { # dst <<content via stdin
    local dst=$1 tmp; tmp=$(mktemp); cat > "$tmp"
    if ! cmp -s "$tmp" "$dst" 2>/dev/null; then
        plan "write $dst"; [ $APPLY -eq 1 ] && install -m 0644 "$tmp" "$dst"
        [ $APPLY -eq 0 ] && sed 's/^/        | /' "$tmp"
    fi
    rm -f "$tmp"
}

say "1. AUTH-9216 그룹 파일 일관성 (grpck -r, 읽기 전용)"
if out=$(grpck -r 2>&1); then echo "   이상 없음"; else
    echo "$out" | sed 's/^/   /'
    echo "   → 수정은 대화형입니다: sudo grpck   (없는 사용자를 그룹에서 제거하거나 gshadow 항목을 추가)"
fi

say "2. 패키지: needrestart, libpam-tmpdir, debsums, apt-show-versions, apt-listchanges (DEB-0831/0280, PKGS-7370/7394, DEB-0811)"
missing=""
for p in needrestart libpam-tmpdir debsums apt-show-versions apt-listchanges; do dpkg -s "$p" >/dev/null 2>&1 || missing="$missing $p"; done
if [ -n "$missing" ]; then run "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq$missing"; else echo "   모두 설치됨"; fi

say "3. LOGG-2190 삭제된 라이브러리를 아직 쓰는 프로세스 (needrestart 목록 모드, 재시작은 하지 않음)"
if command -v needrestart >/dev/null; then needrestart -r l 2>/dev/null | sed 's/^/   /' | head -30; else echo "   (needrestart 설치 후 다시 실행하면 목록이 나옵니다)"; fi

say "4. PKGS-7410 옛 커널 제거 (실행 중 커널, 최신 설치본, 직전 버전 1개는 유지)"
cur=$(uname -r); cur=${cur%-generic}
all=$(dpkg-query -W -f='${binary:Package}\n' 'linux-image-[0-9]*' 2>/dev/null | grep -E '^linux-image-[0-9]' | sed -E 's/^linux-image-//; s/-generic$//' | sort -uV)
latest=$(echo "$all" | tail -1)
prev=$(echo "$all" | grep -x -B1 "$cur" | head -1); [ "$prev" = "$cur" ] && prev=""
remove_versions=$(echo "$all" | grep -v -x -e "$cur" -e "$latest" -e "${prev:-__none__}")
if [ -z "$remove_versions" ]; then echo "   제거할 옛 커널 없음"; else
    pkgs=""
    for v in $remove_versions; do pkgs="$pkgs $(dpkg-query -W -f='${binary:Package} ' "linux-image-$v*" "linux-headers-$v*" "linux-modules-$v*" "linux-modules-extra-$v*" 2>/dev/null)"; done
    echo "   유지: $cur (실행 중), $latest (최신)${prev:+, $prev (폴백)}"; echo "   제거 대상 $(echo $pkgs | wc -w)개:"; echo "$pkgs" | tr ' ' '\n' | grep . | sed 's/^/     /' | head -40
    run "DEBIAN_FRONTEND=noninteractive apt-get purge -y -qq $pkgs && update-grub"
fi
# dkms 가 빌드한 모듈 때문에 남은 /lib/modules/<제거된 커널> 디렉터리 정리
installed_vers=$(dpkg-query -W -f='${binary:Package}\n' 'linux-image-[0-9]*' 2>/dev/null | sed -E 's/^linux-image-//' | sort -u)
for d in /lib/modules/*/; do
    v=$(basename "$d")
    echo "$installed_vers" | grep -qx "$v" && continue
    [ "$v" = "$(uname -r)" ] && continue
    run "rm -rf '/lib/modules/$v'"
done

say "5. HOME-9304 홈 디렉터리 권한 750, 신규 계정 기본 0750"
for h in /home/*/; do [ -d "$h" ] || continue; m=$(stat -c %a "$h"); [ "$m" = "750" ] || [ "$m" = "700" ] || run "chmod 750 '$h'"; done
ensure_line /etc/adduser.conf '^#?DIR_MODE=.*' 'DIR_MODE=0750'

say "6. KRNL-6000 sysctl (Lynis 가 다르다고 본 값 중 docker 와 무관한 것만)"
grep -oE "sysctl key [^ ]+ has a different value[^,]*|Expected[^ ]* Real[^ ]*" /var/log/lynis.log 2>/dev/null | sed 's/^/   lynis: /' | head -20
# 파일명은 zz- 로: /usr/lib/sysctl.d/protect-links.conf 등 배포판 기본값보다 뒤에 적용돼야 덮어쓴다
[ -f /etc/sysctl.d/90-secdash-hardening.conf ] && run "rm -f /etc/sysctl.d/90-secdash-hardening.conf"
write_if_diff /etc/sysctl.d/zz-secdash-hardening.conf <<'S'
# secdash hardening (Lynis KRNL-6000). rp_filter / ip_forward 는 docker 때문에 건드리지 않는다.
kernel.kptr_restrict = 2
kernel.dmesg_restrict = 1
kernel.sysrq = 0
kernel.core_uses_pid = 1
kernel.yama.ptrace_scope = 1
fs.protected_fifos = 2
fs.protected_regular = 2
fs.suid_dumpable = 0
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.secure_redirects = 0
net.ipv4.conf.default.secure_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0
net.ipv4.conf.all.log_martians = 1
net.ipv4.conf.default.log_martians = 1
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.icmp_ignore_bogus_error_responses = 1
net.ipv4.tcp_syncookies = 1
net.ipv6.conf.all.accept_redirects = 0
net.ipv6.conf.default.accept_redirects = 0
net.ipv6.conf.all.accept_source_route = 0
net.ipv6.conf.default.accept_source_route = 0
S
[ $APPLY -eq 1 ] && sysctl -q --system >/dev/null 2>&1

say "7. login.defs: umask 027, 비밀번호 사용 기간, 해싱 라운드 (AUTH-9328/9286/9230)"
ensure_line /etc/login.defs '^UMASK[[:space:]].*' 'UMASK		027'
ensure_line /etc/login.defs '^PASS_MAX_DAYS[[:space:]].*' 'PASS_MAX_DAYS	365'
ensure_line /etc/login.defs '^PASS_MIN_DAYS[[:space:]].*' 'PASS_MIN_DAYS	1'
ensure_line /etc/login.defs '^PASS_WARN_AGE[[:space:]].*' 'PASS_WARN_AGE	14'
ensure_line /etc/login.defs '^#?SHA_CRYPT_MIN_ROUNDS[[:space:]].*' 'SHA_CRYPT_MIN_ROUNDS 65536'
ensure_line /etc/login.defs '^#?SHA_CRYPT_MAX_ROUNDS[[:space:]].*' 'SHA_CRYPT_MAX_ROUNDS 65536'
echo "   (umask 027: 새 파일이 기본적으로 다른 그룹에 읽히지 않습니다. 공유 디렉터리는 setgid+ACL 로 별도 관리)"

say "8. KRNL-5820 코어 덤프 비활성화"
write_if_diff /etc/security/limits.d/90-secdash-nocore.conf <<'S'
* hard core 0
S
if [ -d /etc/systemd/coredump.conf.d ] || [ -f /etc/systemd/coredump.conf ]; then
    mkdir -p /etc/systemd/coredump.conf.d
    write_if_diff /etc/systemd/coredump.conf.d/90-secdash.conf <<'S'
[Coredump]
Storage=none
ProcessSizeMax=0
S
fi

say "9. NETW-3200 미사용 네트워크 프로토콜 모듈 차단 (dccp sctp rds tipc)$([ $USB -eq 1 ] && echo ' + usb-storage')"
{
    echo "# secdash hardening (Lynis NETW-3200)"
    for m in dccp sctp rds tipc; do echo "install $m /bin/false"; echo "blacklist $m"; done
    [ $USB -eq 1 ] && { echo "# USB-1000"; echo "install usb-storage /bin/false"; echo "blacklist usb-storage"; }
} | write_if_diff /etc/modprobe.d/90-secdash-hardening.conf

say "10. BANN-7126/7130 로그인 경고 배너"
banner='이 시스템은 허가된 사용자만 접근할 수 있습니다. 모든 접속과 명령은 기록되며 감사 대상입니다.
Authorized access only. All activity on this system is logged and monitored.'
printf '%s\n' "$banner" | write_if_diff /etc/issue.net
printf '%s\n\n' "$banner" | write_if_diff /etc/issue
if [ -d /etc/ssh/sshd_config.d ]; then
    printf 'Banner /etc/issue.net\n' | write_if_diff /etc/ssh/sshd_config.d/90-secdash-banner.conf
    [ $APPLY -eq 1 ] && sshd -t && systemctl reload ssh 2>/dev/null
fi

say "11. PKGS-7346 제거된 패키지의 설정 잔재 purge"
rc=$(dpkg -l | awk '/^rc/{print $2}')
if [ -z "$rc" ]; then echo "   없음"; else
    echo "   $(echo "$rc" | wc -l)개: $(echo $rc | cut -c1-200)..."
    run "dpkg --purge $(echo $rc) >/dev/null"
fi

say "12. 선택 항목: nginx 제거 / CUPS 비활성화 / GRUB 비밀번호"
if [ $NGINX -eq 1 ]; then
    if dpkg -s nginx >/dev/null 2>&1 || dpkg -s nginx-common >/dev/null 2>&1; then
        serving=$(grep -rlsE "^\s*listen" /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ 2>/dev/null | wc -l)
        if systemctl is-active --quiet nginx && [ "$serving" -gt 0 ]; then
            echo "   !! nginx 가 서버 블록 $serving 개를 서비스 중입니다. 제거를 건너뜁니다 (HTTP-6710 은 HTTPS 적용으로 대응)."
        else
            [ "$serving" -eq 0 ] && systemctl is-active --quiet nginx && echo "   nginx 실행 중이나 서버 블록 없음 (idle 워커만 존재) → 정지 후 제거"
            run "systemctl disable --now nginx 2>/dev/null; DEBIAN_FRONTEND=noninteractive apt-get purge -y -qq 'nginx*' && rm -rf /etc/nginx"
        fi
    else echo "   nginx 없음"; fi
fi
if [ $CUPS -eq 1 ]; then
    for u in cups.service cups.socket cups.path cups-browsed.service; do
        systemctl list-unit-files "$u" --no-legend 2>/dev/null | grep -q . || continue
        if systemctl is-enabled --quiet "$u" 2>/dev/null || systemctl is-active --quiet "$u" 2>/dev/null; then run "systemctl disable --now '$u' && systemctl mask '$u'"; fi
    done
    echo "   (purge 대신 mask: cups 는 데스크톱 메타패키지 의존성이라 제거하면 다른 패키지가 딸려 나갈 수 있음)"
fi
if [ -n "$GRUB_HASH" ]; then
    case "$GRUB_HASH" in grub.pbkdf2.sha512.*) ;; *) echo "   !! 해시 형식이 아닙니다. grub-mkpasswd-pbkdf2 출력의 grub.pbkdf2.sha512.… 부분을 넘기세요"; GRUB_HASH="";; esac
fi
if [ -n "$GRUB_HASH" ]; then
    { printf '#!/bin/sh\n# BOOT-5122: GRUB 메뉴 편집/복구 셸에 비밀번호 요구. 기본 항목은 --unrestricted 라 무인 재부팅은 그대로 된다.\n'
      printf 'cat <<EOF\nset superusers="admin"\npassword_pbkdf2 admin %s\nEOF\n' "$GRUB_HASH"; } | write_if_diff /etc/grub.d/01_secdash_password
    [ $APPLY -eq 1 ] && chmod 755 /etc/grub.d/01_secdash_password
    if ! grep -q -- '--unrestricted' /etc/grub.d/10_linux; then
        run "sed -i 's/^CLASS=\"--class gnu-linux --class gnu --class os\"/CLASS=\"--class gnu-linux --class gnu --class os --unrestricted\"/' /etc/grub.d/10_linux"
    fi
    [ $APPLY -eq 1 ] && update-grub >/dev/null 2>&1 && echo "   GRUB 갱신 완료 (메뉴 편집 시 admin 비밀번호 필요, 기본 부팅은 제한 없음)"
else
    echo "   GRUB 비밀번호: 물리 접근 가능한 서버라면 권장. 터미널에서 grub-mkpasswd-pbkdf2 로 해시를 만든 뒤 --grub-password-hash 로 넘기세요."
fi

say "요약"
if [ $APPLY -eq 1 ]; then
    echo "   적용 완료 ($changes 항목). 다음 Lynis 감사(04:15) 또는 지금 실행: sudo lynis audit system --cronjob --quiet"
    echo "   대시보드의 무결성/영속화 알림에 이 스크립트의 변경이 '최근 관리자 활동' 과 함께 표시됩니다 → 확인(ack) 처리하세요."
else
    echo "   변경 예정 $changes 항목. 적용: sudo deploy/harden.sh --apply"
fi
