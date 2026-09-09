// 전환이 두 종류다. 섞으면 화면 셋이 동등해 보이므로 축을 나눠 둔다.
//
//   모드 (누구를 위한 화면인가)      plain 초보자 · dashboard 전문가
//     └ ModeSwitch 로만 바뀐다. 어느 화면에서든 오른쪽 끝 같은 자리.
//
//   페이지 (같은 모드 안에서 어디)   초보자 모드: home · expert · task · history
//     └ 화면 안의 이동이다. 상단 바 왼쪽(위치)과 본문 링크로 오간다.
//
// 'expert'(자세히 보기)는 전문가 모드가 아니라 초보자 모드의 한 페이지다.
// 예전 패널을 담았을 뿐, 쉬운 말 설명이 붙어 있고 말투도 초보자 화면 그대로다.
import React, { useCallback, useEffect, useState } from 'react';
import PlainApp from './plain/PlainApp';
import Dashboard from './Dashboard';

const MODE_KEY = 'secdash:mode';
const PAGE_KEY = 'secdash:plain-page';
const MODES = ['plain', 'dashboard'];
// 기억하는 페이지는 머무는 곳뿐이다. 할 일 상세·기록은 잠깐 들르는 곳이라
// 새로고침하면 홈으로 돌아오는 게 맞다.
const PAGES = ['home', 'expert'];

function read(key, allowed, fallback) {
    try {
        const v = localStorage.getItem(key);
        return allowed.includes(v) ? v : fallback;
    } catch {
        return fallback;   // 저장소를 못 읽는 브라우저에서도 화면은 떠야 한다
    }
}

function write(key, value) {
    try { localStorage.setItem(key, value); } catch { /* 기억만 못 할 뿐 전환은 된다 */ }
}

export default function App() {
    const [mode, setMode] = useState(() => read(MODE_KEY, MODES, 'plain'));
    const [page, setPage] = useState(() => read(PAGE_KEY, PAGES, 'home'));

    const goMode = useCallback((next) => {
        if (!MODES.includes(next)) return;
        setMode(next);
        write(MODE_KEY, next);
    }, []);

    // 초보자 모드 안에서 머무는 페이지가 바뀌면 기억한다. 전문가 화면에 다녀와도
    // 보던 자리로 돌아온다.
    const goPage = useCallback((next) => {
        if (!PAGES.includes(next)) return;
        setPage(next);
        write(PAGE_KEY, next);
    }, []);

    // 탭 제목도 모드를 따라간다 — 여러 탭을 띄워두는 사람이 구분할 수 있어야 한다.
    useEffect(() => {
        document.title = mode === 'dashboard' ? 'Sentinel Overwatch' : '내 컴퓨터 지킴이';
    }, [mode]);

    if (mode === 'dashboard') return <Dashboard onMode={goMode} />;
    return <PlainApp page={page} onPage={goPage} onMode={goMode} />;
}
