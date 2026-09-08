// 백엔드 API 헬퍼. 모든 /api 호출에 X-API-Token 을 붙인다.
// 토큰 우선순위: localStorage → 빌드 시 VITE_API_TOKEN (개발 편의용)
const BASE = import.meta.env.VITE_API_BASE || '';
const STORAGE_KEY = 'secdash_token';

export function getToken() {
    try {
        return localStorage.getItem(STORAGE_KEY) || import.meta.env.VITE_API_TOKEN || '';
    } catch {
        return import.meta.env.VITE_API_TOKEN || '';
    }
}

export function setToken(token) {
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
