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
| 명령 실행·파일 쓰기 주체 | auditd (`rules.d/secdash.rules`) | 도구 실행 즉시 탐지, 무결성 알림에 "누가 썼나" 첨부 |
| 설정 강화 감사 | Lynis (cron 04:15) | 새 경고·지수 하락만 알림, 제안은 작업 목록 |

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

## 호스트 도구 설정

`deploy/apply-host-config.sh` 가 fail2ban 보강(`jail.d/secdash.conf`: ignoreip, bantime.increment, recidive), auditd 규칙, Lynis 크론을 설치한다. install.sh 와 update.sh 가 자동 호출하며, `ignoreip` 에 관리자 대역을 추가한 뒤 다시 실행하면 반영된다.

## Lynis 프로파일 (수용·해결 항목 제외)

`deploy/lynis-custom.prf` 는 이 서버에서 '수용' 또는 '이미 다른 방식으로 해결' 로 결정한 테스트를 `skip-test=` 로 건너뛴다. 강화 작업 목록에는 아직 결정하지 않은 항목만 남는다. 결정을 바꾸면 줄을 지우거나 추가하고 `sudo deploy/apply-host-config.sh` 를 실행한다.

주의: Lynis 는 프로파일에 ASCII 외 문자가 있으면 실행을 중단한다(보안 조치). 파일은 영문 주석만 쓴다. 결정 근거:

| 테스트 | 결정 | 근거 |
|---|---|---|
| FINT-4350, ACCT-9622, ACCT-9626 | 이미 해결 | 무결성 감시·auditd execve·리소스 감시가 담당 |
| HRDN-7222 | 수용 | GPU 개발 서버라 컴파일러 제한 불가 |
| HRDN-7230 | 수용 | 외부 파일 유입 경로 없음. 생기면 ClamAV 정기 스캔 검토 |
| FILE-6310 | 수용 | 별도 파티션은 재설치 필요. 디스크 사용률 알림으로 대체 |
| FIRE-4513, KRNL-6000 잔여 | 수용 | docker 관리 규칙, GPU 도구용 sysctl 은 의도적 결정 |
| PRNT-2307 | 해당 없음 | CUPS 마스크됨 (인쇄 불필요) |
| SSH-7408 잔여 (AllowTcpForwarding, AllowAgentForwarding, MaxSessions, Port) | 수용 | ssh -L 터널과 개발 편의. LogLevel/MaxAuthTries/ClientAlive/TCPKeepAlive/X11 은 적용 |
| TIME-3185 | 이미 해결 | Lynis 3.0.9 가 보는 파일은 최신 systemd 에서 갱신되지 않음. 대시보드가 timedatectl 로 동기화 여부를 직접 감시 |
| TOOL-5002, NAME-4028, DEB-0810 | 해당 없음 | 단독 호스트, 대화형 잡음 |

## 강화 스크립트 (Lynis 후속)

```bash
sudo deploy/harden.sh          # dry-run: 점검 결과와 변경 예정 목록
sudo deploy/harden.sh --apply  # 적용 (umask 027, sysctl, 코어 덤프, 모듈 차단, 배너, 옛 커널/잔재 정리 등)
```

docker 와 충돌하는 rp_filter/ip_forward, 개발을 막는 컴파일러 제한, 원격 재부팅을 막을 수 있는 GRUB 비밀번호는 건드리지 않는다.

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
