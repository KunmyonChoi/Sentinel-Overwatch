#!/bin/bash
# 배포용 압축본을 만든다. 대상 서버에는 git/node 가 필요 없다 (python3-venv, apt 만 필요).
#   deploy/build-release.sh              → dist-release/secdash-<version>.tar.gz (+ .sha256)
#   deploy/build-release.sh --wheels     → pip 휠까지 포함 (오프라인 서버용, 같은 아키텍처/파이썬 버전에서 빌드)
# 압축본 설치: tar xzf secdash-<version>.tar.gz && sudo secdash-<version>/deploy/install.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WHEELS=0
for a in "$@"; do case "$a" in --wheels) WHEELS=1;; *) echo "unknown arg $a"; exit 1;; esac; done

VERSION=$(cat "$ROOT/VERSION" 2>/dev/null || echo "0.0.0")
if git -C "$ROOT" rev-parse --short HEAD >/dev/null 2>&1; then
    COMMIT=$(git -C "$ROOT" rev-parse --short HEAD)
    git -C "$ROOT" diff --quiet || COMMIT="$COMMIT-dirty"
else
    COMMIT="unknown"
fi
NAME="secdash-$VERSION"
OUT="$ROOT/dist-release"
STAGE="$OUT/$NAME"

echo ">> 1/4 frontend build"
# 개발 토큰이 화면에 박히지 않게: start.sh 가 쓴 .env.local 도, 셸에 남은 VITE_API_TOKEN 도 쓰지 않는다
(cd "$ROOT/frontend" && rm -f .env.local && npm ci --silent && VITE_API_TOKEN= npm run build --silent)

echo ">> 2/4 staging $NAME ($COMMIT)"
rm -rf "$STAGE" && mkdir -p "$STAGE/frontend"
rsync -a --exclude venv --exclude '*.db*' --exclude .api_token --exclude .env --exclude logs --exclude '*.log' --exclude __pycache__ --exclude .pytest_cache --exclude tests \
    "$ROOT/backend" "$STAGE/"
rsync -a "$ROOT/frontend/dist" "$STAGE/frontend/"
rsync -a --exclude build-release.sh "$ROOT/deploy" "$STAGE/"
# 제3자 고지는 대상 서버가 실제로 받게 될 버전으로 만든다. 개발 venv 나 시스템 파이썬의 버전을 적으면
# 고지가 틀린 채로 조용히 나간다(실제로 그랬다). 그래서 빌드 때마다 빈 venv 에 requirements 를 새로 받는다.
NOTICES_VENV="$OUT/.notices-venv"
rm -rf "$NOTICES_VENV"
python3 -m venv "$NOTICES_VENV"
"$NOTICES_VENV/bin/pip" install -q -r "$ROOT/backend/requirements.txt"
"$NOTICES_VENV/bin/python" "$ROOT/deploy/gen-notices.py" >/dev/null
rm -rf "$NOTICES_VENV"
cp "$ROOT/README.md" "$ROOT/LICENSE" "$ROOT/THIRD_PARTY_NOTICES.md" "$STAGE/"
[ -d "$ROOT/docs" ] && rsync -a "$ROOT/docs" "$STAGE/"
printf '%s\n' "$VERSION" > "$STAGE/VERSION"
printf 'version=%s\ncommit=%s\nbuilt=%s\n' "$VERSION" "$COMMIT" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STAGE/RELEASE"

if [ $WHEELS -eq 1 ]; then
    echo ">> 3/4 pip wheels (offline install)"
    python3 -m pip download -q -r "$ROOT/backend/requirements.txt" -d "$STAGE/wheels"
else
    echo ">> 3/4 wheels skipped (--wheels 로 포함 가능)"
fi

echo ">> 4/4 archive"
(cd "$OUT" && tar czf "$NAME.tar.gz" "$NAME" && sha256sum "$NAME.tar.gz" > "$NAME.tar.gz.sha256")
rm -rf "$STAGE"
ls -la "$OUT/$NAME.tar.gz" "$OUT/$NAME.tar.gz.sha256"
echo
echo "대상 서버에서:"
echo "  sha256sum -c $NAME.tar.gz.sha256 && tar xzf $NAME.tar.gz && sudo $NAME/deploy/install.sh"
