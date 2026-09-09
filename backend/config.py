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

# --- 잡음 억제 ---
# 이 프로세스가 실행 중인 계정(대시보드 자신)의 sudo/root 세션은 이벤트로 남기지 않는다
import pwd as _pwd
try:
    SELF_USER = _pwd.getpwuid(os.geteuid()).pw_name
except KeyError:
    SELF_USER = ""
# 외부 연결 이벤트에서 무시할 프로세스 이름 (쉼표 구분, 예: firefox,chrome)
NETWORK_IGNORE_PROCESSES = {p.strip().lower() for p in _env("SECDASH_NETWORK_IGNORE_PROCESSES", "").split(",") if p.strip()}

# --- 노출 면 판정 ---
# 외부에 열려 있어도 정상인 포트 ("22/tcp,443/tcp" 형식). 여기 없는 포트가 외부에서 도달 가능하면 알림.
EXPECTED_EXPOSED_PORTS = _env("SECDASH_EXPECTED_EXPOSED", "22/tcp")
# 파일 권한 감시에서 추가로 훑을 디렉터리 (쉼표 구분). 기본은 /etc.
PERMISSION_TREES = [p.strip() for p in _env("SECDASH_PERMISSION_TREES", "/etc").split(",") if p.strip()]

# --- 브루트포스 판정 ---
BRUTE_FORCE_WINDOW_MIN = _env_int("SECDASH_BRUTE_WINDOW_MIN", 30)
BRUTE_FORCE_THRESHOLD = _env_int("SECDASH_BRUTE_THRESHOLD", 5)

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
