import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { initDesktop, startDesktopBridge } from './desktop.js'

// 데스크톱 앱에서는 OS 키링의 토큰을 먼저 읽고 화면을 그린다 — 그러지 않으면 토큰 입력 창이
// 잠깐 떴다 사라진다. 브라우저에서는 initDesktop 이 바로 끝난다.
initDesktop().finally(() => {
  startDesktopBridge()
  createRoot(document.getElementById('root')).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})
