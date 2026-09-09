# Security Dashboard (Sentinel Overwatch)

중요 서버용 보안 관제 대시보드. **검증된 호스트 도구 위에서 동작하는 뷰/트리아지 계층**으로 설계되어 있다.
탐지를 직접 재발명하기보다 fail2ban, rsyslog(auth.log), auditd, dpkg/apt, /proc, Lynis, Ubuntu USN 을 진실 원천으로 삼고,
그 위에서 상관 분석 → 알림(Alert) → 한국어 조치 안내 → 확인/해결 워크플로를 제공한다.

```
 auth.log ──┐                                   ┌─ 알림 (OPEN → ACKED → RESOLVED)
 auditd ────┤                                   │   · 제목/요약/지금 할 일(한국어)
 fail2ban ──┤   모니터(사실 기록)   상관 규칙     │   · 근거(diff, 로그 줄, 최근 관리자 활동)
 dpkg/apt ──┼─▶ Event(원시) ───▶ Alert 엔진 ───▶┤   · Slack (속도 제한, 호스트명 접두사)
 /proc ─────┤                     (중복 억제)    │   · 점검 모드 중 계획 변경은 자동 확인
 Lynis ─────┤                                   │
 USN JSON ──┘                                   └─ DEFCON = 미확인 알림에서만 계산
```

아키텍처 다이어그램(데이터 흐름, 브루트포스 사건의 경로, 알림 생애주기, 신뢰 경계, 설치·강화 경로): **https://kunmyonchoi.github.io/Sentinel-Overwatch/architecture.html** (원본 [docs/architecture.html](docs/architecture.html), 운영 대시보드에서는 http://127.0.0.1:8000/docs/architecture.html).

## 원칙

1. **조용히 실패하지 않는다.** 로그를 못 읽거나 fail2ban 을 제어할 수 없으면 모니터 상태가 `제한/중단` 으로 바뀌고 해결 명령이 표시된다. 테스트 파일로 대체하지 않는다.
2. **한 일만 말한다.** 실제 차단은 fail2ban 이 한다. 연동이 안 되면 "차단됨" 이 아니라 "차단 권고" 와 실행할 명령을 보여준다.
3. **호스트 로그는 외부로 나가지 않는다.** 한국어 문장은 구조화 필드 기반 템플릿으로 만든다. 외부 번역/AI 평가는 공개 뉴스 제목에만 쓴다.
4. **원시 이벤트와 알림을 분리한다.** 실패 로그 한 줄은 INFO 이벤트, "30분 내 5회 실패" 가 경고 알림, "실패 후 성공" 이 긴급 알림이다. 알림을 확인(ack)하면 DEFCON 에서 빠진다.
5. **계획된 변경은 알림이 아니다.** 패키지 설치가 만든 cron/SUID/설정 파일, `systemctl mask` 링크, snap 갱신은 소유 패키지와 최근 패키지 작업을 대조해 정보 이벤트로만 남긴다. 운영자는 점검 모드를 켜서 작업 중 알림을 자동 확인 처리할 수 있다. sudoers, sshd_config, authorized_keys, ld.so.preload, 그리고 모든 침입 신호는 예외 없이 알린다.
6. **판단에 필요한 근거를 함께 준다.** 프로세스명·실행 파일·사용자·부모, 파일 diff 와 추가된 키/계정, 누가 방금 어떤 sudo 명령을 실행했는지, 취약한 패키지와 수정 버전.

## 화면 구성

| 패널 | 내용 | 운영자가 하는 일 |
|---|---|---|
| 현재 상황 요약 | 미확인 알림, 탐지 공백, 24h 로그인 실패/성공, 차단 IP, 미적용 보안 업데이트, Lynis 지수를 한 문단으로 | 하루 한 번 읽기 |
| 시스템 상태 | DEFCON, 미확인 긴급/경고/대응 중 수, 리소스, 24h 타임라인, 실행 권한 점검, USB 저장장치 차단 상태와 해제/재차단 명령 | 레벨이 SAFE 가 아니면 알림 패널로 |
| 알림 | OPEN/ACKED 알림. 제목·요약·**지금 할 일**·근거(diff, 로그 줄, 최근 관리자 활동). 확인/해결/모두 확인 | 알림마다 확인(ack) 또는 해결(resolve) |
| 모니터 상태 | 11개 모니터의 health(정상/제한/중단), 사유, 해결 명령 복사 | 제한/중단이 보이면 그 명령 실행 |
| 계정 상태 | root 와 사람 계정의 잠김/만료, sudo·docker 그룹, SSH 키, 마지막 로그인·출발지, 180일 미사용 표시, 잠금/되살리기 명령 | 쓰지 않는 계정 잠그기 |
| 강화 작업 목록 | Lynis 강화 지수, 경고, 제안. 제안은 알림이 아니라 백로그 | 주 1회, 항목마다 적용/수용/해결 결정 |
| 위협 인텔 | 보안 뉴스 + Ubuntu USN. 설치 패키지에 실제 영향 있는 공지는 "이 서버 영향" 배지 | 배지가 붙은 것만 처리 |
| IP 차단 | fail2ban 의 실제 차단 목록(sshd, recidive), 수동 차단/해제, 미연동 시 차단 권고 명령 | 관리자 IP 가 차단되면 해제 |
| 라이브 피드 | 원시 이벤트(한국어 + 원문). 시뮬레이션은 TEST DATA 표시 | 알림의 근거를 찾을 때 |
| 점검 모드 (헤더) | 시간과 메모를 정하면 그동안의 설정·패키지·영속화 알림은 자동 확인, 침입 신호는 그대로 | 계획 작업 전에 켜기 |

## 탐지 항목

| 모니터 | 소스 | 알림 규칙 |
|---|---|---|
| AuthLogWatcher | auth.log | 브루트포스, 실패 후 성공(긴급), 새 공인 IP 로그인, root 직접 로그인, sudo 실패, 계정/권한 그룹 변경 |
| AuditMonitor | auditd (`deploy/audit-secdash.rules`) | 대화형 세션의 모든 execve(도구·임시 디렉터리 실행 즉시 탐지), 핵심 파일 쓰기의 주체, ld.so.preload 쓰기(긴급), 커널 모듈 로드 |
| Fail2banSync | `fail2ban-client banned` | sshd·recidive jail 차단 목록 동기화, 수동 차단/해제, jail 비활성 시 제한 표시 |
| NetworkWatcher | /proc/net | 외부 인터페이스 새 리스너(프로세스 포함), 새 외부 연결, 포트 스캔(저신뢰) |
| ProcessAudit | /proc (30초 샘플링, auditd 폴백) | 셸 stdin/stdout 이 소켓(리버스 셸, 긴급), /tmp·/dev/shm 실행, 삭제된 실행 파일, 공격/진단 도구 실행 |
| IntegrityMonitor | sha256 + DB 기준선 | passwd/group/shadow/sudoers(.d)/sshd_config(.d)/authorized_keys/ld.so.preload/modprobe.d/sysctl.d — diff 와 최근 관리자 활동 첨부, 서비스 중지 중 변경도 탐지 |
| PersistenceMonitor | cron, systemd, SUID | 새/변경된 cron·유닛(curl\|sh, /dev/tcp 패턴이면 긴급), 새 SUID/SGID. 패키지 소유·mask 링크·snap 유닛은 정보만 |
| UpdateMonitor | dpkg.log, apt | 패키지 제거(보안 패키지면 긴급, 누가 실행했는지 첨부), 미적용 보안 업데이트 |
| ResourceMonitor | psutil, timedatectl | CPU/메모리/디스크/프로세스 급증, NTP 동기화 끊김 (해소 시 자동 해결) |
| IntelMonitor | 뉴스 RSS, Ubuntu USN | USN 영향 패키지 ↔ 설치 버전 대조 → 이 서버에 실제 영향 있는 공지만 알림 |
| LynisMonitor | Lynis 크론 결과 | 새 경고 알림, 사라지면 자동 해결, 강화 지수 하락 알림, 제안은 강화 작업 목록으로 표시 |

## 운영 리듬

- **매일**: 요약 문단과 DEFCON 만 본다. 알림이 있으면 "지금 할 일" 대로 처리하고 확인(ack) 또는 해결(resolve).
- **계획 작업 전**: 점검 모드를 켠다(15분~4시간, 메모 필수). 무결성·영속화·패키지·리스너·모듈·Lynis 알림은 자동 확인되고 근거만 남는다.
- **주 1회**: 강화 작업 목록에서 새 항목만 결정한다. "Claude 에 붙여넣기용 복사" 로 호스트 역할·상세·이미 결정한 항목이 담긴 브리프를 복사해 의논하고, 수용/해결로 정한 항목은 `deploy/lynis-custom.prf` 에 `skip-test=` 로, 적용할 항목은 `deploy/harden.sh` 에 넣는다.
- **알림이 늘었다고 느낄 때**: 원인이 대시보드 자신이거나 계획 변경이면 코드나 정책을 고친다. 알림을 일일이 지우는 것은 해결이 아니다.

## 실행

개발:

```bash
./start.sh          # backend 127.0.0.1:8000 + vite 127.0.0.1:5173, 토큰 자동 주입
```

운영 (전용 계정 + capability + sudoers + systemd). 대상 서버에는 python3-venv 와 apt 만 있으면 된다.

```bash
# 빌드 머신에서 한 번
deploy/build-release.sh            # dist-release/secdash-<version>.tar.gz + .sha256  (--wheels: 오프라인용 pip 휠 포함)

# 대상 서버에서
sha256sum -c secdash-1.0.0.tar.gz.sha256 && tar xzf secdash-1.0.0.tar.gz
sudo secdash-1.0.0/deploy/install.sh
```

저장소를 직접 clone 한 경우에도 `sudo deploy/install.sh` 로 설치할 수 있다(npm 필요). 업데이트는 새 압축본을 풀고 `sudo secdash-<version>/deploy/update.sh`.
접속은 SSH 터널(`ssh -L 8000:127.0.0.1:8000 서버`)로 http://127.0.0.1:8000 을 열고 `/opt/secdash/backend/.api_token` 값을 한 번 입력한다.

권한 모델, 호스트 도구 설정(fail2ban·auditd·Lynis), 강화 스크립트(`deploy/harden.sh`), 시뮬레이션 방법은 [deploy/README.md](deploy/README.md) 를 보라.

## API

모든 `/api` 요청은 `X-API-Token` 헤더가 필요하다 (`backend/.api_token` 또는 `SECDASH_API_TOKEN`). 커스텀 헤더라 브라우저 CSRF 로는 호출할 수 없다.

| 경로 | 설명 |
|---|---|
| `GET /api/stats` | DEFCON(미확인 알림 기반), 24h 집계, 리소스, 탐지 공백, 점검 모드 |
| `GET /api/alerts?status=active\|all` · `POST /api/alerts/{id}/ack\|resolve` | 알림 조회/확인/해결 |
| `POST /api/alerts/ack-all` | 미확인 알림 일괄 확인 (`ids` 또는 `rule`, 메모) |
| `GET/POST/DELETE /api/maintenance` | 점검 모드 조회/시작(`minutes`, `note`)/종료 |
| `GET /api/events` | 원시 이벤트 (`include_simulation=false` 로 테스트 제외) |
| `GET /api/blocked` · `POST /api/blocked` · `POST /api/blocked/{ip}/unblock` | fail2ban 차단 목록/수동 차단/해제 |
| `GET /api/monitors` | 모니터 health(ok/degraded/down), 사유, 해결 힌트 |
| `GET /api/host` | 호스트, 버전, 실행 권한 점검, 미적용 업데이트, USB 저장장치 차단 상태 |
| `GET /api/accounts` | root 와 사람 계정의 잠김/만료, 권한 그룹, SSH 키, 마지막 로그인 |
| `GET /api/hardening` · `GET /api/hardening/brief?item=` | Lynis 강화 지수·경고·제안 / 대화형 도구에 붙여넣을 마크다운 브리프 |
| `GET /api/intel` | 뉴스 + USN (이 서버 영향 여부) |
| `GET /api/summary/korean` | 현재 상황 한국어 요약 |

## 테스트

```bash
cd backend && venv/bin/python -m pytest -q tests     # 파서·상관 규칙·알림 엔진·점검 모드·무결성·auditd·Lynis·fail2ban·계정·API
python3 simulate_attack.py                            # 탐지 파이프라인 점검 (TEST DATA 로 표시, DEFCON/Slack/fail2ban 영향 없음)
./clear_simulation.sh                                 # 시뮬레이션 흔적 정리
```

## 설정

`backend/.env` 또는 환경 변수. 운영에서는 `/etc/secdash/secdash.env`(예시: `deploy/secdash.env.example`). 전체 목록은 `backend/config.py`.

| 변수 | 기본값 | 설명 |
|---|---|---|
| `SECDASH_HOST` / `SECDASH_PORT` | 127.0.0.1 / 8000 | 바인드 주소. 외부 노출 대신 SSH 터널 사용 |
| `SECDASH_API_TOKEN` | 자동 생성(`backend/.api_token`) | API 토큰 고정 |
| `SECDASH_HOSTNAME` | 시스템 호스트명 | Slack 알림 제목 접두사, 대시보드 헤더 |
| `SECDASH_HOST_ROLE` | – | 서버 역할 메모. 강화 작업 목록의 "Claude 에 붙여넣기용 복사" 본문에 포함 |
| `SECDASH_AUTH_LOG` / `SECDASH_DPKG_LOG` | /var/log/auth.log, /var/log/dpkg.log | 로그 경로 (시뮬레이션 시 테스트 파일) |
| `SECDASH_FAIL2BAN_JAIL` / `SECDASH_FAIL2BAN_JAILS` | sshd / sshd,recidive | 차단 요청 jail / 동기화 대상 jail |
| `SECDASH_BRUTE_THRESHOLD` / `SECDASH_BRUTE_WINDOW_MIN` | 5 / 30 | 브루트포스 판정 |
| `SECDASH_NETWORK_IGNORE_PROCESSES` | – | 외부 연결 이벤트에서 제외할 프로세스 (예: `firefox,chrome`) |
| `SLACK_WEBHOOK_URL` / `SECDASH_NOTIFY_MAX_PER_MINUTE` | – / 10 | 알림 발송, 분당 제한(초과분 집계) |
| `ANTHROPIC_API_KEY`, `SECDASH_INTEL_TRANSLATE` | –, 1 | 뉴스 제목 번역/긴급도 (호스트 로그 미전송) |
| `SECDASH_INTEL_FEEDS` / `SECDASH_USN_FEED` / `SECDASH_USN_MATCH` | THN RSS / Ubuntu USN / 1 | 인텔 소스, USN ↔ 설치 패키지 대조 |
| `SECDASH_EVENT_RETENTION_DAYS` / `SECDASH_ALERT_RETENTION_DAYS` | 30 / 90 | 보존 기간 (기동 1시간 뒤부터 적용) |

## 한계 (알고 쓰기)

- 포트 스캔 탐지는 커널 소켓 테이블 기반 휴리스틱이라 SYN 스캔 대부분을 놓친다. 필요하면 방화벽 로그나 IDS 를 붙여라.
- 파일 무결성은 자체 해시다. 규제 요건이 있으면 AIDE 를 병행하고 이 대시보드는 표시 계층으로 써라.
- auditd 가 없으면 프로세스 실행 이력(execve)은 30초 샘플링으로만 본다. `deploy/install.sh` 는 auditd 와 최소 규칙을 설치해 이 공백을 메운다.
- 서버 한 대 단위다. 여러 서버를 한 화면에서 보려면 Wazuh 같은 중앙 관리 도구가 필요하며, 그때 이 대시보드는 그 위의 한국어 트리아지 뷰로 쓸 수 있다.

## 라이선스

Apache License 2.0. [LICENSE](LICENSE) 를 보라.
