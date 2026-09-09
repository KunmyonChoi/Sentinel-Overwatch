// 비전문가용 화면의 공통 조각. 아이콘은 전부 선으로 그린다 (이모지를 쓰지 않는다).
import React from 'react';
import { TONE } from './tokens';

const P = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' };

export function Icon({ name, size = 20, className = '' }) {
    const paths = {
        shield: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /><path d="M9 12h6" /></>,
        check: <path d="M20 6 9 17l-5-5" />,
        alert: <><path d="M12 9v4" /><path d="M12 17h.01" /><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /></>,
        lock: <><rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7.5a4 4 0 0 1 8 0V11" /></>,
        door: <><path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h8" /><path d="M14 3l5 2v14l-5 2z" /></>,
        update: <><path d="M12 3v11" /><path d="m7.5 9.5 4.5 4.5 4.5-4.5" /><path d="M5 20h14" /></>,
        box: <><path d="M21 8 12 3 3 8v8l9 5 9-5z" /><path d="m3 8 9 5 9-5" /><path d="M12 13v8" /></>,
        clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
        back: <><path d="M19 12H5" /><path d="m12 19-7-7 7-7" /></>,
        right: <path d="m9 18 6-6-6-6" />,
        down: <path d="m6 9 6 6 6-6" />,
        arrow: <><path d="M5 12h14" /><path d="m12 5 7 7-7 7" /></>,
        chart: <><path d="M3 3v18h18" /><path d="m7 14 3.5-4 3 3L18 8" /></>,
        eye: <><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6z" /><circle cx="12" cy="12" r="2.5" /></>,
        save: <><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" /><path d="M17 21v-8H7v8" /><path d="M7 3v5h8" /></>,
    };
    return (
        <svg width={size} height={size} viewBox="0 0 24 24" className={className} {...P} aria-hidden="true">
            {paths[name] || paths.alert}
        </svg>
    );
}

/** 기본 버튼. 히트 영역은 항상 44px 이상. */
export function Btn({ kind = 'ghost', children, className = '', ...rest }) {
    const base = 'h-12 px-5 rounded-lg text-[15px] font-kr inline-flex items-center gap-2 cursor-pointer disabled:opacity-50 disabled:cursor-default transition-colors';
    const kinds = {
        primary: 'bg-calm-accent text-white font-medium hover:bg-calm-accent2 border-0',
        outline: 'bg-calm-panel text-calm-ink border border-calm-line2 hover:bg-calm-panel2',
        danger: 'bg-calm-panel text-calm-crit border border-calm-crit font-medium hover:bg-calm-crit-soft',
        ghost: 'bg-transparent text-calm-muted border-0 hover:bg-calm-panel2',
    };
    return <button className={`${base} ${kinds[kind]} ${className}`} {...rest}>{children}</button>;
}

export function Card({ children, className = '', tone }) {
    const border = tone ? TONE[tone].border : 'border-calm-line';
    return <div className={`bg-calm-panel border ${border} rounded-xl ${className}`}>{children}</div>;
}

/** 큰 상태 표시. 화면에서 가장 큰 요소. */
export function StatusHead({ tone, icon, label, lead, big = true }) {
    const t = TONE[tone];
    return (
        <div className="flex items-center gap-5">
            <div className={`${t.ring} ${t.fg} rounded-full flex items-center justify-center shrink-0`}
                style={{ width: big ? 64 : 52, height: big ? 64 : 52 }}>
                <Icon name={icon} size={big ? 32 : 26} className="[stroke-width:2.3]" />
            </div>
            <div className="min-w-0">
                <div className={`font-semibold tracking-tight leading-tight ${big ? 'text-[34px]' : 'text-[28px]'}`}>{label}</div>
                {lead && <div className="text-[15px] text-calm-muted mt-1" style={{ wordBreak: 'keep-all' }}>{lead}</div>}
            </div>
        </div>
    );
}

/** 홈의 안심 정보 한 칸 */
export function FactCard({ icon, label, value, note }) {
    return (
        <Card className="p-5">
            <div className="flex items-center gap-2 text-calm-muted text-[13px] mb-3">
                <Icon name={icon} size={16} />
                <span style={{ wordBreak: 'keep-all' }}>{label}</span>
            </div>
            <div className="text-[26px] font-semibold leading-none">{value}</div>
            {note && <div className="text-[13px] text-calm-muted mt-2 leading-relaxed" style={{ wordBreak: 'keep-all' }}>{note}</div>}
        </Card>
    );
}

/** 전 → 후 한 줄 */
export function BeforeAfter({ label, sub, before, after }) {
    return (
        <div className="grid items-center gap-x-3 px-5 py-3 border-t border-[#eef2f0]"
            style={{ gridTemplateColumns: 'minmax(0,1fr) 150px 24px 150px' }}>
            <div className="min-w-0">
                <div className="text-[14.5px]" style={{ wordBreak: 'keep-all' }}>{label}</div>
                {sub && <div className="text-[12px] text-calm-muted mt-0.5 truncate" title={sub}>{sub}</div>}
            </div>
            <div className="text-[13.5px] text-calm-muted">{before}</div>
            <div className="text-calm-line2"><Icon name="arrow" size={18} /></div>
            <div className="text-[13.5px] text-calm-accent font-medium">{after}</div>
        </div>
    );
}

export function BackLink({ onClick, children = '돌아가기' }) {
    return (
        <button onClick={onClick}
            className="h-11 -ml-3 px-3 rounded-lg inline-flex items-center gap-1.5 text-[14px] text-calm-muted hover:bg-calm-panel2 cursor-pointer font-kr">
            <Icon name="back" size={17} />{children}
        </button>
    );
}
