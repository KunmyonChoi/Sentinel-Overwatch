import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// 개발 시 /api 는 백엔드(127.0.0.1:8000)로 프록시한다. 빌드 결과는 백엔드가 직접 서빙한다.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1',
    proxy: {
      '/api': { target: process.env.SECDASH_API_URL || 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
})
