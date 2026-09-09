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
(cd "$ROOT/frontend" && rm -f .env.local && npm ci --silent && npm run build --silent)

echo ">> 2/4 staging $NAME ($COMMIT)"
rm -rf "$STAGE" && mkdir -p "$STAGE/frontend"
rsync -a --exclude venv --exclude '*.db*' --exclude .api_token --exclude .env --exclude logs --exclude '*.log' --exclude __pycache__ --exclude .pytest_cache --exclude tests \
    "$ROOT/backend" "$STAGE/"
rsync -a "$ROOT/frontend/dist" "$STAGE/frontend/"
rsync -a --exclude build-release.sh "$ROOT/deploy" "$STAGE/"
cp "$ROOT/README.md" "$STAGE/"
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
