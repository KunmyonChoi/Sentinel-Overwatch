#!/bin/bash
# 개발용 실행 스크립트. 운영 배포는 deploy/install.sh / deploy/update.sh 를 사용하세요.
#
# 같은 호스트에 운영 인스턴스(secdash.service, 8000)가 떠 있으면 포트가 겹칩니다.
# 그때는 비어 있는 포트를 골라 쓰세요. 운영 인스턴스는 건드리지 않습니다.
#   SECDASH_PORT=8001 SECDASH_UI_PORT=5174 ./start.sh
set -euo pipefail
cd "$(dirname "$0")"

API_PORT="${SECDASH_PORT:-8000}"
UI_PORT="${SECDASH_UI_PORT:-5173}"

# 백엔드 venv
if [ ! -x backend/venv/bin/python ]; then
    echo ">> creating venv"
    rm -rf backend/venv
    python3 -m venv backend/venv
fi
backend/venv/bin/pip install -q -r backend/requirements.txt

# API 토큰 (없으면 백엔드가 처음 실행할 때 생성)
if [ ! -f backend/.api_token ]; then
    (cd backend && venv/bin/python -c "import config; print(config.API_TOKEN)" >/dev/null)
fi
TOKEN=$(cat backend/.api_token)
# 개발 편의: Vite 가 토큰을 자동 주입 (운영 빌드에는 넣지 마세요)
printf 'VITE_API_TOKEN=%s\n' "$TOKEN" > frontend/.env.local

# 포트 점유 확인 (다른 프로세스를 함부로 죽이지 않는다)
busy() { ss -ltn "sport = :$1" | grep -q LISTEN; }
if busy "$API_PORT"; then
    echo "!! ${API_PORT} 번 포트를 이미 누가 쓰고 있습니다."
    if systemctl is-active --quiet secdash 2>/dev/null; then
        echo "   운영 인스턴스(secdash.service)가 쓰는 중입니다. 그건 그대로 두세요."
    fi
    echo "   비어 있는 포트로 띄우려면:"
    echo "     SECDASH_PORT=8001 SECDASH_UI_PORT=5174 ./start.sh"
    echo "   지금 누가 쓰는지: ss -ltnp | grep :${API_PORT}"
    exit 1
fi
if busy "$UI_PORT"; then
    echo "!! ${UI_PORT} 번 포트를 이미 누가 쓰고 있습니다. SECDASH_UI_PORT=5174 로 바꿔 실행하세요."
    exit 1
fi

echo ">> starting backend on 127.0.0.1:${API_PORT}"
(cd backend && SECDASH_PORT="$API_PORT" exec venv/bin/python app.py) &
BACKEND_PID=$!

[ -d frontend/node_modules ] || (cd frontend && npm install)
echo ">> starting frontend dev server on 127.0.0.1:${UI_PORT} (API proxied to backend)"
# vite.config.js 의 프록시가 이 값을 따라간다
(cd frontend && SECDASH_API_URL="http://127.0.0.1:${API_PORT}" exec npm run dev -- --host 127.0.0.1 --port "$UI_PORT" --strictPort) &
FRONTEND_PID=$!

echo
echo "  Dashboard : http://127.0.0.1:${UI_PORT}"
echo "  API token : $TOKEN   (backend/.api_token)"
echo
echo "  탐지 공백(권한) 확인: 대시보드 '자세히 보기 → 지킴이가 보고 있는 것'"
echo "  또는: curl -H \"X-API-Token: \$TOKEN\" http://127.0.0.1:${API_PORT}/api/monitors"
echo

trap 'kill $BACKEND_PID $FRONTEND_PID 2>/dev/null' EXIT INT TERM
wait
