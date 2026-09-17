// 프런트엔드 테스트 설정.
//
// vite.config.js 와 따로 둔다. vitest 는 vitest.config.js 가 있으면 그쪽을 먼저 읽는데,
// 빌드용 설정에 들어 있는 것(개발 프록시, tailwind)은 테스트에 필요하지 않다.
// JSX 를 읽어야 하므로 react 플러그인만 가져온다.
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    // 기본은 node 다. 화면을 그리는 테스트만 파일 맨 위에 @vitest-environment jsdom 을
    // 적어 jsdom 을 쓴다 — 판정 함수 테스트에까지 DOM 을 켜면 느려지기만 한다.
    environment: 'node',
    include: ['src/**/*.test.{js,jsx}'],
    // globals 를 켜지 않는다. describe·it·expect 를 파일마다 import 하면
    // eslint 에 테스트용 전역을 따로 열어주지 않아도 된다.
    globals: false,
    clearMocks: true,
    restoreMocks: true,
  },
})
