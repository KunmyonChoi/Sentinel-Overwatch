// 데스크톱 앱(desktop/, Tauri) 안에서만 도는 다리. 브라우저에서는 아무것도 하지 않는다.
//
// 1. 토큰: 시작할 때 OS 키링에서 읽는다(initDesktop). 예전 원형이 창 안 저장소에 둔 토큰은
//    키링에 저장이 끝난 뒤에만 지운다 — 옮기다 실패해서 토큰을 잃지 않게.
// 2. 트레이: 상태를 여기서 판정해 앱에 넘긴다. 판정은 쉬운 화면과 같은 buildTasks·statusOf 를
//    쓴다 — 트레이와 화면이 서로 다른 말을 하면 안 되기 때문이다.
// 3. 긴급 알림: 처음 보는 긴급(CRITICAL) 알림을 OS 알림으로 한 번 띄운다.
// 화면이 전문가 모드여도, 창이 숨겨져 있어도 이 주기는 계속 돈다.
import { api, getToken, legacyStoredToken, configureTokenStore } from './api';
import { buildTasks, statusOf } from './plain/tasks';

const POLL_MS = 15000;
const NOTIFIED_KEY = 'secdash_notified_alerts';   // 이미 알린 알림 id. 토큰 같은 비밀은 아니다.
const NOTIFIED_MAX = 300;

const tauriInvoke = () => window.__TAURI__?.core?.invoke;

export async function initDesktop() {
    const invoke = tauriInvoke();
    if (!invoke) return;
    const legacy = legacyStoredToken();
    let initial;
    try {
        initial = (await invoke('token_get')) || '';
        if (!initial && legacy.token) {
            await invoke('token_set', { token: legacy.token });
            initial = legacy.token;
        }
    } catch (e) {
        // 키링을 쓸 수 없으면 예전처럼 창 안 저장소를 쓴다. 조용히 넘기지 않고 남긴다.
        console.warn('OS 키링을 쓸 수 없어 창 안 저장소에 토큰을 둡니다', e);
        return;
    }
    if (legacy.token) legacy.remove();
    configureTokenStore({
        initial,
        persist: (token) => (token ? invoke('token_set', { token }) : invoke('token_clear')),
    });
}

function loadNotified() {
    try {
        const ids = JSON.parse(localStorage.getItem(NOTIFIED_KEY) || '[]');
        return new Set(Array.isArray(ids) ? ids : []);
    } catch {
        return new Set();
    }
}

function saveNotified(set) {
    try {
        localStorage.setItem(NOTIFIED_KEY, JSON.stringify([...set].slice(-NOTIFIED_MAX)));
    } catch { /* 기억하지 못하면 다음 실행에서 한 번 더 알릴 뿐이다 */ }
}

/** 알릴 알림: 긴급, 아직 아무도 확인하지 않음(OPEN), 연습용 아님, 아직 알리지 않음. */
export function urgentToNotify(alerts, notified) {
    return (alerts || []).filter((a) =>
        a.severity === 'CRITICAL' && a.status === 'OPEN' && !a.is_simulation && !notified.has(String(a.id)));
}

export function startDesktopBridge() {
    const invoke = tauriInvoke();
    if (!invoke) return;

    const notified = loadNotified();
    let running = false;
    const tick = async () => {
        if (running) return;
        running = true;
        let status;
        let alerts = null;
        try {
            if (!getToken()) {
                status = { key: 'unknown', label: '토큰을 입력해야 해요' };
            } else {
                const [stats, active] = await Promise.all([
                    api('/api/stats'),
                    api('/api/alerts?status=active'),
                ]);
                alerts = active;
                // 개수가 아니라 할 일 목록을 넘긴다. 침입 신호인지 아닌지까지 같은 판정을 쓴다.
                status = statusOf(stats, buildTasks(active), 'ok');
            }
        } catch {
            // 못 읽었으면 '이상 없음'이라고 말하지 않는다.
            status = statusOf(null, 0, 'down');
        }
        invoke('set_tray_status', { level: status.key, label: status.label }).catch(() => {});

        for (const a of urgentToNotify(alerts, notified)) {
            try {
                await invoke('notify_urgent', {
                    title: `지금 확인하세요: ${a.title_ko || a.title}`,
                    body: '내 컴퓨터 지킴이 창을 열어 무슨 일인지 확인하세요.',
                });
                notified.add(String(a.id));
            } catch (e) {
                // 띄우지 못한 알림은 기억하지 않는다 — 다음 주기에 다시 시도한다.
                console.warn('OS 알림을 띄우지 못했습니다', e);
            }
        }
        saveNotified(notified);
        // 알림까지 끝난 뒤에 푼다. 먼저 풀면 알림을 띄우는 사이 다음 주기가 겹쳐 같은 알림을 두 번 띄운다.
        running = false;
    };

    tick();
    setInterval(tick, POLL_MS);
    window.addEventListener('secdash:token-changed', tick);
    window.addEventListener('secdash:unauthorized', tick);
}
