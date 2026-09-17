// @vitest-environment jsdom
//
// 데스크톱 앱의 다리. 여기서 지키는 것은 'OS 알림을 한 번만, 그리고 알릴 것만 띄우는가'다.
// 트레이 상태 판정은 쉬운 화면과 같은 buildTasks·statusOf 를 쓰므로 tasks.test.js 가 함께 지킨다.
import { describe, it, expect } from 'vitest';
import { urgentToNotify, initDesktop, startDesktopBridge } from './desktop';

const alert = (over = {}) => ({
    id: 1,
    severity: 'CRITICAL',
    status: 'OPEN',
    is_simulation: false,
    title: 'Something urgent',
    title_ko: '급한 일',
    ...over,
});

describe('urgentToNotify', () => {
    it('긴급하고 미확인이고 연습용이 아니고 아직 알리지 않은 것만 알린다', () => {
        const out = urgentToNotify([alert({ id: 7 })], new Set());
        expect(out.map((a) => a.id)).toEqual([7]);
    });

    it('긴급하지 않으면 알리지 않는다', () => {
        expect(urgentToNotify([alert({ severity: 'WARNING' })], new Set())).toEqual([]);
        expect(urgentToNotify([alert({ severity: 'INFO' })], new Set())).toEqual([]);
    });

    it('이미 확인한 알림은 알리지 않는다', () => {
        expect(urgentToNotify([alert({ status: 'ACKED' })], new Set())).toEqual([]);
        expect(urgentToNotify([alert({ status: 'RESOLVED' })], new Set())).toEqual([]);
    });

    it('연습용 알림은 알리지 않는다', () => {
        expect(urgentToNotify([alert({ is_simulation: true })], new Set())).toEqual([]);
    });

    // id 는 숫자로 오고 기억은 문자열로 남는다. 같은 것으로 봐야 두 번 알리지 않는다.
    it('이미 알린 알림은 다시 알리지 않는다 (숫자 id 와 문자열 기억을 같게 본다)', () => {
        expect(urgentToNotify([alert({ id: 7 })], new Set(['7']))).toEqual([]);
        expect(urgentToNotify([alert({ id: '7' })], new Set(['7']))).toEqual([]);
    });

    it('알릴 것과 아닌 것이 섞여 있으면 알릴 것만 골라낸다', () => {
        const out = urgentToNotify([
            alert({ id: 1, severity: 'WARNING' }),
            alert({ id: 2 }),
            alert({ id: 3, is_simulation: true }),
            alert({ id: 4, status: 'ACKED' }),
            alert({ id: 5 }),
            alert({ id: 6 }),
        ], new Set(['6']));
        expect(out.map((a) => a.id)).toEqual([2, 5]);
    });

    it('알림을 못 받았으면 아무것도 알리지 않는다', () => {
        expect(urgentToNotify(null, new Set())).toEqual([]);
        expect(urgentToNotify(undefined, new Set())).toEqual([]);
        expect(urgentToNotify([], new Set())).toEqual([]);
    });
});

// 브라우저에서는 아무것도 하지 않는다. window.__TAURI__ 가 없으면 조용히 빠져나온다 —
// 주기(setInterval)도 시작하지 않아야 테스트가 시계를 붙잡지 않는다.
describe('데스크톱 밖에서는 아무것도 하지 않는다', () => {
    it('startDesktopBridge 는 Tauri 가 없으면 아무 일도 하지 않는다', () => {
        expect(window.__TAURI__).toBeUndefined();
        expect(startDesktopBridge()).toBeUndefined();
    });

    it('initDesktop 은 Tauri 가 없으면 아무 일도 하지 않는다', async () => {
        await expect(initDesktop()).resolves.toBeUndefined();
    });
});
