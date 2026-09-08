#!/bin/bash
# 운영 인스턴스(/opt/secdash) 에 코드 변경만 반영하고 재시작한다. root 로 실행.
#   sudo deploy/update.sh            # 백엔드 + (빌드돼 있으면) 프론트엔드 dist
# DB, API 토큰, 로그, venv 는 건드리지 않는다. 의존성이 바뀌었으면 --deps 를 붙인다.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 1; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST=/opt/secdash

rsync -a --exclude venv --exclude '*.db*' --exclude .api_token --exclude logs --exclude __pycache__ --exclude .env --exclude tests "$SRC/backend/" "$DEST/backend/"
[ -d "$SRC/frontend/dist" ] && rsync -a --delete "$SRC/frontend/dist/" "$DEST/frontend/dist/"
rsync -a "$SRC/deploy/" "$DEST/deploy/"
if [ "${1:-}" = "--deps" ]; then
    "$DEST/backend/venv/bin/pip" install -q -r "$DEST/backend/requirements.txt"
fi
if ! cmp -s "$SRC/deploy/secdash.service" /etc/systemd/system/secdash.service; then
    install -m 0644 "$SRC/deploy/secdash.service" /etc/systemd/system/secdash.service
    systemctl daemon-reload
fi
if ! cmp -s "$SRC/deploy/sudoers-secdash" /etc/sudoers.d/secdash; then
    install -m 0440 -o root -g root "$SRC/deploy/sudoers-secdash" /etc/sudoers.d/secdash && visudo -cf /etc/sudoers.d/secdash
fi
chown -R secdash:secdash "$DEST/backend" "$DEST/frontend" 2>/dev/null || true
systemctl restart secdash
sleep 6
systemctl --no-pager --lines=3 status secdash | head -5
TOKEN=$(cat "$DEST/backend/.api_token")
curl -s -H "X-API-Token: $TOKEN" http://127.0.0.1:8000/api/monitors | python3 -c "import sys,json; [print(f\"{m['name']:20} {m['health']:9} {m['health_reason']}\") for m in json.load(sys.stdin)]"
