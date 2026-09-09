#!/bin/bash
# 권한 일괄 조치. sudo 로 root 실행된다 (deploy/sudoers-secdash 에 인자까지 고정 등록).
#   sudo secdash-fix-permissions            # 무엇을 바꿀지만 출력 (dry-run)
#   sudo secdash-fix-permissions --apply    # 실제 적용
#
# 설계 원칙
#   1. 대상 경로를 인자로 받지 않는다. 무엇이 문제인지는 아래 파이썬 진입점이 root 권한으로
#      직접 다시 스캔해 정한다. 호출자가 임의 경로를 지정할 수 없다.
#   2. 권한은 좁히기만 한다 (새 모드 = 기존 & 목표).
#   3. root 로 실행할 코드는 root 만 쓸 수 있어야 한다.
#      대시보드 서비스 계정(secdash)이 쓸 수 있는 파일을 root 로 실행하면, 그 계정이 침해되는 순간
#      NOPASSWD sudo 규칙을 타고 그대로 root 가 된다. 그래서 진입점과 스캐너는 서비스 트리가 아니라
#      /usr/local/lib/secdash 에 root 소유로 설치하고, 인터프리터도 venv 가 아닌 시스템 python 을 쓴다.
#      아래 검사는 그 전제가 깨진 채 배포되었을 때 실행을 거부하기 위한 안전장치다.
set -euo pipefail

LIB=/usr/local/lib/secdash
PY=/usr/bin/python3
ENTRY="$LIB/fix_permissions.py"
SCANNER="$LIB/permissions_scan.py"

# 메시지에 따옴표·역슬래시를 쓰지 않는다 (JSON 을 손으로 만들기 때문)
refuse() { echo "{\"ok\": false, \"error\": \"$1\", \"fix_hint\": \"$2\", \"results\": [], \"changed\": 0}"; exit 3; }

must_be_root_owned() {
    local p real
    p="$1"
    real="$(readlink -f "$p" 2>/dev/null || true)"
    [ -n "$real" ] && [ -e "$real" ] || refuse "필요한 파일이 없습니다: $p" "sudo deploy/update.sh 로 다시 배포하세요."
    [ "$(stat -c %u "$real")" = "0" ] || refuse "root 소유가 아니라 실행을 거부했습니다: $real" "sudo chown root:root $real"
    if [ -n "$(find "$real" -maxdepth 0 -perm /022 -print -quit 2>/dev/null)" ]; then
        refuse "다른 계정이 쓸 수 있어 실행을 거부했습니다: $real" "sudo chmod go-w $real"
    fi
}

# --- MAIN --- (이 줄 위쪽은 정의만. 테스트가 여기서 잘라 함수만 가져다 쓴다)

[ "$(id -u)" -eq 0 ] || refuse "root 로 실행해야 합니다" "deploy/sudoers-secdash 설치 여부를 확인하세요."

MODE=""
case "${1:-}" in
    --apply) MODE="--apply" ;;
    "")      MODE="" ;;
    *)       refuse "허용되지 않은 인자입니다 (--apply 만 가능)" "" ;;
esac

# 실행 체인 전체가 root 소유여야 한다: 디렉터리, 진입점, 스캐너, 인터프리터
for p in "$LIB" "$ENTRY" "$SCANNER" "$PY"; do
    must_be_root_owned "$p"
done

exec "$PY" "$ENTRY" ${MODE:+$MODE}
