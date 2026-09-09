#!/bin/bash
# 운영 설치 스크립트 (Ubuntu/Debian). root 로 실행.
#   sudo deploy/install.sh
# 하는 일: 전용 계정 생성 → /opt/secdash 복사 → venv/프론트 빌드 → sudoers/systemd 설치 → 서비스 시작
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 1; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST=/opt/secdash

echo ">> 1/6 전제 도구 확인 (fail2ban, rsyslog, auditd, lynis)"
for pkg in fail2ban rsyslog python3-venv auditd lynis; do
    dpkg -s "$pkg" >/dev/null 2>&1 || apt-get install -y "$pkg"
done
systemctl enable --now fail2ban auditd
# 호스트 도구 설정 (fail2ban 보강, auditd 규칙, lynis 크론) — update.sh 와 같은 파일을 쓴다
"$SRC/deploy/apply-host-config.sh" "$SRC"

echo ">> 2/6 전용 계정"
id secdash >/dev/null 2>&1 || useradd --system --home-dir "$DEST" --shell /usr/sbin/nologin secdash
usermod -aG adm secdash

echo ">> 3/6 코드 복사 및 빌드 (버전 $(cat "$SRC/VERSION" 2>/dev/null || echo dev))"
mkdir -p "$DEST"
rsync -a --delete --exclude venv --exclude node_modules --exclude '*.db*' --exclude .api_token --exclude logs --exclude __pycache__ --exclude .env "$SRC/backend" "$SRC/frontend" "$SRC/deploy" "$DEST/"
for f in VERSION RELEASE README.md; do [ -f "$SRC/$f" ] && cp "$SRC/$f" "$DEST/"; done
[ -d "$SRC/docs" ] && rsync -a --delete "$SRC/docs/" "$DEST/docs/"
[ -x "$DEST/backend/venv/bin/python" ] || python3 -m venv "$DEST/backend/venv"
if [ -d "$SRC/wheels" ]; then
    "$DEST/backend/venv/bin/pip" install -q --no-index --find-links "$SRC/wheels" -r "$DEST/backend/requirements.txt"
else
    "$DEST/backend/venv/bin/pip" install -q -r "$DEST/backend/requirements.txt"
fi
if [ -f "$DEST/frontend/dist/index.html" ]; then
    echo "   빌드된 프론트엔드 사용 (frontend/dist)"
elif command -v npm >/dev/null; then
    (cd "$DEST/frontend" && rm -f .env.local && npm ci --silent && npm run build --silent)
else
    echo "   !! frontend/dist 가 없고 npm 도 없습니다. deploy/build-release.sh 로 만든 압축본을 사용하세요."
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
