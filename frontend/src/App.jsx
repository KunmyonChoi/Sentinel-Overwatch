// 화면이 셋이다. 같은 자료를 세 가지 눈높이로 보여준다.
//
//   plain      쉬운 화면      — 지금 할 일만. 보안을 모르는 사람 기준.
//   expert     자세히 보기    — 예전 패널을 접이식으로. 쉬운 말 설명이 붙어 있다.
//   dashboard  대시보드       — 예전 전문가 화면 그대로. 한 화면에 전부 펼친다.
//
// 어느 화면을 쓰는지는 사람마다 다르고, 같은 사람도 상황에 따라 다르다.
// 그래서 고른 화면을 기억한다 — 새로고침하거나 다시 열어도 그 화면으로 돌아온다.
import React, { useCallback, useEffect, useState } from 'react';
import PlainApp from './plain/PlainApp';
import Dashboard from './Dashboard';

const KEY = 'secdash:view';
const VIEWS = ['plain', 'expert', 'dashboard'];

function loadView() {
  try {
    const v = localStorage.getItem(KEY);
    return VIEWS.includes(v) ? v : 'plain';
  } catch {
    return 'plain';   // 저장소를 못 읽는 브라우저에서도 화면은 떠야 한다
  }
}

export default function App() {
  const [view, setView] = useState(loadView);

  const go = useCallback((next) => {
    if (!VIEWS.includes(next)) return;
    setView(next);
    try { localStorage.setItem(KEY, next); } catch { /* 기억만 못 할 뿐 전환은 된다 */ }
  }, []);

  // 탭 제목도 화면을 따라간다 — 여러 탭을 띄워두는 사람이 구분할 수 있어야 한다.
  useEffect(() => {
    document.title = view === 'dashboard' ? 'Sentinel Overwatch' : '내 컴퓨터 지킴이';
  }, [view]);

  if (view === 'dashboard') return <Dashboard onGo={go} />;
  // 쉬운 화면과 자세히 보기는 자료를 함께 쓰므로 한 껍데기 안에 있다.
  return <PlainApp mode={view} onGo={go} />;
}
