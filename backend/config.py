"""
중앙 설정 모듈.

모든 값은 환경 변수(또는 backend/.env)로 재정의할 수 있다.
설정을 한 곳에 두어 배포(systemd)와 개발(start.sh)이 같은 코드를 쓰게 한다.
"""
import os
import secrets
import stat
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default=None):
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, default))
    except (TypeError, ValueError):
        return default


# --- 서버 바인딩 ---
HOST = _env("SECDASH_HOST", "127.0.0.1")
PORT = _env_int("SECDASH_PORT", 8000)

# --- 데이터 소스 ---
AUTH_LOG_PATH = _env("SECDASH_AUTH_LOG", "/var/log/auth.log")
DPKG_LOG_PATH = _env("SECDASH_DPKG_LOG", "/var/log/dpkg.log")
DB_URL = _env("SECDASH_DB_URL", f"sqlite:///{BASE_DIR / 'security_monitor.db'}")

# --- fail2ban 연동 ---
FAIL2BAN_JAIL = _env("SECDASH_FAIL2BAN_JAIL", "sshd")            # 차단 요청을 보낼 jail
FAIL2BAN_JAILS = [j.strip() for j in _env("SECDASH_FAIL2BAN_JAILS", "sshd,recidive").split(",") if j.strip()]  # 동기화 대상
FAIL2BAN_CLIENT = _env("SECDASH_FAIL2BAN_CLIENT", "/usr/bin/fail2ban-client")
# root가 아니면 sudo -n 으로 fail2ban-client 를 호출한다 (deploy/sudoers-secdash 참고)
FAIL2BAN_USE_SUDO = _env_bool("SECDASH_FAIL2BAN_USE_SUDO", os.geteuid() != 0)
# 관리자 IP·대역(공백·쉼표 구분). 대시보드는 이 주소를 차단하지 않고, apply-host-config.sh 가
# fail2ban ignoreip 에도 넣는다. 원격 서버에서 비워 두면 관리자가 스스로 차단될 수 있다.
F2B_IGNOREIP = _env("SECDASH_F2B_IGNOREIP", "")
# SSH 포트. 로그인해 있는 관리자 세션을 알아보는 데 쓴다(admin_guard).
SSH_PORTS = {int(x) for x in _env("SECDASH_SSH_PORTS", "22").replace(",", " ").split() if x.isdigit()}

# --- 잡음 억제 ---
# 이 프로세스가 실행 중인 계정(대시보드 자신)의 sudo/root 세션은 이벤트로 남기지 않는다
import pwd as _pwd
try:
    SELF_USER = _pwd.getpwuid(os.geteuid()).pw_name
except KeyError:
    SELF_USER = ""
# 외부 연결 이벤트에서 무시할 프로세스 이름 (쉼표 구분, 예: firefox,chrome)
NETWORK_IGNORE_PROCESSES = {p.strip().lower() for p in _env("SECDASH_NETWORK_IGNORE_PROCESSES", "").split(",") if p.strip()}
# 임시 디렉터리 실행 판정에서 제외할 실행 파일 경로 패턴 (쉼표 구분, fnmatch 글롭).
# AppImage 처럼 읽기 전용으로 자기를 마운트하는 경로는 코드가 이미 걸러내므로 보통 비워 둔다.
# 쓰기 가능한 경로를 여기에 넣으면 그만큼 눈을 감는 것이다.
TMP_EXEC_ALLOW = [p.strip() for p in _env("SECDASH_TMP_EXEC_ALLOW", "").split(",") if p.strip()]
# 같은 실행 파일의 execve 가 이 시간(초) 안에 반복되면 알림 횟수를 올리지 않는다.
# auditd 는 대화형 세션의 execve 를 전부 흘려보내므로, 이 창이 없으면 한 알림의
# '발생 횟수' 가 실행 횟수만큼(수십만까지) 올라간다.
EXEC_DEDUP_SEC = _env_int("SECDASH_EXEC_DEDUP_SEC", 60)

# --- 노출 면 판정 ---
# 외부에 열려 있어도 정상인 포트 ("22/tcp,443/tcp" 형식). 여기 없는 포트가 외부에서 도달 가능하면 알림.
EXPECTED_EXPOSED_PORTS = _env("SECDASH_EXPECTED_EXPOSED", "22/tcp")
# 인터넷에 '나가면서' 임시 포트를 여는 프로그램. 이 포트는 남이 들어오는 문이 아니다.
# 임시 포트 범위 안이고 이 목록에 있는 프로그램이 열었을 때만 '나가는 통로'로 본다
# (범위만 보고 거르면 Tailscale 41641 같은 진짜 서비스를 놓친다).
CLIENT_PROCESSES = {p.strip().lower() for p in _env(
    "SECDASH_CLIENT_PROCESSES",
    "firefox,chrome,chromium,chromium-browser,brave,brave-browser,opera,vivaldi,msedge,microsoft-edge,"
    "thunderbird,slack,discord,telegram-desktop,signal-desktop,element-desktop,zoom,teams,skype,"
    "electron,code,cursor,obsidian,spotify,steam,whatsapp,webexmta,jitsi",
).split(",") if p.strip()}

# 파일 권한 감시에서 추가로 훑을 디렉터리 (쉼표 구분). 기본은 /etc.
PERMISSION_TREES = [p.strip() for p in _env("SECDASH_PERMISSION_TREES", "/etc").split(",") if p.strip()]
# 권한 일괄 조치 스크립트. 경로를 인자로 받지 않고 스스로 재스캔하므로 API 가 임의 경로를 건드릴 수 없다.
# 배포본은 /usr/local/sbin 에 root 소유로 설치된다 (서비스 계정이 쓸 수 있는 트리에 두면 안 된다).
# 개발 트리에서 직접 쓰려면 SECDASH_PERMISSION_FIX_SCRIPT 로 가리키되, 그 경우 root 권한이 필요하다.
_FIX_SCRIPT_DEFAULT = "/usr/local/sbin/secdash-fix-permissions"
PERMISSION_FIX_SCRIPT = _env("SECDASH_PERMISSION_FIX_SCRIPT", _FIX_SCRIPT_DEFAULT)
PERMISSION_FIX_USE_SUDO = _env_bool("SECDASH_PERMISSION_FIX_USE_SUDO", os.geteuid() != 0)

# --- 물리 접근 (이 기계 앞에 사람이 앉을 수 있는가) ---
# 홈의 'USB 저장장치' 줄은 누가 이 기계 앞에 와서 USB 를 꽂는 상황을 위한 조작이다.
# 아무도 손댈 수 없는 원격 서버에서는 그 줄이 잡음이라 빼는 편이 낫다.
#   auto   = logind seat 을 1차 신호로, 섀시·가상화를 보조로 판정한다. 못 읽으면 그린다.
#   always = 자동 판정과 무관하게 늘 그린다.
#   never  = 아무도 직접 손댈 수 없는 기계다 — 그리지 않는다.
# 판정 결과와 그렇게 정한 이유는 /api/host 의 physical_access 에 실린다 (integrations/presence.py).
PHYSICAL_ACCESS = (_env("SECDASH_PHYSICAL_ACCESS", "auto") or "auto").strip().lower()

# --- 브루트포스 판정 ---
BRUTE_FORCE_WINDOW_MIN = _env_int("SECDASH_BRUTE_WINDOW_MIN", 30)
BRUTE_FORCE_THRESHOLD = _env_int("SECDASH_BRUTE_THRESHOLD", 5)

# --- 방화벽 로그(ufw) 포트 스캔 판정 ---
# ufw 가 막은 패킷 기록. secdash 계정은 adm 그룹이라 추가 권한 없이 읽는다.
UFW_LOG_PATH = _env("SECDASH_UFW_LOG", "/var/log/ufw.log")
# 같은 IP 가 이 시간(초) 안에 서로 다른 포트 N개를 두드리면 스캔으로 본다 (스캔 자체는 이벤트만).
SCAN_WINDOW_SEC = _env_int("SECDASH_SCAN_WINDOW_SEC", 60)
SCAN_PORTS = _env_int("SECDASH_SCAN_PORTS", 10)
# 스캔한 IP 가 이 시간 안에 SSH 로그인 시도·실제 연결을 하면 경고 알림.
SCAN_FOLLOWUP_HOURS = _env_int("SECDASH_SCAN_FOLLOWUP_HOURS", 24)

# --- 외부 연동 (호스트 로그는 절대 외부로 보내지 않는다) ---
SLACK_WEBHOOK_URL = _env("SLACK_WEBHOOK_URL")
ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
# 위협 인텔(공개 뉴스)만 외부 번역/평가 허용
INTEL_TRANSLATE = _env_bool("SECDASH_INTEL_TRANSLATE", True)
INTEL_FEEDS = [
    f.strip() for f in _env(
        "SECDASH_INTEL_FEEDS",
        "https://feeds.feedburner.com/TheHackersNews",
    ).split(",") if f.strip()
]
USN_FEED_URL = _env("SECDASH_USN_FEED", "https://ubuntu.com/security/notices/rss.xml")
USN_MATCH = _env_bool("SECDASH_USN_MATCH", True)

# --- 보존 정책 ---
EVENT_RETENTION_DAYS = _env_int("SECDASH_EVENT_RETENTION_DAYS", 30)
ALERT_RETENTION_DAYS = _env_int("SECDASH_ALERT_RETENTION_DAYS", 90)
# 확인(ack)만 된 채 이 기간 동안 다시 관찰되지 않은 알림은 자동 해결로 정리한다 (0 이면 끄기).
# 확인은 "봤다"는 표시일 뿐이라 스스로 사라지지 않는다. 그대로 두면 ACKED 만 수백 건 쌓이고,
# 쌓인 목록은 결국 아무도 보지 않는다. 침입 신호 계열은 시간이 지났다는 이유로 닫지 않는다
# (대상 규칙은 alerts.AGEABLE_ACKED_RULE_PREFIXES).
ACKED_AGE_DAYS = _env_int("SECDASH_ACKED_AGE_DAYS", 30)

# --- 식별 ---
import socket as _socket
HOSTNAME = _env("SECDASH_HOSTNAME", _socket.gethostname())
def _read_version() -> str:
    for p in (BASE_DIR.parent / "VERSION", BASE_DIR / "VERSION"):
        try:
            return p.read_text(encoding="utf-8").strip()
        except OSError:
            continue
    return "dev"
VERSION = _read_version()

# 이 서버의 역할 메모 (강화 작업 목록을 Claude 등에 붙여넣을 때 맥락으로 포함됨)
HOST_ROLE = _env("SECDASH_HOST_ROLE", "")

# --- 알림 속도 제한 ---
NOTIFY_MAX_PER_MINUTE = _env_int("SECDASH_NOTIFY_MAX_PER_MINUTE", 10)

# --- 프론트엔드 정적 파일 (빌드 결과가 있으면 백엔드가 직접 서빙) ---
FRONTEND_DIST = Path(_env("SECDASH_FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist"))

# --- 문서 (docs/architecture.html 등) ---
DOCS_DIR = Path(_env("SECDASH_DOCS_DIR", BASE_DIR.parent / "docs"))

# --- API 토큰 ---
API_TOKEN_FILE = Path(_env("SECDASH_API_TOKEN_FILE", BASE_DIR / ".api_token"))


def load_api_token() -> str:
    """환경 변수 → 토큰 파일 → 신규 생성 순으로 API 토큰을 확보한다."""
    token = _env("SECDASH_API_TOKEN")
    if token:
        return token.strip()
    try:
        if API_TOKEN_FILE.exists():
            token = API_TOKEN_FILE.read_text(encoding="utf-8").strip()
            if token:
                return token
    except OSError:
        pass
    token = secrets.token_urlsafe(32)
    try:
        API_TOKEN_FILE.write_text(token + "\n", encoding="utf-8")
        os.chmod(API_TOKEN_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return token


API_TOKEN = load_api_token()
