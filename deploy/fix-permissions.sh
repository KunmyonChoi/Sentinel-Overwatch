#!/bin/bash
# 권한 일괄 조치. root 로 실행한다. sudoers 에 인자까지 고정해 등록하므로 와일드카드가 없다.
#   sudo deploy/fix-permissions.sh            # 무엇을 바꿀지만 출력 (dry-run)
#   sudo deploy/fix-permissions.sh --apply    # 실제 적용
#
# 이 스크립트는 대상 경로를 인자로 받지 않는다. 무엇이 문제인지는 backend/fix_permissions.py 가
# root 권한으로 직접 다시 스캔해 정한다. 호출자가 임의 경로를 지정할 수 없게 하기 위함이다.
# 권한은 좁히기만 한다 (새 모드 = 기존 & 목표).
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo '{"ok": false, "error": "root 로 실행해야 합니다", "results": []}'; exit 1; }

BASE="$(cd "$(dirname "$0")/.." && pwd)"
PY="$BASE/backend/venv/bin/python"
[ -x "$PY" ] || PY=/usr/bin/python3

MODE=""
case "${1:-}" in
    --apply) MODE="--apply" ;;
    "")      MODE="" ;;
    *)       echo '{"ok": false, "error": "허용되지 않은 인자입니다 (--apply 만 가능)", "results": []}'; exit 2 ;;
esac

exec "$PY" "$BASE/backend/fix_permissions.py" ${MODE:+$MODE}
