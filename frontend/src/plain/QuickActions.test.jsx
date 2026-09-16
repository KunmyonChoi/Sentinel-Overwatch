// @vitest-environment jsdom
//
// 홈의 '지금 할 수 있는 것'. 이 줄들은 root 권한이 필요한 조작이라, 버튼이 하는 일은
// '터미널에 붙여 넣을 명령을 보여주는 것'뿐이다. 그래서 여기서 지키는 것은 두 가지다.
//   1) 어떤 상태에서 어떤 줄과 버튼이 나오는가 (없는 것을 있다고 하지 않는가)
//   2) 버튼을 누르면 명령 글자가 그대로 나오는가
//
// '지금'은 컴포넌트가 시계를 읽지 않고 asOf 프로퍼티로 받는다(react-hooks/purity).
// 그래서 테스트도 시계를 고정할 필요 없이 asOf 를 넘기면 된다.
import React from 'react';
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import QuickActions from './QuickActions';

afterEach(cleanup);

// 화면을 받은 시각. 테스트 안에서 바뀌지 않는다.
const ASOF = Date.parse('2026-09-16T00:00:00Z');
const daysBefore = (n) => new Date(ASOF - n * 86400000).toISOString();

const usbHost = (state, commands = {}, state_ko = '상태') => ({
    usb_storage: { state, state_ko, commands },
});

const account = (over = {}) => ({
    uid: 1000,
    name: 'minji',
    state: 'active',
    state_ko: '쓰는 중',
    last_login: daysBefore(1),
    commands: { lock: 'sudo usermod -L minji', unlock: 'sudo usermod -U minji' },
    ...over,
});

describe('QuickActions — USB 저장장치', () => {
    it('막혀 있으면 잠깐 쓰기와 계속 쓰기로 바꾸기를 보여준다', () => {
        render(<QuickActions host={usbHost('blocked', {
            temp_unblock: 'sudo secdash-usb temp-unblock',
            permanent_unblock: 'sudo secdash-usb permanent-unblock',
        }, '막혀 있어요')} />);

        expect(screen.getByText('USB 저장장치')).toBeTruthy();
        expect(screen.getByText('막혀 있어요')).toBeTruthy();
        expect(screen.getByRole('button', { name: '잠깐 쓰기' })).toBeTruthy();
        expect(screen.getByRole('button', { name: '계속 쓰기로 바꾸기' })).toBeTruthy();
        // 이미 막혀 있으니 '다시 막기'는 나오지 않는다.
        expect(screen.queryByRole('button', { name: '다시 막기' })).toBeNull();
        expect(screen.getByText(/꽂아도 파일이 열리지 않아요/)).toBeTruthy();
    });

    it('잠깐 풀어둔 상태면 다시 막기와 항상 막기로 바꾸기를 보여준다', () => {
        render(<QuickActions host={usbHost('temporarily_unblocked', {
            reblock: 'sudo secdash-usb reblock',
            permanent_block: 'sudo secdash-usb permanent-block',
        }, '잠깐 열려 있어요')} />);

        expect(screen.getByRole('button', { name: '다시 막기' })).toBeTruthy();
        expect(screen.getByRole('button', { name: '항상 막기로 바꾸기' })).toBeTruthy();
        expect(screen.queryByRole('button', { name: '잠깐 쓰기' })).toBeNull();
    });

    it('열려 있으면 지금 열려 있다고 말한다', () => {
        render(<QuickActions host={usbHost('unblocked', {
            reblock: 'sudo secdash-usb reblock',
            permanent_block: 'sudo secdash-usb permanent-block',
        }, '열려 있어요')} />);

        expect(screen.getByText('지금은 USB 메모리를 꽂으면 파일이 열려요.')).toBeTruthy();
        expect(screen.getByRole('button', { name: '다시 막기' })).toBeTruthy();
    });

    it('상태를 모르면 USB 줄을 그리지 않는다', () => {
        const { container } = render(<QuickActions host={usbHost('unknown', {
            temp_unblock: 'sudo secdash-usb temp-unblock',
        })} />);

        expect(screen.queryByText('USB 저장장치')).toBeNull();
        expect(container.firstChild).toBeNull();
    });

    it('상태는 알아도 쓸 명령이 없으면 줄을 그리지 않는다', () => {
        const { container } = render(<QuickActions host={usbHost('blocked', {})} />);
        expect(container.firstChild).toBeNull();
    });
});

describe('QuickActions — 계정', () => {
    it('180일 넘게 안 쓴 계정은 잠그기를 보여준다', () => {
        render(<QuickActions accounts={[account({ last_login: daysBefore(200) })]} asOf={ASOF} />);

        expect(screen.getByText('계정 minji')).toBeTruthy();
        expect(screen.getByRole('button', { name: '이 계정 잠그기' })).toBeTruthy();
        expect(screen.getByText('180일 넘게 쓰지 않은 계정이에요. 안 쓰는 계정은 잠가두는 것이 안전해요.')).toBeTruthy();
    });

    it('잠긴 계정은 다시 쓸 수 있게 하기를 보여준다', () => {
        render(<QuickActions accounts={[account({ name: 'olduser', state: 'locked', state_ko: '잠김', last_login: null })]} asOf={ASOF} />);

        expect(screen.getByText('계정 olduser')).toBeTruthy();
        expect(screen.getByRole('button', { name: '다시 쓸 수 있게 하기' })).toBeTruthy();
        expect(screen.getByText('지금은 이 계정으로 로그인할 수 없어요. 다시 쓰려면 풀어 주세요.')).toBeTruthy();
    });

    it('최근에 쓴 계정은 줄을 만들지 않는다', () => {
        const { container } = render(<QuickActions accounts={[account({ last_login: daysBefore(3) })]} asOf={ASOF} />);
        expect(container.firstChild).toBeNull();
    });

    // 경계: 180일은 '넘게'가 아니다.
    it('딱 180일이면 아직 안 쓴 계정으로 보지 않고, 181일이면 본다', () => {
        const { container } = render(<QuickActions accounts={[account({ last_login: daysBefore(180) })]} asOf={ASOF} />);
        expect(container.firstChild).toBeNull();
        cleanup();

        render(<QuickActions accounts={[account({ last_login: daysBefore(181) })]} asOf={ASOF} />);
        expect(screen.getByText('계정 minji')).toBeTruthy();
    });

    // 기준 시각을 모르는데 "180일 넘게 안 썼다"고 적으면 지어낸 말이 된다.
    it('화면을 아직 한 번도 못 받았으면(asOf 없음) 미사용 여부를 말하지 않는다', () => {
        const { container } = render(<QuickActions accounts={[account({ last_login: daysBefore(200) })]} />);
        expect(container.firstChild).toBeNull();
    });

    it('root 계정은 건드리지 않는다', () => {
        const { container } = render(<QuickActions
            accounts={[account({ uid: 0, name: 'root', state: 'locked', state_ko: '잠김' })]}
            asOf={ASOF} />);
        expect(container.firstChild).toBeNull();
    });

    it('쓸 명령이 없는 계정은 줄을 만들지 않는다', () => {
        const { container } = render(<QuickActions
            accounts={[account({ state: 'locked', state_ko: '잠김', commands: undefined })]}
            asOf={ASOF} />);
        expect(container.firstChild).toBeNull();
    });

    it('안 쓰는 계정이 있으면 잠긴 계정보다 그것을 먼저 보여준다', () => {
        render(<QuickActions accounts={[
            account({ uid: 1001, name: 'lockeduser', state: 'locked', state_ko: '잠김', last_login: null }),
            account({ uid: 1000, name: 'unuseduser', last_login: daysBefore(200) }),
        ]} asOf={ASOF} />);

        expect(screen.getByText('계정 unuseduser')).toBeTruthy();
        expect(screen.queryByText('계정 lockeduser')).toBeNull();
    });
});

describe('QuickActions — 아무것도 없을 때', () => {
    it('host·accounts 를 못 읽었으면 빈 줄을 만들지 않고 자리를 비운다', () => {
        const { container } = render(<QuickActions />);
        expect(container.firstChild).toBeNull();
    });

    it('계정 목록이 비어 있어도 아무것도 그리지 않는다', () => {
        const { container } = render(<QuickActions host={{}} accounts={[]} asOf={ASOF} />);
        expect(container.firstChild).toBeNull();
    });
});

describe('QuickActions — 버튼은 붙여 넣을 명령을 보여준다', () => {
    it('USB 버튼을 누르면 명령 글자가 그대로 나온다', () => {
        const cmd = 'sudo secdash-usb temp-unblock';
        render(<QuickActions host={usbHost('blocked', { temp_unblock: cmd }, '막혀 있어요')} />);

        // 누르기 전에는 명령이 보이지 않는다.
        expect(screen.queryByText(cmd)).toBeNull();

        const btn = screen.getByRole('button', { name: '잠깐 쓰기' });
        expect(btn.getAttribute('aria-expanded')).toBe('false');
        fireEvent.click(btn);

        expect(screen.getByText(cmd)).toBeTruthy();
        expect(btn.getAttribute('aria-expanded')).toBe('true');
        expect(screen.getByRole('button', { name: /명령 복사하기/ })).toBeTruthy();
        expect(screen.getByText(/터미널에 붙여 넣고 Enter/)).toBeTruthy();
    });

    it('같은 버튼을 다시 누르면 명령을 접는다', () => {
        const cmd = 'sudo secdash-usb temp-unblock';
        render(<QuickActions host={usbHost('blocked', { temp_unblock: cmd }, '막혀 있어요')} />);

        const btn = screen.getByRole('button', { name: '잠깐 쓰기' });
        fireEvent.click(btn);
        expect(screen.getByText(cmd)).toBeTruthy();

        fireEvent.click(btn);
        expect(screen.queryByText(cmd)).toBeNull();
        expect(btn.getAttribute('aria-expanded')).toBe('false');
    });

    it('계정 잠그기 버튼을 누르면 그 계정의 명령이 나온다', () => {
        render(<QuickActions
            accounts={[account({ last_login: daysBefore(200), commands: { lock: 'sudo usermod -L minji' } })]}
            asOf={ASOF} />);

        fireEvent.click(screen.getByRole('button', { name: '이 계정 잠그기' }));

        expect(screen.getByText('sudo usermod -L minji')).toBeTruthy();
        expect(screen.getByText(/minji 계정으로는 로그인할 수 없게 돼요/)).toBeTruthy();
    });

    it('잠긴 계정 풀기 버튼을 누르면 풀는 명령이 나온다', () => {
        render(<QuickActions
            accounts={[account({ name: 'olduser', state: 'locked', state_ko: '잠김', last_login: null, commands: { unlock: 'sudo usermod -U olduser' } })]}
            asOf={ASOF} />);

        fireEvent.click(screen.getByRole('button', { name: '다시 쓸 수 있게 하기' }));

        expect(screen.getByText('sudo usermod -U olduser')).toBeTruthy();
    });

    it('USB 와 계정 줄이 함께 있으면 서로 다른 명령을 따로 펼친다', () => {
        render(<QuickActions
            host={usbHost('blocked', { temp_unblock: 'sudo usb-temp' }, '막혀 있어요')}
            accounts={[account({ last_login: daysBefore(200), commands: { lock: 'sudo lock-minji' } })]}
            asOf={ASOF} />);

        fireEvent.click(screen.getByRole('button', { name: '잠깐 쓰기' }));
        expect(screen.getByText('sudo usb-temp')).toBeTruthy();
        expect(screen.queryByText('sudo lock-minji')).toBeNull();

        // 한 번에 하나만 펼친다.
        fireEvent.click(screen.getByRole('button', { name: '이 계정 잠그기' }));
        expect(screen.getByText('sudo lock-minji')).toBeTruthy();
        expect(screen.queryByText('sudo usb-temp')).toBeNull();
    });
});
