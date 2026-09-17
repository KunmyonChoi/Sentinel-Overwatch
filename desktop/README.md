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

## 설치와 사용 (Ubuntu 24.04 이상 · amd64)

이 앱은 **화면만** 담는다. 지킴이 본체(백엔드)가 **이 컴퓨터의 `127.0.0.1:8000`** 에 떠 있어야 한다.

- 이 컴퓨터에 지킴이를 설치했다면 그대로 쓴다. 아직이면 [루트 README 의 설치와 사용](../README.md#설치와-사용) 1~2단계부터.
- 원격 서버의 지킴이를 보려면 앱을 켜기 전에 SSH 터널을 열어 둔다: `ssh -L 8000:127.0.0.1:8000 사용자@서버주소` (창을 닫지 말 것).
- 본체는 이 앱을 알아보는 버전(1.0.0 릴리스 또는 PR #13 이후)이어야 한다. 그보다 오래된 본체는 앱의 요청을 거절한다.

1. **받기와 확인** — 터미널(`Ctrl` + `Alt` + `T`)에서:
   ```bash
   cd ~
   wget https://github.com/KunmyonChoi/Sentinel-Overwatch/releases/download/desktop-v0.1.1/sentinel-overwatch_0.1.1_amd64.deb
   wget https://github.com/KunmyonChoi/Sentinel-Overwatch/releases/download/desktop-v0.1.1/SHA256SUMS
   sha256sum -c --ignore-missing SHA256SUMS      # "…deb: OK" 가 아니면 설치하지 않는다
   ```
2. **설치** — 처음 한 번 내 계정 비밀번호를 묻는다(입력하는 글자는 보이지 않는다).
   ```bash
   sudo apt install ./sentinel-overwatch_0.1.1_amd64.deb
   ```
   설치하지 않고 쓰려면 같은 릴리스의 AppImage 를 받아 `chmod +x sentinel-overwatch_0.1.1_amd64.AppImage && ./sentinel-overwatch_0.1.1_amd64.AppImage`.
3. **실행** — 앱 메뉴에서 **내 컴퓨터 지킴이**(영문 환경에서는 Sentinel Overwatch)를 연다.
4. **토큰 넣기** — 처음 창이 뜨면 **"API 토큰 필요"** 창이 나온다. 토큰은 지킴이 화면에 들어가는 비밀 문자열이다.
   - 지킴이가 설치된 컴퓨터(원격이면 서버)의 터미널에서 `sudo cat /opt/secdash/backend/.api_token` 을 실행한다.
   - 나온 긴 문자열을 복사해(터미널에서는 `Ctrl` + `Shift` + `C`) 입력칸에 붙여 넣고 **연결** 을 누른다.
   - 토큰은 **OS 키링**(Ubuntu 의 '암호와 키')에 저장되어 다음 실행부터는 묻지 않는다. 토큰이 틀리거나 바뀌면 같은 창이 다시 뜬다.

## 동작

- 트레이 메뉴: `상태: …` · 창 열기 · 로그인할 때 자동으로 켜기 · 종료
- 창을 닫으면 앱은 끝나지 않고 트레이에 남는다. 끝내려면 메뉴의 **종료**.
- 두 번 실행하면 새로 뜨지 않고 떠 있는 창을 앞으로 가져온다.
- **Linux 제약**: AppIndicator 트레이는 아이콘 클릭 이벤트와 툴팁을 주지 않는다. 그래서 창은
  메뉴로 열고, 상태는 메뉴 첫 줄 글자로도 적는다. 순수 GNOME(Ubuntu 가 아닌 배포판)에서는
  AppIndicator 확장을 따로 켜야 트레이가 보인다.

## 지우기

```bash
sudo apt remove sentinel-overwatch
```

키링의 토큰은 남는다. 필요하면 '암호와 키'에서 `io.github.kunmyonchoi.sentinel` 항목을 지운다.

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
  키링을 쓸 수 없는 환경이면 예전처럼 창 안 저장소를 쓴다. 예전 원형이 창 안 저장소에 둔 토큰은 키링에 옮긴 뒤 지운다.

## 개발자용

상태 판정은 쉬운 화면과 **같은 함수**(`frontend/src/plain/tasks.js` 의 `buildTasks`·`statusOf`)로
`frontend/src/desktop.js` 가 15초마다 하고, 결과를 앱(`set_tray_status`)에 넘긴다.
두 곳에서 따로 판정하면 트레이와 화면이 다른 말을 하게 되기 때문이다.

### 준비 (Ubuntu 24.04)

```bash
sudo apt install libwebkit2gtk-4.1-dev build-essential curl wget file \
  libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev
rustup update stable          # Rust 최신 stable
cd desktop && npm install     # Tauri CLI
```

conda(miniforge)가 PATH 앞에 있으면 `cc` 가 conda 의 gcc 가 되어 링크가
`undefined symbol: __libc_csu_init` 로 실패한다. `src-tauri/.cargo/config.toml` 이 Linux x86_64 에서
시스템 gcc 를 쓰도록 고정해 두었다.

### 빌드와 개발 실행

```bash
cd desktop
npm ci && npm run build   # 화면 빌드(frontend → desktop/dist) + 앱 빌드
# → src-tauri/target/release/bundle/deb/Sentinel Overwatch_<버전>_amd64.deb
#   src-tauri/target/release/bundle/appimage/Sentinel Overwatch_<버전>_amd64.AppImage
```

빌드한 머신의 glibc 보다 오래된 배포판에서는 뜨지 않는다(Ubuntu 24.04 에서 빌드하면 glibc 2.39 필요).

화면을 고치면서 보려면 `./start.sh` 로 Vite(5173)를 띄운 뒤 `npx tauri dev`.
운영 인스턴스가 8000 을 쓰고 있으면 개발 인스턴스는 다른 포트로 띄우고
(`SECDASH_PORT=8001 SECDASH_UI_PORT=5174 ./start.sh`),
`npx tauri dev --config '{"build":{"devUrl":"http://127.0.0.1:5174"}}'` 로 붙는다.

### 직접 만든 패키지를 이 컴퓨터에서 시험하기

1. **운영 백엔드를 최신으로** (저장소 루트에서)
   ```bash
   (cd frontend && VITE_API_TOKEN= npx vite build)   # 웹 화면: 개발 토큰 없이
   sudo deploy/update.sh
   ```
   `update.sh` 는 `frontend/dist` 에 개발 토큰이 들어 있으면 웹 화면을 올리지 않고 알린다.
2. **설치** — `sudo apt install "./src-tauri/target/release/bundle/deb/Sentinel Overwatch_0.1.1_amd64.deb"`
3. **확인할 것** — 트레이 아이콘과 메뉴 첫 줄, 창 닫기(트레이에 남음)·창 열기, 로그인 시 자동 시작,
   운영 서비스를 멈췄을 때 "상태를 알 수 없어요" (`sudo systemctl stop secdash` → 확인 → `start`).

## 아직 안 한 것

- 원격 서버: 앱이 SSH 터널을 직접 여는 기능 (지금은 사용자가 연 터널에 붙는다)
- 서명된 패키지
- AppImage 실행 시험, 다른 컴퓨터에 설치해 보기 (deb 는 Ubuntu 24.04 에서 설치해 시험함)
