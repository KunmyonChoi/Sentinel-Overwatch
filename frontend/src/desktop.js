// 데스크톱 앱(desktop/, Tauri) 안에서만 도는 다리. 브라우저에서는 아무것도 하지 않는다.
//
// 트레이 아이콘이 보여줄 상태를 여기서 판정해 앱에 넘긴다. 판정은 쉬운 화면과 같은
// buildTasks·statusOf 를 쓴다 — 트레이와 화면이 서로 다른 말을 하면 안 되기 때문이다.
// 화면이 전문가 모드여도, 창이 숨겨져 있어도 이 주기는 계속 돈다.
import { api, getToken } from './api';
import { buildTasks, statusOf } from './plain/tasks';

const POLL_MS = 15000;

export function startDesktopBridge() {
    const invoke = window.__TAURI__?.core?.invoke;
    if (!invoke) return;

    let running = false;
    const tick = async () => {
        if (running) return;
        running = true;
        let status;
        try {
            if (!getToken()) {
                status = { key: 'unknown', label: '토큰을 입력해야 해요' };
            } else {
                const [stats, alerts] = await Promise.all([
                    api('/api/stats'),
                    api('/api/alerts?status=active'),
                ]);
                status = statusOf(stats, buildTasks(alerts).length, 'ok');
            }
        } catch {
            // 못 읽었으면 '이상 없음'이라고 말하지 않는다.
            status = statusOf(null, 0, 'down');
        } finally {
            running = false;
        }
        invoke('set_tray_status', { level: status.key, label: status.label }).catch(() => {});
    };

    tick();
    setInterval(tick, POLL_MS);
    window.addEventListener('secdash:token-changed', tick);
    window.addEventListener('secdash:unauthorized', tick);
}
