// 모드 전환기. '누구를 위한 화면인가'를 바꾸는 유일한 조작이다.
//
// 쉬운 화면 ↔ 자세히 보기는 여기 들어오지 않는다. 둘 다 초보자 화면이고,
// 그 사이 이동은 '모드 바꾸기'가 아니라 '같은 모드 안에서 다른 페이지로 가기'다.
// 성격이 다른 두 전환을 같은 모양으로 늘어놓으면 세 화면이 동등해 보인다.
//
// 그래서 이 조각은 두 모드 어디서나 같은 자리(오른쪽 끝)에 같은 모양으로 있는다.
// 색만 화면에 맞춘다 — 초보자 화면은 문서 팔레트, 전문가 화면은 네온.
import React from 'react';

const MODES = [
    ['plain', '쉬운 화면'],
    ['dashboard', '전문가 화면'],
];

const TONE = {
    calm: {
        wrap: 'bg-calm-panel2 border border-calm-line',
        on: 'bg-calm-panel text-calm-ink shadow-sm',
        off: 'text-calm-muted hover:text-calm-ink',
    },
    neon: {
        wrap: 'border border-neon-green/30',
        on: 'bg-neon-green/15 text-neon-green',
        off: 'text-neon-green/45 hover:text-neon-green/80',
    },
};

export default function ModeSwitch({ mode, onChange, tone = 'calm' }) {
    const t = TONE[tone] || TONE.calm;
    return (
        <div role="group" aria-label="화면 모드" className={`inline-flex items-center gap-0.5 rounded-lg p-0.5 font-kr ${t.wrap}`}>
            {MODES.map(([id, label]) => {
                const on = mode === id;
                return (
                    <button key={id} type="button" onClick={() => !on && onChange(id)} aria-pressed={on}
                        className={`h-9 px-3 rounded-[7px] text-[13.5px] whitespace-nowrap transition-colors
                            ${on ? t.on : `${t.off} cursor-pointer`}`}>
                        {label}
                    </button>
                );
            })}
        </div>
    );
}
