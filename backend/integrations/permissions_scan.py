"""
파일 권한 스캐너 (순수 로직).

표준 라이브러리만 쓴다. DB·설정·네트워크에 의존하지 않는다 —
root 로 도는 조치 스크립트(deploy/fix-permissions.sh)가 이 모듈만 가져다 쓰기 때문이다.
감시 계층(monitor/permissions.py)과 조치 계층이 같은 판정 규칙을 공유해야 서로 어긋나지 않는다.

보는 것은 두 가지다.
  1. world/group-writable — 다른 로컬 계정이 쓸 수 있는 설정 파일·디렉터리.
     ~/.config 가 열려 있으면 autostart 에 .desktop 을 넣어 그 계정의 세션에서 코드를 실행시킬 수 있고,
     ~/.gitconfig 나 셸 rc 가 열려 있으면 그 계정이 명령을 칠 때마다 공격자의 코드가 함께 돈다.
  2. 시크릿 과다 노출 — 개인키·토큰·자격증명이 소유자 외에게 읽히는 경우.

SUID/SGID 는 PersistenceMonitor 가 따로 본다.
"""
import glob
import os
import pwd
import re
import stat

# 홈 아래에서 쓰기 권한을 확인할 대상. 여기가 쓰기 가능하면 세션 탈취로 이어진다.
HOME_SENSITIVE = (
    ".config", ".ssh", ".gnupg", ".local/bin", ".docker", ".aws", ".kube", ".claude",
    ".bashrc", ".bash_profile", ".bash_login", ".profile", ".zshrc", ".zshenv",
    ".gitconfig", ".npmrc", ".pypirc", ".netrc", ".selected_editor",
)

# 소유자 외 읽기를 허용하면 안 되는 파일 (홈 기준 상대 경로, glob 허용)
HOME_SECRETS = (
    ".ssh/id_*", ".ssh/*.pem", ".ssh/config",
    ".git-credentials", ".netrc", ".npmrc", ".pypirc",
    ".aws/credentials", ".docker/config.json", ".kube/config",
    ".claude/.credentials.json", ".config/gh/hosts.yml", ".config/ngrok/ngrok.yml",
)
_PUBLIC_KEY_RE = re.compile(r"\.pub$")

# 셸 초기화 파일은 실행 권한을 남겨둬야 하는 경우가 있어 644 를 목표로 한다
_RC_FILES = (".bashrc", ".profile", ".zshrc", ".bash_profile", ".bash_login", ".zshenv", ".gitconfig", ".selected_editor")

# 세션 탈취에 쓰이는 자리. 권한이 열려 있을 때 '이미 심어졌는지' 확인한다.
_HIJACK_KEYS = ("hooksPath", "credential.helper", "sshCommand", "pager", "core.editor")

ETC_MAX_DEPTH = 3
MAX_ENTRIES = 20000  # 폭주 방지


def mode_of(path: str) -> int | None:
    """심볼릭 링크는 따라가지 않는다 (링크 자체의 777 은 의미가 없다)."""
    try:
        st = os.lstat(path)
    except OSError:
        return None
    if stat.S_ISLNK(st.st_mode):
        return None
    return stat.S_IMODE(st.st_mode)


def _owner(path: str) -> str:
    try:
        return pwd.getpwuid(os.lstat(path).st_uid).pw_name
    except (OSError, KeyError):
        return "?"


def narrow(old: int, target: int) -> int:
    """권한을 좁히기만 한다. old & target 은 항상 old 의 부분집합이므로 절대 넓어지지 않는다."""
    return old & target


def hijack_evidence(path: str) -> str:
    """권한이 열린 자리에 이미 무언가 심어졌는지 확인해 근거 문자열로 돌려준다."""
    try:
        if os.path.isdir(path) and os.path.basename(path) == ".config":
            entries = sorted(os.listdir(os.path.join(path, "autostart")))
            if entries:
                return "autostart 등록 항목: " + ", ".join(entries[:10])
            return "autostart 비어 있음 (아직 심어진 것 없음)"
        if os.path.basename(path) == ".gitconfig" and os.path.isfile(path):
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
            hits = [k for k in _HIJACK_KEYS if k in text]
            return ("gitconfig 에 설정된 항목: " + ", ".join(hits)) if hits else "gitconfig 에 훅/헬퍼 설정 없음"
    except OSError:
        return ""
    return ""


def check_writable(path: str) -> dict | None:
    """다른 계정이 쓸 수 있는가. 디렉터리는 sticky bit 가 있으면 (예: /tmp) 정상으로 본다."""
    mode = mode_of(path)
    if mode is None:
        return None
    is_dir = os.path.isdir(path)
    group_w, other_w = bool(mode & stat.S_IWGRP), bool(mode & stat.S_IWOTH)
    if not other_w and not group_w:
        return None
    if is_dir and other_w and (mode & stat.S_ISVTX):
        return None  # sticky: 남의 파일을 지울 수 없다
    who = "모든 사용자" if other_w else "같은 그룹"
    kind_ko = "디렉터리" if is_dir else "파일"
    severity = "CRITICAL" if other_w else "WARNING"
    target = 0o700 if is_dir else 0o600
    if not is_dir and os.path.basename(path) in _RC_FILES:
        target = 0o644
    return {
        "path": path, "kind": "world_writable", "mode": oct(mode)[2:].rjust(3, "0"), "target": target,
        "severity": severity, "owner": _owner(path),
        "title_ko": f"{who}가 쓸 수 있는 {kind_ko}: {path}",
        "detail_ko": (f"권한 {oct(mode)[2:]}. 이 자리에 파일을 넣거나 바꾸면 소유자 '{_owner(path)}' 의 세션에서 "
                      f"의도하지 않은 코드가 실행될 수 있습니다."),
        "fix": f"chmod {oct(narrow(mode, target))[2:]} {path}",
    }


def check_secret(path: str) -> dict | None:
    """소유자 외에게 읽히는 시크릿."""
    if _PUBLIC_KEY_RE.search(path):
        return None
    mode = mode_of(path)
    if mode is None or not os.path.isfile(path):
        return None
    if not (mode & 0o077):
        return None
    private_key = "/.ssh/id_" in path or path.endswith(".pem")
    return {
        "path": path, "kind": "secret_exposed", "mode": oct(mode)[2:].rjust(3, "0"), "target": 0o600,
        "severity": "CRITICAL" if private_key else "WARNING", "owner": _owner(path),
        "title_ko": f"소유자 외에게 읽히는 {'개인키' if private_key else '자격증명 파일'}: {path}",
        "detail_ko": f"권한 {oct(mode)[2:]}. 같은 호스트의 다른 계정이 내용을 읽을 수 있습니다.",
        "fix": f"chmod 600 {path}",
    }


def scan_home(home: str) -> list[dict]:
    findings = []
    if not os.path.isdir(home):
        return findings
    f = check_writable(home)
    if f:
        f["target"] = 0o750
        f["fix"] = f"chmod {oct(narrow(int(f['mode'], 8), 0o750))[2:]} {home}"
        findings.append(f)
    for rel in HOME_SENSITIVE:
        f = check_writable(os.path.join(home, rel))
        if f:
            findings.append(f)
    for pattern in HOME_SECRETS:
        for path in glob.glob(os.path.join(home, pattern)):
            f = check_secret(path)
            if f:
                findings.append(f)
    return findings


def scan_tree(root: str, max_depth: int = ETC_MAX_DEPTH) -> list[dict]:
    """디렉터리 트리에서 world/group-writable 항목을 찾는다. 접근 거부는 조용히 건너뛴다."""
    findings, seen = [], 0
    root = root.rstrip("/")
    base_depth = root.count("/")
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, onerror=lambda e: None, followlinks=False):
        if dirpath.count("/") - base_depth >= max_depth:
            dirnames[:] = []
        for name in list(dirnames) + filenames:
            seen += 1
            if seen > MAX_ENTRIES:
                return findings
            f = check_writable(os.path.join(dirpath, name))
            if f:
                findings.append(f)
    return findings


def human_homes() -> list[str]:
    """사람이 쓰는 계정의 홈 (uid 0 또는 1000~60000)."""
    homes = []
    for p in pwd.getpwall():
        if p.pw_uid == 0 or 1000 <= p.pw_uid < 60000:
            if p.pw_dir and p.pw_dir not in ("/", "/nonexistent") and os.path.isdir(p.pw_dir):
                homes.append(p.pw_dir)
    return sorted(set(homes))


_RANK = {"CRITICAL": 2, "WARNING": 1, "INFO": 0}


def scan(homes: list[str], trees: list[str]) -> list[dict]:
    """홈과 트리를 훑어 경로별로 가장 심각한 findings 하나씩 돌려준다."""
    findings: list[dict] = []
    for home in homes:
        findings += scan_home(home)
    for tree in trees:
        findings += scan_tree(tree)
    best: dict[str, dict] = {}
    for f in findings:
        cur = best.get(f["path"])
        if cur is None or _RANK[f["severity"]] > _RANK[cur["severity"]]:
            best[f["path"]] = f
    return sorted(best.values(), key=lambda x: (-_RANK[x["severity"]], x["path"]))
