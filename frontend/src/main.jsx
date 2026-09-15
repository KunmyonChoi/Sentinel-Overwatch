import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { startDesktopBridge } from './desktop.js'

// 데스크톱 앱 안에서만 트레이 상태를 보낸다. 브라우저에서는 아무것도 하지 않는다.
startDesktopBridge()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
