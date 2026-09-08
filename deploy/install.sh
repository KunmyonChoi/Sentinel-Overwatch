#!/bin/bash
# 운영 설치 스크립트 (Ubuntu/Debian). root 로 실행.
#   sudo deploy/install.sh
# 하는 일: 전용 계정 생성 → /opt/secdash 복사 → venv/프론트 빌드 → sudoers/systemd 설치 → 서비스 시작
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 1; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST=/opt/secdash

echo ">> 1/6 전제 도구 확인"
for pkg in fail2ban rsyslog python3-venv; do
    dpkg -s "$pkg" >/dev/null 2>&1 || apt-get install -y "$pkg"
done
systemctl enable --now fail2ban
if ! fail2ban-client status sshd >/dev/null 2>&1; then
    cat > /etc/fail2ban/jail.d/secdash-sshd.conf <<'J'
[sshd]
enabled = true
J
    systemctl restart fail2ban
fi

echo ">> 2/6 전용 계정"
id secdash >/dev/null 2>&1 || useradd --system --home-dir "$DEST" --shell /usr/sbin/nologin secdash
usermod -aG adm secdash

echo ">> 3/6 코드 복사 및 빌드"
mkdir -p "$DEST"
rsync -a --delete --exclude venv --exclude node_modules --exclude '*.db*' --exclude .api_token --exclude logs "$SRC/backend" "$SRC/frontend" "$SRC/deploy" "$DEST/"
python3 -m venv "$DEST/backend/venv"
"$DEST/backend/venv/bin/pip" install -q -r "$DEST/backend/requirements.txt"
if command -v npm >/dev/null; then
    (cd "$DEST/frontend" && rm -f .env.local && npm ci --silent && npm run build --silent)
else
    echo "   npm 이 없어 프론트엔드를 빌드하지 못했습니다. 다른 머신에서 frontend/dist 를 빌드해 복사하세요."
fi
mkdir -p "$DEST/backend/logs"
chown -R secdash:secdash "$DEST"
chmod 750 "$DEST/backend"

echo ">> 4/6 설정"
mkdir -p /etc/secdash
[ -f /etc/secdash/secdash.env ] || cp "$SRC/deploy/secdash.env.example" /etc/secdash/secdash.env
chown root:secdash /etc/secdash/secdash.env && chmod 640 /etc/secdash/secdash.env

echo ">> 5/6 sudoers + systemd"
install -m 0440 -o root -g root "$SRC/deploy/sudoers-secdash" /etc/sudoers.d/secdash
visudo -cf /etc/sudoers.d/secdash
install -m 0644 "$SRC/deploy/secdash.service" /etc/systemd/system/secdash.service
systemctl daemon-reload
systemctl enable --now secdash
sleep 3

echo ">> 6/6 상태"
systemctl --no-pager --lines=5 status secdash || true
TOKEN=$(cat "$DEST/backend/.api_token" 2>/dev/null || echo "(아직 생성 안 됨 - 서비스 로그 확인)")
echo
echo "  대시보드 : http://127.0.0.1:8000  (원격이면 ssh -L 8000:127.0.0.1:8000 <서버>)"
echo "  API 토큰 : $TOKEN"
echo "  탐지 공백 : curl -s -H 'X-API-Token: $TOKEN' http://127.0.0.1:8000/api/monitors | python3 -m json.tool"
