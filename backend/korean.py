"""
한국어 텍스트 템플릿.

호스트 로그(계정명, sudo 명령, 내부 IP 등)는 외부 번역 서비스로 보내지 않는다.
모니터가 만든 구조화 필드(details)로 결정적인 한국어 문장을 생성한다.
"""

EVENT_TYPE_KO = {
    "AUTH_FAILURE": "로그인 실패",
    "INVALID_USER": "존재하지 않는 계정",
    "AUTH_SUCCESS": "로그인 성공",
    "SUDO_COMMAND": "sudo 명령",
    "SUDO_FAILURE": "sudo 실패",
    "ROOT_SESSION": "root 세션",
    "ACCOUNT_CHANGE": "계정 변경",
    "IP_BLOCKED": "IP 차단",
    "IP_UNBLOCKED": "IP 차단 해제",
    "IP_BLOCK_RECOMMENDED": "IP 차단 권고",
    "NETWORK_LISTENER": "리스닝 포트",
    "NETWORK_CONN": "외부 연결",
    "PORT_SCAN": "포트 스캔 의심",
    "PORT_EXPOSURE": "포트 노출 상태",
    "PORT_CLOSED": "리스닝 포트 닫힘",
    "FILE_PERMISSION": "파일 권한",
    "PERMISSION_FIXED": "파일 권한 조치",
    "CONTAINER_CONFIG": "컨테이너 설정",
    "PROCESS_TOOL": "보안 도구 실행",
    "PROCESS_INDICATOR": "의심 프로세스",
    "FILE_INTEGRITY": "파일 무결성",
    "PERSISTENCE": "영속화 지점 변경",
    "RESOURCE_ANOMALY": "리소스 이상",
    "SOFTWARE_UPDATE": "소프트웨어 업데이트",
    "PENDING_UPDATES": "미적용 업데이트",
    "THREAT_INTEL": "위협 인텔",
    "LYNIS_AUDIT": "보안 감사 (Lynis)",
    "AUDIT_WRITE": "감시 파일 쓰기 (auditd)",
    "AUDIT_EXEC": "명령 실행 (auditd)",
    "KERNEL_MODULE": "커널 모듈",
    "SYSTEM": "시스템",
    "MONITOR_HEALTH": "모니터 상태",
    # 이전 버전 호환
    "INTRUSION_ATTEMPT": "침입 시도",
    "SUCCESSFUL_LOGIN": "로그인 성공",
    "PRIVILEGE_ESCALATION": "권한 상승",
    "MALWARE_DETECTED": "악성코드 탐지",
    "NETWORK_ANOMALY": "네트워크 이상",
}

SEVERITY_KO = {"CRITICAL": "긴급", "WARNING": "경고", "INFO": "정보"}

DEFCON_KO = {
    "DEFCON 1": "긴급 대응 필요",
    "DEFCON 3": "주의 필요",
    "SAFE": "정상",
}


def event_type_ko(event_type: str) -> str:
    return EVENT_TYPE_KO.get(event_type, event_type)


def _who(d: dict) -> str:
    user = d.get("user")
    ip = d.get("ip")
    if user and ip:
        return f"계정 '{user}' ({ip})"
    if user:
        return f"계정 '{user}'"
    if ip:
        return f"{ip}"
    return "알 수 없는 출처"


def event_ko(event_type: str, d: dict | None = None) -> str:
    """이벤트 유형과 구조화 필드로 한국어 설명을 만든다."""
    d = d or {}
    t = event_type
    if t == "AUTH_FAILURE":
        return f"{_who(d)} 에서 SSH 로그인 실패 ({d.get('method', '비밀번호')})"
    if t == "INVALID_USER":
        return f"{d.get('ip', '알 수 없는 IP')} 에서 존재하지 않는 계정 '{d.get('user', '?')}' 으로 접근 시도"
    if t == "AUTH_SUCCESS":
        key = f", 키 {d['key']}" if d.get("key") else ""
        return f"{_who(d)} SSH 로그인 성공 ({d.get('method', '?')}{key})"
    if t == "SUDO_COMMAND":
        return f"'{d.get('user', '?')}' 이(가) {d.get('target', 'root')} 권한으로 실행: {d.get('command', '?')}"
    if t == "SUDO_FAILURE":
        return f"'{d.get('user', '?')}' 의 sudo 실패: {d.get('reason', '인증 실패')}"
    if t == "ROOT_SESSION":
        return f"root 세션 열림 (시작 주체: {d.get('by', '?')}, 경로: {d.get('via', '?')})"
    if t == "ACCOUNT_CHANGE":
        return f"계정 변경: {d.get('change', '?')}"
    if t == "IP_BLOCKED":
        return f"IP {d.get('ip', '?')} 차단됨 ({d.get('source', '?')}) — 사유: {d.get('reason', '?')}"
    if t == "IP_UNBLOCKED":
        return f"IP {d.get('ip', '?')} 차단 해제 ({d.get('by', '수동')})"
    if t == "IP_BLOCK_RECOMMENDED":
        return f"IP {d.get('ip', '?')} 차단 권고 — fail2ban 을 사용할 수 없어 자동 차단하지 못함"
    if t == "NETWORK_LISTENER":
        proc = d.get("process") or "알 수 없는 프로세스"
        return f"새 리스닝 포트 {d.get('address', '')}:{d.get('port', '?')} ({proc}, 사용자 {d.get('user', '?')})"
    if t == "NETWORK_CONN":
        proc = d.get("process") or "알 수 없는 프로세스"
        return f"{proc} 이(가) 외부 {d.get('ip', '?')}:{d.get('port', '?')} 에 연결"
    if t == "PORT_SCAN":
        return f"{d.get('ip', '?')} 이(가) 서비스 포트 {d.get('port_count', '?')}개에 접촉 (포트 스캔 의심, 신뢰도 낮음)"
    if t in ("PORT_EXPOSURE", "PORT_CLOSED", "CONTAINER_CONFIG"):
        return d.get("message_ko") or ""
    if t == "FILE_PERMISSION":
        return d.get("title_ko") or f"{d.get('path', '?')} 권한 {d.get('mode', '?')}"
    if t == "PERMISSION_FIXED":
        return f"권한 좁힘: {d.get('path', '?')} {d.get('before', '?')} → {d.get('after', '?')}"
    if t == "PROCESS_TOOL":
        return f"보안/해킹 도구 '{d.get('tool', '?')}' 실행 감지 (PID {d.get('pid', '?')}, 사용자 {d.get('user', '?')}, 실행 파일 {d.get('exe', '?')})"
    if t == "PROCESS_INDICATOR":
        return f"의심 프로세스 지표: {d.get('indicator_ko', d.get('indicator', '?'))} (PID {d.get('pid', '?')}, {d.get('name', '?')}, 사용자 {d.get('user', '?')})"
    if t == "FILE_INTEGRITY":
        return f"{d.get('path', '?')} {d.get('change_ko', '변경됨')}"
    if t == "PERSISTENCE":
        return f"{d.get('kind_ko', '영속화 지점')} {d.get('change_ko', '변경됨')}: {d.get('path', '?')}"
    if t == "RESOURCE_ANOMALY":
        return d.get("message_ko") or "리소스 이상"
    if t == "SOFTWARE_UPDATE":
        a = d.get("action")
        pkg = d.get("package", "?")
        if a == "remove" or a == "purge":
            return f"패키지 제거됨: {pkg}"
        if a == "install":
            return f"패키지 설치됨: {pkg} {d.get('version', '')}".strip()
        if a == "upgrade":
            return f"패키지 업그레이드: {pkg} {d.get('old', '')} → {d.get('new', '')}"
        return f"패키지 변경: {pkg}"
    if t == "PENDING_UPDATES":
        return f"미적용 업데이트 {d.get('total', 0)}건 (보안 {d.get('security', 0)}건)"
    if t == "THREAT_INTEL":
        return d.get("title_ko") or ""
    if t == "LYNIS_AUDIT":
        return d.get("message_ko") or "Lynis 감사 완료"
    if t == "AUDIT_WRITE":
        return f"{d.get('user', '?')} 이(가) {d.get('exe', '?')} 로 {', '.join(d.get('paths', [])[:3]) or '감시 파일'} 에 씀" + ("" if d.get("success", True) else " (실패)")
    if t == "AUDIT_EXEC":
        return f"{d.get('user', '?')} 이(가) 실행: {d.get('command', '?')[:120]}"
    if t == "KERNEL_MODULE":
        return f"커널 모듈 {d.get('op', '변경')} (사용자 {d.get('user', '?')}, 명령 {d.get('command', '?')[:80]})"
    if t == "MONITOR_HEALTH":
        return d.get("message_ko") or ""
    return d.get("message_ko") or ""


def defcon_ko(status: str) -> str:
    return DEFCON_KO.get(status, status)
