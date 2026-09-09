"""
권한 일괄 조치기. root 로 실행된다 (deploy/fix-permissions.sh 를 거쳐서).

설계상 가장 중요한 것: **호출자가 경로를 지정할 수 없다.**
API 는 "지금 문제인 것을 고쳐라" 라고만 말하고, 무엇이 문제인지는 이 스크립트가 root 권한으로
직접 다시 스캔해 정한다. 그래서 API 토큰이 유출되어도 임의 경로의 권한을 건드릴 수 없다.

두 번째 방어: 권한은 **좁히기만** 한다. 새 모드는 `기존 & 목표` 로 계산하므로 항상 기존의
부분집합이다. 넓히는 연산은 코드에 존재하지 않는다.

세 번째 방어: O_NOFOLLOW 로 열어 fchmod 한다. 스캔과 적용 사이에 대상이 심볼릭 링크로
바뀌어도 엉뚱한 파일의 권한이 바뀌지 않는다.

출력은 JSON 한 덩어리. 백엔드가 이것을 읽어 이벤트로 기록한다.
  --apply 없이 실행하면 무엇을 바꿀지만 계산한다 (기본값은 dry-run).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 배포 시에는 permissions_scan.py 와 나란히 /usr/local/lib/secdash 에 root 소유로 설치된다.
# 개발 트리에서는 integrations 패키지 안에 있다. 어느 쪽이든 같은 판정 규칙을 쓴다.
try:
    from permissions_scan import human_homes, mode_of, narrow, scan  # noqa: E402
except ImportError:
    from integrations.permissions_scan import human_homes, mode_of, narrow, scan  # noqa: E402

DEFAULT_TREES = ["/etc"]


def apply_one(path: str, target: int) -> dict:
    """한 경로의 권한을 좁힌다. 적용 직전에 상태를 다시 확인한다."""
    before = mode_of(path)
    if before is None:
        return {"path": path, "applied": False, "error": "심볼릭 링크이거나 접근할 수 없음"}
    after = narrow(before, target)
    if after == before:
        return {"path": path, "before": oct(before)[2:], "after": oct(before)[2:], "applied": False,
                "error": "이미 목표보다 좁음 (넓히지 않는다)"}
    try:
        # O_NOFOLLOW: 스캔 이후 대상이 링크로 바뀌었어도 링크가 가리키는 파일을 건드리지 않는다
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as e:
        return {"path": path, "before": oct(before)[2:], "applied": False, "error": f"열기 실패: {e}"}
    try:
        os.fchmod(fd, after)
    except OSError as e:
        return {"path": path, "before": oct(before)[2:], "applied": False, "error": f"chmod 실패: {e}"}
    finally:
        os.close(fd)
    return {"path": path, "before": oct(before)[2:], "after": oct(after)[2:], "applied": True,
            "kind": "", "error": ""}


def main() -> int:
    ap = argparse.ArgumentParser(description="world-writable 설정 파일과 노출된 시크릿의 권한을 좁힌다 (좁히기만 한다)")
    ap.add_argument("--apply", action="store_true", help="실제로 적용한다. 없으면 계획만 출력")
    ap.add_argument("--trees", default=",".join(DEFAULT_TREES), help="추가로 훑을 디렉터리 (쉼표 구분)")
    args = ap.parse_args()

    if os.geteuid() != 0:
        print(json.dumps({"ok": False, "error": "root 로 실행해야 합니다", "results": []}, ensure_ascii=False))
        return 1

    trees = [t.strip() for t in args.trees.split(",") if t.strip()]
    findings = scan(human_homes(), trees)

    results = []
    for f in findings:
        target = f.get("target")
        if not isinstance(target, int):
            continue
        if args.apply:
            r = apply_one(f["path"], target)
        else:
            before = mode_of(f["path"])
            after = narrow(before, target) if before is not None else None
            r = {"path": f["path"], "before": oct(before)[2:] if before is not None else "?",
                 "after": oct(after)[2:] if after is not None else "?", "applied": False, "error": ""}
        r["kind"] = f["kind"]
        r["severity"] = f["severity"]
        results.append(r)

    print(json.dumps({
        "ok": True,
        "applied": bool(args.apply),
        "scanned_homes": human_homes(),
        "scanned_trees": trees,
        "changed": sum(1 for r in results if r.get("applied")),
        "results": results,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
