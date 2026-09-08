# 배포 가이드

이 대시보드는 검증된 호스트 도구 위에서 동작하는 **뷰/트리아지 계층**입니다.

| 기능 | 진실 원천 | 대시보드의 역할 |
|---|---|---|
| IP 차단 | fail2ban (`sshd` jail) | 차단 목록 동기화, 수동 차단/해제 요청, 미연동 시 "차단 권고" 표시 |
| SSH/sudo/계정 이벤트 | rsyslog `/var/log/auth.log` | 구조화, 상관 분석(브루트포스, 실패 후 성공, 새 IP), 한국어 안내 |
| 패키지 변경/보안 업데이트 | dpkg.log, `apt list --upgradable` | 이벤트화, 미적용 보안 업데이트 알림 |
| 파일/영속화 무결성 | 자체 SHA-256 + DB 기준선 | diff 첨부 알림 (AIDE 가 있으면 병행 권장) |
| 프로세스/네트워크 | /proc (psutil) | 리버스 셸·임시 디렉터리 실행·새 리스너 탐지 |
| 취약점 | Ubuntu USN JSON ↔ 설치 패키지 | 이 호스트에 실제 영향 있는 공지만 알림 |

## 설치

```bash
sudo deploy/install.sh
```

스크립트가 하는 일:
1. fail2ban / rsyslog 설치·활성화, sshd jail 활성화
2. 전용 계정 `secdash` 생성 (+ `adm` 그룹: auth.log 읽기)
3. `/opt/secdash` 에 복사, venv 및 프론트엔드 빌드
4. `/etc/secdash/secdash.env` 설정 파일
5. `/etc/sudoers.d/secdash` (fail2ban-client 만 허용) 와 systemd 유닛 설치
6. 서비스 시작, API 토큰 출력

## 업데이트

```bash
sudo deploy/update.sh          # 코드만 반영하고 재시작 (DB·토큰·로그 유지)
sudo deploy/update.sh --deps   # requirements 가 바뀐 경우
```

## 권한 모델

| 필요 권한 | 제공 방법 | 용도 |
|---|---|---|
| auth.log 읽기 | `adm` 그룹 | SSH/sudo 이벤트 |
| /etc/shadow, 다른 홈의 authorized_keys, cron spool | `CAP_DAC_READ_SEARCH` | 무결성 감시 |
| 다른 사용자 프로세스의 exe/fd | `CAP_SYS_PTRACE` | 리버스 셸/임시 실행 탐지 |
| 소켓 → 프로세스 귀속 | `CAP_NET_ADMIN` | 리스너 프로세스 확인 |
| fail2ban 제어 | `sudo -n fail2ban-client` (sudoers) | 차단/해제 |

권한이 없으면 대시보드는 **조용히 넘어가지 않고** 모니터 상태 패널에 `제한/중단` 과 해결 명령을 표시합니다.

## 접근

백엔드는 127.0.0.1:8000 에만 바인드합니다. 원격에서는 SSH 터널을 쓰세요.

```bash
ssh -L 8000:127.0.0.1:8000 user@server
# 브라우저: http://127.0.0.1:8000  → 토큰 입력 (서버의 /opt/secdash/backend/.api_token)
```

모든 `/api` 요청은 `X-API-Token` 헤더가 필요합니다. 커스텀 헤더라 브라우저 CSRF 로는 호출할 수 없습니다.

## 시뮬레이션 (탐지 파이프라인 점검)

운영 서버에서는 실제 로그를 건드리지 않도록 `SECDASH_AUTH_LOG` 를 테스트 파일로 바꿔 별도 인스턴스로 실행하세요.

```bash
cd backend && SECDASH_AUTH_LOG=./test_auth.log SECDASH_PORT=8001 venv/bin/python app.py &
python3 ../simulate_attack.py
```

시뮬레이션 이벤트/알림은 `TEST DATA` 로 표시되며 DEFCON 과 Slack 알림에는 영향을 주지 않습니다.
