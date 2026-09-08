#!/bin/bash
# 개발용 실행 스크립트. 운영 배포는 deploy/install.sh 를 사용하세요.
set -euo pipefail
cd "$(dirname "$0")"

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
for p in 8000 5173; do
    if ss -ltn "sport = :$p" | grep -q LISTEN; then
        echo "!! port $p already in use. Stop the other process first (ss -ltnp | grep :$p)"; exit 1
    fi
done

echo ">> starting backend on 127.0.0.1:8000"
(cd backend && exec venv/bin/python app.py) &
BACKEND_PID=$!

[ -d frontend/node_modules ] || (cd frontend && npm install)
echo ">> starting frontend dev server on 127.0.0.1:5173 (API proxied to backend)"
(cd frontend && exec npm run dev -- --host 127.0.0.1) &
FRONTEND_PID=$!

echo
echo "  Dashboard : http://127.0.0.1:5173"
echo "  API token : $TOKEN   (backend/.api_token)"
echo
echo "  탐지 공백(권한) 확인: 대시보드 '모니터 상태' 패널 또는 curl -H \"X-API-Token: \$TOKEN\" http://127.0.0.1:8000/api/monitors"
echo

trap 'kill $BACKEND_PID $FRONTEND_PID 2>/dev/null' EXIT INT TERM
wait
