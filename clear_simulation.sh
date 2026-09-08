#!/bin/bash
# 시뮬레이션 흔적 정리: 테스트 로그 비우기, 시뮬레이션 이벤트/알림 삭제, 더미 프로세스 종료
cd "$(dirname "$0")"
[ -f backend/test_auth.log ] && : > backend/test_auth.log && echo "✓ cleared backend/test_auth.log"
pkill -f "_sim [0-9]+" 2>/dev/null; rm -f ./*_sim; echo "✓ killed simulation processes"
if [ -f backend/security_monitor.db ]; then
    (cd backend && venv/bin/python - <<'PY'
from database import SessionLocal, Event, Alert, BlockedIP
db = SessionLocal()
n1 = db.query(Event).filter(Event.is_simulation == True).delete(synchronize_session=False)
n2 = db.query(Alert).filter(Alert.is_simulation == True).delete(synchronize_session=False)
n3 = db.query(BlockedIP).filter(BlockedIP.ip_address == "192.168.1.200").delete(synchronize_session=False)
db.commit(); db.close()
print(f"✓ removed {n1} simulation events, {n2} alerts, {n3} block rows")
PY
    )
fi
echo ">>> done (실제 이벤트와 DB 는 유지됩니다)"
