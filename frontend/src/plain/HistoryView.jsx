import React, { useEffect, useState } from 'react';
import { api, fmtTime } from '../api';
import { Icon, Card, Btn } from './ui';
import { EVENT_KO } from './tasks';

// 백엔드가 만든 한국어 문장에 남아 있는 전문용어를 화면에서 마지막으로 걷어낸다.
const TERMS = [
    [/리스닝 포트/g, '밖에서 들어올 수 있는 문'],
    [/루프백/g, '이 컴퓨터 안에서만 쓰는'],
    [/바인딩 ?주소|바인드 ?주소/g, '연결 위치'],
    [/패키지/g, '프로그램'],
    [/브루트포스/g, '비밀번호를 계속 찍어보는 시도'],
    [/SSH 로그인/g, '원격 접속'],
    [/sudo 명령/g, '관리자 권한 명령'],
    [/무결성/g, '설정 파일'],
    [/컨테이너/g, '프로그램 묶음'],
];
function plainify(s) {
    let out = String(s || '');
    for (const [re, to] of TERMS) out = out.replace(re, to);
    return out;
}

function dayLabel(iso) {
    const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
    const today = new Date();
    const y = new Date(today); y.setDate(today.getDate() - 1);
    const same = (a, b) => a.toDateString() === b.toDateString();
    if (same(d, today)) return '오늘';
    if (same(d, y)) return '어제';
    return d.toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' });
}

/** 권한 조치 기록을 펼쳤을 때: 무엇이 바뀌었고, 되돌리려면 무엇을 해야 하는가 */
function FixedDetail({ ev }) {
    const d = ev.details || {};
    const [copied, setCopied] = useState(false);
    const cmd = d.path && d.before ? `chmod ${d.before} ${d.path}` : null;
    return (
        <div className="px-6 pb-4 pl-[95px] bg-[#f7fbf9] border-b border-[#eef2f0]">
            <div className="grid gap-y-1 gap-x-3 text-[13px] pt-2 pb-1" style={{ gridTemplateColumns: 'minmax(0,1fr) 120px 20px 120px' }}>
                <div className="text-calm-muted text-[12px]">파일</div>
                <div className="text-calm-muted text-[12px]">잠그기 전</div><div />
                <div className="text-calm-muted text-[12px]">지금</div>
                <div className="truncate" title={d.path}>{d.path}</div>
                <div className="text-calm-muted">{d.before}</div>
                <div className="text-calm-line2">→</div>
                <div className="text-calm-accent">{d.after}</div>
            </div>
            {cmd && (
                <div className="mt-2.5">
                    <div className="text-[13px] text-calm-muted" style={{ wordBreak: 'keep-all' }}>
                        되돌리려면 아래 명령을 터미널에 붙여넣으세요. 지킴이는 <b className="text-calm-ink">잠그기만</b> 하고 다시 열지는 않아요 —
                        여는 일은 사람이 직접 하도록 남겨둡니다.
                    </div>
                    <div className="flex items-center gap-2 mt-2">
                        <code className="text-[12.5px] font-mono bg-calm-panel border border-calm-line rounded px-2 py-1.5">{cmd}</code>
                        <Btn kind="outline" className="h-11 px-3 text-[13px]"
                            onClick={() => { navigator.clipboard.writeText(cmd); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>
                            {copied ? '복사됨' : '복사'}
                        </Btn>
                    </div>
                </div>
            )}
        </div>
    );
}

export default function HistoryView() {
    const [events, setEvents] = useState(null);
    const [open, setOpen] = useState(null);

    useEffect(() => {
        let alive = true;
        api('/api/events?limit=80&include_simulation=false')
            .then((d) => { if (alive) setEvents(d); })
            .catch(() => { if (alive) setEvents([]); });
        return () => { alive = false; };
    }, []);

    const save = () => {
        const text = (events || []).map((e) => `${e.timestamp}  ${plainify(e.description_ko || e.description)}`).join('\n');
        const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `내컴퓨터지킴이-기록-${new Date().toISOString().slice(0, 10)}.txt`;
        a.click();
        URL.revokeObjectURL(a.href);
    };

    // 날짜 머리글은 렌더 중 변수를 고쳐 쓰지 않고 미리 계산한다
    const rows = [];
    let prevDay = null;
    for (const e of events || []) {
        const day = dayLabel(e.timestamp);
        rows.push({ e, head: day !== prevDay ? day : null });
        prevDay = day;
    }

    return (
        <div className="flex flex-col min-h-full">
            <div className="flex-1 px-6 sm:px-10 py-6 pb-10">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div className="text-[25px] font-semibold tracking-tight">무슨 일이 있었는지</div>
                    <Btn kind="outline" className="h-11 px-4 text-[14px]" onClick={save}>
                        <Icon name="save" size={16} />파일로 저장
                    </Btn>
                </div>
                <div className="text-[14px] text-calm-muted mt-1.5" style={{ wordBreak: 'keep-all' }}>
                    지킴이가 한 일과 컴퓨터에 생긴 일을 시간 순서로 적어둬요. 줄을 누르면 자세히 볼 수 있어요.
                </div>

                {events === null && <div className="mt-6 text-[14px] text-calm-muted">불러오는 중이에요…</div>}
                {events && events.length === 0 && (
                    <Card className="mt-5 p-6 text-[14px] text-calm-muted">아직 적어둘 일이 없어요.</Card>
                )}

                {events && events.length > 0 && (
                    <Card className="mt-5 overflow-hidden">
                        {rows.map(({ e, head }) => {
                            const meta = EVENT_KO[e.event_type] || { icon: 'alert', who: '기록' };
                            const expandable = e.event_type === 'PERMISSION_FIXED';
                            const isOpen = open === e.id;
                            const tone = e.severity === 'CRITICAL' ? 'text-calm-crit' : e.severity === 'WARNING' ? 'text-calm-warn' : 'text-calm-muted';
                            return (
                                <React.Fragment key={e.id}>
                                    {head && (
                                        <div className="px-6 py-2.5 bg-calm-panel2 text-[12.5px] font-medium text-calm-muted border-t border-calm-line first:border-t-0">{head}</div>
                                    )}
                                    <div onClick={() => expandable && setOpen(isOpen ? null : e.id)}
                                        className={`grid items-start gap-x-3 px-6 py-3 border-t border-[#eef2f0] ${expandable ? 'cursor-pointer hover:bg-[#f7fbf9]' : ''} ${isOpen ? 'bg-[#f7fbf9]' : ''}`}
                                        style={{ gridTemplateColumns: '58px 24px minmax(0,1fr) auto 18px' }}>
                                        <div className="text-[13px] text-calm-muted pt-0.5">{fmtTime(e.timestamp).slice(0, 5)}</div>
                                        <div className={`${tone} pt-0.5`}><Icon name={meta.icon} size={19} /></div>
                                        <div className="min-w-0">
                                            <div className="text-[14.8px] leading-snug" style={{ wordBreak: 'keep-all' }}>
                                                {plainify(e.description_ko || e.description)}
                                            </div>
                                        </div>
                                        <div className="text-[12px] text-calm-muted whitespace-nowrap pt-1">{meta.who}</div>
                                        <div className="text-calm-line2 pt-1">
                                            {expandable && <Icon name="down" size={16} className={isOpen ? 'rotate-180' : ''} />}
                                        </div>
                                    </div>
                                    {expandable && isOpen && <FixedDetail ev={e} />}
                                </React.Fragment>
                            );
                        })}
                    </Card>
                )}

                <div className="mt-4 text-[13px] text-calm-muted">30일치를 보관해요. 더 필요하면 위의 ‘파일로 저장’을 눌러 두세요.</div>
            </div>
        </div>
    );
}
