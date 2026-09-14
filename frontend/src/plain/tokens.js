// 컴포넌트가 아닌 값들. (fast refresh 를 위해 컴포넌트 파일과 분리한다)

export const TONE = {
    ok: { ring: 'bg-calm-accent-soft', fg: 'text-calm-accent', border: 'border-calm-accent' },
    warn: { ring: 'bg-calm-warn-soft', fg: 'text-calm-warn', border: 'border-calm-warn' },
    crit: { ring: 'bg-calm-crit-soft', fg: 'text-calm-crit', border: 'border-calm-crit' },
    flat: { ring: 'bg-calm-panel2', fg: 'text-calm-muted', border: 'border-calm-line' },
};

export function toneOf(severity) {
    return severity === 'CRITICAL' ? 'crit' : severity === 'WARNING' ? 'warn' : 'flat';
}

/**
 * 지금 열려 있는 문의 개수.
 * IPv4·IPv6 는 같은 문이므로 포트로 묶는다.
 * 루프백(안에서만 쓰는 통로)과 client(브라우저 등이 나가면서 잠시 여는 통로)는 문이 아니다.
 */
const NOT_A_DOOR = new Set(['loopback', 'client']);
export function doorCount(exposure) {
    const out = new Set();
    for (const l of exposure?.listeners || []) {
        if (!NOT_A_DOOR.has(l.state)) out.add(`${l.proto}/${l.port}`);
    }
    return out.size;
}
