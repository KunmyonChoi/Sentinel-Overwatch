# frontend

Sentinel Overwatch 대시보드 UI (React + Vite + Tailwind). 상위 디렉터리의 README.md 를 참고하세요.

- 개발: 저장소 루트에서 `./start.sh` (백엔드와 함께 실행, `/api` 는 Vite 프록시)
- 빌드: `npm run build` → `dist/` 를 백엔드가 정적 서빙 (`deploy/build-release.sh` 가 수행)
- API 토큰은 브라우저 localStorage 에 저장되며, 개발 시 `.env.local` 의 `VITE_API_TOKEN` 으로 자동 주입됩니다.
