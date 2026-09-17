// 앱과 서버의 버전.
//
// 둘은 따로 올라간다. 데스크톱 앱은 화면을 빌드할 때 안에 담아 두고, 서버는 update.sh 로 바뀐다.
// 그래서 "서버는 새것인데 앱은 옛것"인 상태가 흔히 생긴다. 문제를 물어볼 때 둘을 함께 말할 수
// 있도록 한 줄로 보여준다.

/**
 * 데스크톱 앱(Tauri) 안이면 앱 버전을, 브라우저면 null 을 돌려준다.
 * 읽다가 실패해도 null 이다 — 버전을 못 읽었다고 화면이 깨지면 안 된다.
 */
export async function readAppVersion() {
    const get = globalThis.window?.__TAURI__?.app?.getVersion;
    if (typeof get !== 'function') return null;
    try {
        return (await get()) || null;
    } catch {
        return null;
    }
}

/** "앱 0.1.1 · 서버 1.0.0". 모르는 쪽은 빼고, 둘 다 모르면 빈 문자열. */
export function versionLabel({ app = null, server = null } = {}) {
    const parts = [];
    if (app) parts.push(`앱 ${app}`);
    if (server) parts.push(`서버 ${server}`);
    return parts.join(' · ');
}
