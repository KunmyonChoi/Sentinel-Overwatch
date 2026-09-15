# 내 컴퓨터 지킴이 — 데스크톱 앱 (트레이 상주)

브라우저 대신 자기 창을 가진 앱으로 대시보드를 연다. 트레이(상단 바)에 항상 떠 있고,
아이콘 모양으로 지금 상태를 보여준다. 화면은 `frontend/` 를 그대로 담는다 — 따로 만들지 않는다.

| 아이콘 | 상태 |
|---|---|
| 초록 체크 | 이상 없음 |
| 노란 느낌표 | 살펴보세요 |
| 빨간 느낌표 | 지금 확인하세요 |
| 회색 물음표 | 알 수 없음 (지킴이와 연결 못 함 · 토큰 없음 · 화면이 60초 넘게 소식 없음) |

**지금 확인하세요(긴급)** 알림이 새로 생기면 OS 알림으로 한 번 띄운다. 연습용(시뮬레이션) 알림은 띄우지 않고,
이미 알린 알림은 다시 띄우지 않는다(알림 id 를 기억한다). 알림을 띄우지 못하면 기억하지 않고 다음 주기에 다시 시도한다.

상태 판정은 쉬운 화면과 **같은 함수**(`frontend/src/plain/tasks.js` 의 `buildTasks`·`statusOf`)로
`frontend/src/desktop.js` 가 15초마다 하고, 결과를 앱(`set_tray_status`)에 넘긴다.
두 곳에서 따로 판정하면 트레이와 화면이 다른 말을 하게 되기 때문이다.

## 동작

- 트레이 메뉴: `상태: …` · 창 열기 · 로그인할 때 자동으로 켜기 · 종료
- 창을 닫으면 앱은 끝나지 않고 트레이에 남는다. 끝내려면 메뉴의 **종료**.
- 두 번 실행하면 새로 뜨지 않고 떠 있는 창을 앞으로 가져온다.
- **Linux 제약**: AppIndicator 트레이는 아이콘 클릭 이벤트와 툴팁을 주지 않는다. 그래서 창은
  메뉴로 열고, 상태는 메뉴 첫 줄 글자로도 적는다. 순수 GNOME(Ubuntu 가 아닌 배포판)에서는
  AppIndicator 확장을 따로 켜야 트레이가 보인다.

## 준비 (Ubuntu 24.04)

```bash
sudo apt install libwebkit2gtk-4.1-dev build-essential curl wget file \
  libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev
rustup update stable          # Rust 최신 stable
cd desktop && npm install     # Tauri CLI
```

conda(miniforge)가 PATH 앞에 있으면 `cc` 가 conda 의 gcc 가 되어 링크가
`undefined symbol: __libc_csu_init` 로 실패한다. `src-tauri/.cargo/config.toml` 이 Linux x86_64 에서
시스템 gcc 를 쓰도록 고정해 두었다.

## 실행

지킴이 백엔드가 `127.0.0.1:8000` 에 떠 있어야 한다(운영 인스턴스 또는 `./start.sh`).
처음 창이 뜨면 API 토큰을 한 번 입력한다. 토큰은 **OS 키링**(Linux 는 GNOME 키링 같은 Secret Service,
macOS Keychain, Windows 자격 증명 관리자)에 저장된다. 예전 원형이 창 안 저장소에 둔 토큰은 키링에 옮긴 뒤 지운다.
키링을 쓸 수 없는 환경이면 예전처럼 창 안 저장소를 쓴다.

```bash
cd desktop
npm run build        # 화면 빌드(frontend → desktop/dist) + 앱 빌드(deb, AppImage)
```

화면을 고치면서 보려면 `./start.sh` 로 Vite(5173)를 띄운 뒤 `npx tauri dev`.
운영 인스턴스가 8000 을 쓰고 있으면 개발 인스턴스는 다른 포트로 띄우고
(`SECDASH_PORT=8001 SECDASH_UI_PORT=5174 ./start.sh`),
`npx tauri dev --config '{"build":{"devUrl":"http://127.0.0.1:5174"}}'` 로 붙는다.

## 보안에 관해

- 백엔드는 여전히 `127.0.0.1` 에만 붙고, 모든 API 호출에 `X-API-Token` 이 필요하다.
  CORS 허용 목록에 앱 출처(`tauri://localhost`, `http://tauri.localhost`)를 더했을 뿐,
  토큰 없이 읽을 수 있게 된 것은 없다(`backend/tests/test_intel_and_api.py` 의 CORS 테스트).
- `build:web` 은 `VITE_API_TOKEN` 을 비워서 빌드한다. `./start.sh` 가 만드는 개발 토큰
  (`frontend/.env.local`)이 배포용 앱에 들어가지 않게 하기 위해서다.
- CSP(`tauri.conf.json` 의 `app.security.csp`): 스크립트는 앱 자신만, 통신은 내부 IPC 와
  `http://127.0.0.1:8000` 만, 스타일·글꼴은 Google Fonts 만 허용한다. 백엔드를 다른 포트로 띄워 붙이려면
  `connect-src` 도 바꿔야 한다(예: `--config '{"app":{"security":{"csp":{"connect-src":"'"'"'self'"'"' ipc: http://ipc.localhost http://127.0.0.1:8001"}}}}'`).
- 토큰은 OS 키링에 있고, 창 안 저장소에는 두지 않는다. 창 안 저장소는 앱 데이터 폴더의 평문 파일이다.

## 아직 안 한 것

- 원격 서버: 앱이 SSH 터널을 직접 여는 기능 (지금은 사용자가 연 터널에 붙는다)
- 서명된 패키지, deb/AppImage 를 실제로 설치해 보기
