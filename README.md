# Security Dashboard

중요 서버용 보안 관제 대시보드. **검증된 호스트 도구 위에서 동작하는 뷰/트리아지 계층**으로 설계되어 있다.
탐지를 직접 재발명하기보다 fail2ban, rsyslog(auth.log), dpkg/apt, /proc, Ubuntu USN 을 진실 원천으로 삼고,
그 위에서 상관 분석 → 알림(Alert) → 한국어 조치 안내 → 확인/해결 워크플로를 제공한다.

```
 auth.log ──┐                                   ┌─ 알림 (OPEN → ACKED → RESOLVED)
 fail2ban ──┤   모니터(사실 기록)   상관 규칙     │   · 제목/요약/지금 할 일(한국어)
 dpkg/apt ──┼─▶ Event(원시) ───▶ Alert 엔진 ───▶┤   · 근거(diff, 로그 줄)
 /proc ─────┤                     (중복 억제)    │   · Slack (속도 제한)
 USN JSON ──┘                                   └─ DEFCON = 미확인 알림에서만 계산
```

## 원칙

1. **조용히 실패하지 않는다.** 로그를 못 읽거나 fail2ban 을 제어할 수 없으면 모니터 상태가 `제한/중단` 으로 바뀌고 해결 명령이 표시된다. 테스트 파일로 대체하지 않는다.
2. **한 일만 말한다.** 실제 차단은 fail2ban 이 한다. 연동이 안 되면 "차단됨" 이 아니라 "차단 권고" 와 실행할 명령을 보여준다.
3. **호스트 로그는 외부로 나가지 않는다.** 한국어 문장은 구조화 필드 기반 템플릿으로 만든다. 외부 번역/AI 평가는 공개 뉴스 제목에만 쓴다.
4. **원시 이벤트와 알림을 분리한다.** 실패 로그 한 줄은 INFO 이벤트, "30분 내 5회 실패" 가 경고 알림, "실패 후 성공" 이 긴급 알림이다. 알림을 확인(ack)하면 DEFCON 에서 빠진다.
5. **계획된 변경은 알림이 아니다.** 패키지 설치가 만든 cron/SUID/설정 파일, `systemctl mask` 링크, snap 갱신은 소유 패키지와 최근 패키지 작업을 대조해 정보 이벤트로만 남긴다. 운영자는 점검 모드를 켜서 작업 중 알림을 자동 확인 처리할 수 있다. sudoers, sshd_config, authorized_keys, ld.so.preload, 그리고 모든 침입 신호는 예외 없이 알린다.
6. **판단에 필요한 근거를 함께 준다.** 프로세스명·실행 파일·사용자·부모, 파일 diff 와 추가된 키/계정, 취약한 패키지와 수정 버전.

## 탐지 항목

| 모니터 | 소스 | 알림 규칙 |
|---|---|---|
| AuthLogWatcher | auth.log | 브루트포스, 실패 후 성공(긴급), 새 공인 IP 로그인, root 직접 로그인, sudo 실패, 계정/권한 그룹 변경 |
| Fail2banSync | fail2ban-client | 실제 차단 목록 동기화, 수동 차단/해제 |
| NetworkWatcher | /proc/net | 외부 인터페이스 새 리스너(프로세스 포함), 새 외부 연결, 포트 스캔(저신뢰) |
| ProcessAudit | /proc | 셸 stdin/stdout 이 소켓(리버스 셸, 긴급), /tmp·/dev/shm 실행, 삭제된 실행 파일, 공격/진단 도구 실행 |
| IntegrityMonitor | sha256 + DB 기준선 | passwd/group/shadow/sudoers(.d)/sshd_config(.d)/authorized_keys/ld.so.preload — diff 첨부, 서비스 중지 중 변경도 탐지 |
| PersistenceMonitor | cron, systemd, SUID | 새/변경된 cron·유닛(curl\|sh, /dev/tcp 패턴이면 긴급), 새 SUID/SGID |
| UpdateMonitor | dpkg.log, apt | 패키지 제거(보안 패키지면 긴급), 미적용 보안 업데이트 |
| ResourceMonitor | psutil | CPU/메모리/디스크/프로세스 급증 (해소 시 자동 해결) |
| IntelMonitor | 뉴스 RSS, Ubuntu USN | USN 영향 패키지 ↔ 설치 버전 대조 → 이 서버에 실제 영향 있는 공지만 알림 |
| AuditMonitor | auditd (`deploy/audit-secdash.rules`) | 대화형 세션의 모든 execve(도구·임시 디렉터리 실행 즉시 탐지), 핵심 파일 쓰기의 주체, ld.so.preload 쓰기(긴급), 커널 모듈 |
| LynisMonitor | Lynis 크론 결과 | 새 경고 알림, 사라지면 자동 해결, 강화 지수 하락 알림, 제안은 강화 작업 목록으로 표시 |

## 실행

개발:

```bash
./start.sh          # backend 127.0.0.1:8000 + vite 127.0.0.1:5173, 토큰 자동 주입
```

운영 (전용 계정 + capability + sudoers + systemd):

```bash
sudo deploy/install.sh
```

자세한 권한 모델과 접근 방법은 [deploy/README.md](deploy/README.md) 를 보라.

## API

모든 `/api` 요청은 `X-API-Token` 헤더가 필요하다 (`backend/.api_token` 또는 `SECDASH_API_TOKEN`).

| 경로 | 설명 |
|---|---|
| `GET /api/stats` | DEFCON(미확인 알림 기반), 24h 집계, 리소스, 탐지 공백 |
| `GET /api/alerts?status=active\|all` · `POST /api/alerts/{id}/ack\|resolve` | 알림 조회/확인/해결 |
| `GET /api/events` | 원시 이벤트 (`include_simulation=false` 로 테스트 제외) |
| `GET /api/blocked` · `POST /api/blocked` · `POST /api/blocked/{ip}/unblock` | fail2ban 차단 목록/수동 차단/해제 |
| `GET /api/monitors` | 모니터 health(ok/degraded/down), 사유, 해결 힌트 |
| `GET /api/host` | 호스트, 실행 권한 점검, 미적용 업데이트 |
| `GET /api/intel` | 뉴스 + USN (이 서버 영향 여부) |
| `GET /api/hardening` | Lynis 강화 지수, 경고, 제안 |
| `POST /api/alerts/ack-all` | 미확인 알림 일괄 확인 (`ids` 또는 `rule`) |
| `GET/POST/DELETE /api/maintenance` | 점검 모드: 계획 작업 중 설정·패키지·영속화 알림 자동 확인 (침입 신호는 제외) |
| `GET /api/summary/korean` | 현재 상황 한국어 요약 |

## 테스트

```bash
cd backend && venv/bin/python -m pytest -q tests     # 파서·상관 규칙·알림 엔진·무결성·fail2ban 어댑터·API
python3 simulate_attack.py                            # 탐지 파이프라인 점검 (TEST DATA 로 표시, DEFCON/Slack/fail2ban 영향 없음)
./clear_simulation.sh                                 # 시뮬레이션 흔적 정리
```

## 설정

`backend/.env` 또는 환경 변수. 전체 목록은 `backend/config.py`, 운영 예시는 `deploy/secdash.env.example`.

| 변수 | 기본값 | 설명 |
|---|---|---|
| `SECDASH_AUTH_LOG` | `/var/log/auth.log` | 인증 로그 경로 (시뮬레이션 시 테스트 파일) |
| `SECDASH_FAIL2BAN_JAIL` | `sshd` | 동기화/차단에 쓰는 jail |
| `SECDASH_BRUTE_THRESHOLD` / `_WINDOW_MIN` | 5 / 30 | 브루트포스 판정 |
| `SECDASH_NETWORK_IGNORE_PROCESSES` | – | 외부 연결 이벤트에서 제외할 프로세스 (예: `firefox,chrome`) |
| `SLACK_WEBHOOK_URL` | – | 알림 발송 (분당 10건 제한, 초과분 집계) |
| `ANTHROPIC_API_KEY`, `SECDASH_INTEL_TRANSLATE` | –, 1 | 뉴스 제목 번역/긴급도 (호스트 로그 미전송) |
| `SECDASH_USN_MATCH` | 1 | USN ↔ 설치 패키지 대조 |
| `SECDASH_EVENT_RETENTION_DAYS` / `_ALERT_RETENTION_DAYS` | 30 / 90 | 보존 기간 |

## 한계 (알고 쓰기)

- 포트 스캔 탐지는 커널 소켓 테이블 기반 휴리스틱이라 SYN 스캔 대부분을 놓친다. 필요하면 방화벽 로그나 IDS 를 붙여라.
- 파일 무결성은 자체 해시다. 규제 요건이 있으면 AIDE 를 병행하고 이 대시보드는 표시 계층으로 써라.
- auditd 가 없으면 프로세스 실행 이력(execve)은 30초 샘플링으로만 본다. `deploy/install.sh` 는 auditd 와 최소 규칙을 설치해 이 공백을 메운다.
