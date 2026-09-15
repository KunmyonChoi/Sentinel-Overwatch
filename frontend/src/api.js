// 백엔드 API 헬퍼. 모든 /api 호출에 X-API-Token 을 붙인다.
// 토큰 우선순위: (데스크톱 앱) OS 키링 → localStorage → 빌드 시 VITE_API_TOKEN (개발 편의용)
const BASE = import.meta.env.VITE_API_BASE || '';
const STORAGE_KEY = 'secdash_token';

// 데스크톱 앱에서는 토큰을 OS 키링에 둔다. desktop.js 가 시작할 때 키링에서 읽어 여기에 넣는다.
// null 이면 키링을 쓰지 않는다(브라우저, 또는 키링을 쓸 수 없는 경우) — 예전처럼 localStorage.
let memoryToken = null;
let persistToken = null;

export function configureTokenStore({ initial, persist }) {
    memoryToken = (initial || '').trim();
    persistToken = persist;
}

/** 예전 원형이 localStorage 에 둔 토큰. 키링으로 옮긴 뒤 remove() 로 지운다. */
export function legacyStoredToken() {
    try {
        return { token: localStorage.getItem(STORAGE_KEY) || '', remove: () => localStorage.removeItem(STORAGE_KEY) };
    } catch {
        return { token: '', remove: () => {} };
    }
}

export function getToken() {
    if (memoryToken !== null) return memoryToken || import.meta.env.VITE_API_TOKEN || '';
    try {
        return localStorage.getItem(STORAGE_KEY) || import.meta.env.VITE_API_TOKEN || '';
    } catch {
        return import.meta.env.VITE_API_TOKEN || '';
    }
}

export function setToken(token) {
    if (memoryToken !== null) {
        memoryToken = (token || '').trim();
        // 키링 쓰기가 실패해도 이번 실행 동안은 메모리의 토큰으로 계속 쓴다. 다음 실행에서 다시 묻는다.
        Promise.resolve(persistToken?.(memoryToken)).catch((e) => console.warn('토큰을 OS 키링에 저장하지 못했습니다', e));
        window.dispatchEvent(new CustomEvent('secdash:token-changed'));
        return;
    }
    try {
        if (token) localStorage.setItem(STORAGE_KEY, token.trim());
        else localStorage.removeItem(STORAGE_KEY);
    } catch { /* ignore */ }
    window.dispatchEvent(new CustomEvent('secdash:token-changed'));
}

export class ApiError extends Error {
    constructor(status, message) {
        super(message);
        this.status = status;
    }
}

export async function api(path, { method = 'GET', body } = {}) {
    const res = await fetch(`${BASE}${path}`, {
        method,
        headers: {
            'Content-Type': 'application/json',
            'X-API-Token': getToken(),
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (res.status === 401) {
        window.dispatchEvent(new CustomEvent('secdash:unauthorized'));
        throw new ApiError(401, 'unauthorized');
    }
    if (!res.ok) {
        let detail = res.statusText;
        try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
        throw new ApiError(res.status, detail);
    }
    return res.json();
}

export function fmtTime(iso) {
    if (!iso) return '';
    const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
    return d.toLocaleTimeString('ko-KR', { hour12: false });
}

export function fmtDateTime(iso) {
    if (!iso) return '';
    const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
    return d.toLocaleString('ko-KR', { hour12: false });
}
