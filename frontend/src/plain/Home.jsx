import React from 'react';
import { Icon, Card, Btn, StatusHead, FactCard } from './ui';
import { TONE, toneOf } from './tokens';
import { KIND } from './tasks';

function TaskCard({ task, onOpen }) {
    const tone = toneOf(task.severity);
    const t = TONE[tone];
    return (
        <Card tone={tone} className="p-6">
            <div className="flex items-start gap-4">
                <div className={`${t.ring} ${t.fg} rounded-[9px] flex items-center justify-center shrink-0 mt-0.5`} style={{ width: 38, height: 38 }}>
                    <Icon name={task.icon} size={20} />
                </div>
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                        <div className="text-[19px] font-semibold leading-snug" style={{ wordBreak: 'keep-all' }}>{task.title}</div>
                        {task.response === 'unsure' && (
                            <span className="text-[11.5px] text-calm-warn border border-calm-warn rounded-full px-2 py-0.5 shrink-0">확인 중</span>
                        )}
                        {task.response === 'not_me' && (
                            <span className="text-[11.5px] text-calm-crit border border-calm-crit rounded-full px-2 py-0.5 shrink-0">내가 한 일 아님</span>
                        )}
                    </div>
                    {task.what && (
                        <div className="text-[15px] text-calm-muted leading-relaxed mt-2 max-w-[62ch]" style={{ wordBreak: 'keep-all' }}>
                            {task.what}
                        </div>
                    )}
                    <div className="flex items-center gap-2.5 mt-5 flex-wrap">
                        {task.kind === KIND.FIX && <Btn kind="primary" onClick={() => onOpen(task, 'fix')}>{task.fix.verb}</Btn>}
                        <Btn kind="outline" onClick={() => onOpen(task)}>
                            {task.kind === KIND.FIX ? '무엇이 바뀌는지 먼저 보기'
                                : task.kind === KIND.JUDGE ? (task.response ? '다시 보기' : '확인하기')
                                    : '어떻게 하는지 보기'}
                        </Btn>
                    </div>
                </div>
                {task.count > 1 && <div className="text-calm-muted text-[12.5px] whitespace-nowrap mt-1">{task.count}건</div>}
            </div>
        </Card>
    );
}

export default function Home({ status, tasks, facts, lastCheck, onOpenTask, onGo }) {
    const hasTasks = tasks.length > 0;
    return (
        <div className="flex flex-col min-h-full">
            <div className="flex items-center justify-between px-6 sm:px-10 py-5 border-b border-calm-line">
                <div className="flex items-center gap-2.5">
                    <span className="text-calm-accent"><Icon name="shield" size={22} /></span>
                    <span className="text-[16px] font-semibold tracking-tight">내 컴퓨터 지킴이</span>
                </div>
                <div className="flex items-center gap-1.5 text-calm-muted text-[13px]">
                    <Icon name="clock" size={15} />
                    <span>{lastCheck}</span>
                </div>
            </div>

            <div className={`flex-1 px-6 sm:px-10 ${hasTasks ? 'pt-8' : 'flex flex-col justify-center'}`}>
                <StatusHead tone={status.key} icon={status.key === 'ok' ? 'check' : 'alert'}
                    label={status.label} lead={status.lead} big={!hasTasks} />

                {hasTasks && (
                    <div className="flex flex-col gap-3 mt-6">
                        {tasks.map((t) => <TaskCard key={t.id} task={t} onOpen={onOpenTask} />)}
                    </div>
                )}

                <div className={`grid gap-4 ${hasTasks ? 'mt-6' : 'mt-10'} grid-cols-1 sm:grid-cols-3`}>
                    <FactCard icon="door" label="밖에서 들어올 수 있는 문"
                        value={`${facts.doors}개`} note={facts.doorsNote} />
                    <FactCard icon="update" label="밀린 보안 업데이트"
                        value={facts.updates} note={facts.updatesNote} />
                    <FactCard icon="shield" label={facts.blockedLabel}
                        value={facts.blocked} note={facts.blockedNote} />
                </div>
            </div>

            <div className="flex items-center gap-4 px-6 sm:px-10 py-3.5 border-t border-calm-line">
                <button onClick={() => onGo('history')}
                    className="h-11 -ml-3 px-3 rounded-lg inline-flex items-center gap-2 text-[14.5px] text-calm-accent hover:bg-calm-panel2 cursor-pointer font-kr">
                    <Icon name="chart" size={16} />무슨 일이 있었는지 보기
                </button>
                <button onClick={() => onGo('expert')}
                    className="h-11 px-3 rounded-lg inline-flex items-center text-[14.5px] text-calm-muted hover:bg-calm-panel2 cursor-pointer font-kr">
                    자세히 보기
                </button>
            </div>
        </div>
    );
}
