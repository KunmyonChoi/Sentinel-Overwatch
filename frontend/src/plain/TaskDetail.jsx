import React, { useEffect, useState } from 'react';
import { api, fmtDateTime } from '../api';
import { Icon, Card, Btn, BackLink, BeforeAfter, StatusHead } from './ui';
import { TONE, toneOf } from './tokens';
import { KIND, JUDGE_STEPS } from './tasks';
import { buildBrief, copyText } from './brief';

// 권한 조치 미리보기 결과의 파일 경로 → 사람이 아는 이름
const FILE_KO = [
    [/\.bashrc$/, '터미널을 열 때 실행되는 설정'],
    [/\.zshrc$/, '터미널을 열 때 실행되는 설정'],
    [/\.profile$|\.bash_profile$/, '로그인할 때 실행되는 설정'],
    [/\.gitconfig$/, '개발 도구 설정'],
    [/\.local\/bin$/, '내가 설치한 프로그램이 들어가는 폴더'],
    [/\.ssh$/, '접속 열쇠를 넣어두는 폴더'],
    [/\.ssh\/config$/, '접속 설정'],
    [/\.ssh\/id_/, '접속에 쓰는 개인 열쇠'],
    [/\.config$/, '프로그램 설정이 모여 있는 폴더'],
    [/\.env$/, '프로그램이 쓰는 비밀값 파일'],
    [/\.aws|\.docker|\.claude|\.kube/, '서비스 접속 정보 폴더'],
];
function fileKo(path) {
    const base = String(path || '');
    for (const [re, ko] of FILE_KO) if (re.test(base)) return ko;
    return base.split('/').slice(-1)[0] || base;
}
const modeKo = (m, isDir) => {
    const o = String(m || '');
    if (/[2367]$/.test(o)) return isDir ? '누구나 넣을 수 있음' : '누구나 고칠 수 있음';
    if (/[2367]$/.test(o.slice(1, 2))) return '같은 그룹이 고칠 수 있음';
    if (o === '700' || o === '600') return isDir ? '나만 열 수 있음' : '나만 고칠 수 있음';
    if (o === '750' || o === '640' || o === '644') return isDir ? '나만 열 수 있음' : '나만 고칠 수 있음';
    return isDir ? '나만 열 수 있음' : '나만 고칠 수 있음';
};

/** 버튼 하나로 끝나는 일: 미리보기 → 적용 → 결과 */
function FixFlow({ task, onDone }) {
    const [preview, setPreview] = useState(null);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const [busy, setBusy] = useState(false);

    const call = async (apply) => {
        setBusy(true); setError(null);
        try {
            const r = await api(`/api/permissions/fix?apply=${apply}`, { method: 'POST' });
            if (!r.ok) { setError(r); return; }
            if (apply) { setResult(r); onDone?.(); } else setPreview(r);
        } catch (e) {
            setError({ error: e.message || '요청이 실패했어요', fix_hint: '' });
        } finally { setBusy(false); }
    };

    // 상세 화면에 들어오면 바로 미리보기를 부른다 (한 번만)
    useEffect(() => { call(false); }, []);  // eslint-disable-line react-hooks/exhaustive-deps

    if (result) {
        return (
            <div className="mt-7">
                <StatusHead tone="ok" icon="lock" label={task.fix.done} big={false}
                    lead={`${result.changed}개를 나만 고칠 수 있게 바꿨어요.`} />
                <Card className="mt-6 overflow-hidden">
                    <div className="grid gap-x-3 px-5 pt-2.5 pb-1.5 text-[12px] text-calm-muted bg-calm-panel2"
                        style={{ gridTemplateColumns: 'minmax(0,1fr) 150px 24px 150px' }}>
                        <div>파일</div><div>잠그기 전</div><div /><div>지금</div>
                    </div>
                    {(result.results || []).filter((r) => r.applied).map((r) => (
                        <BeforeAfter key={r.path} label={fileKo(r.path)} sub={r.path}
                            before={modeKo(r.before, r.kind === 'world_writable' && !r.path.includes('.'))}
                            after={modeKo(r.after, r.kind === 'world_writable' && !r.path.includes('.'))} />
                    ))}
                </Card>
                <Card className="mt-5 p-5">
                    <div className="text-[14px] font-semibold mb-1.5">혹시 뭔가 안 되나요?</div>
                    <div className="text-[14px] text-calm-muted leading-relaxed max-w-[74ch]" style={{ wordBreak: 'keep-all' }}>
                        이 변경은 <b className="text-calm-ink">기록</b>에 그대로 남아 있어요. 무엇이 어떻게 바뀌었는지 시간과 함께 볼 수 있고, 되돌리는 방법도 거기에 적어뒀어요.
                    </div>
                </Card>
            </div>
        );
    }

    return (
        <div className="mt-7">
            {error && (
                <Card tone="warn" className="p-4 mb-4">
                    <div className="text-[14px] text-calm-warn flex items-start gap-2" style={{ wordBreak: 'keep-all' }}>
                        <Icon name="alert" size={16} className="mt-0.5 shrink-0" />
                        <div>
                            <div>지금은 대신 처리해 드릴 수 없어요 — {error.error}</div>
                            {error.fix_hint && <div className="text-calm-muted mt-1 text-[13px]">해결: {error.fix_hint}</div>}
                        </div>
                    </div>
                </Card>
            )}

            <Card className="overflow-hidden">
                <div className="flex items-center gap-2 px-5 py-3.5 border-b border-calm-line bg-calm-panel2">
                    <Icon name="eye" size={17} className="text-calm-muted" />
                    <span className="text-[14px] font-medium">무엇이 바뀌는지 먼저 보여드릴게요</span>
                </div>
                {busy && !preview && <div className="px-5 py-6 text-[14px] text-calm-muted">확인하는 중이에요…</div>}
                {preview && (preview.results || []).length === 0 && (
                    <div className="px-5 py-6 text-[14px] text-calm-muted">바꿀 것이 없어요. 이미 잠겨 있어요.</div>
                )}
                {preview && (preview.results || []).length > 0 && (
                    <>
                        <div className="grid gap-x-3 px-5 pt-1.5 pb-1 text-[12px] text-calm-muted"
                            style={{ gridTemplateColumns: 'minmax(0,1fr) 150px 24px 150px' }}>
                            <div>파일</div><div>지금</div><div /><div>잠근 뒤</div>
                        </div>
                        {preview.results.map((r) => (
                            <BeforeAfter key={r.path} label={fileKo(r.path)} sub={r.path}
                                before={modeKo(r.before, false)} after={modeKo(r.after, false)} />
                        ))}
                        <div className="flex items-center gap-2 px-5 py-3 border-t border-calm-line bg-[#f7fbf9] text-[13.5px] text-calm-muted">
                            <Icon name="check" size={16} className="text-calm-accent shrink-0" />
                            <span><b className="text-calm-ink">{task.fix.note}</b></span>
                        </div>
                    </>
                )}
            </Card>

            <div className="flex items-center gap-2.5 mt-6 flex-wrap">
                <Btn kind="primary" disabled={busy || !preview || !(preview.results || []).length} onClick={() => call(true)}>
                    {busy ? '처리 중이에요…' : task.fix.verb}
                </Btn>
                <Btn kind="outline" onClick={onDone}>나중에</Btn>
                <div className="text-[13px] text-calm-muted ml-1" style={{ wordBreak: 'keep-all' }}>
                    되돌리고 싶으면 기록에서 언제든 확인할 수 있어요.
                </div>
            </div>
        </div>
    );
}

/** 본인만 아는 일: 본인 여부를 묻고, 아니라면 순서대로 안내 */
function JudgeFlow({ task, onAck }) {
    const [mine, setMine] = useState(null);
    return (
        <div className="mt-7">
            <div className="text-[17px] font-semibold">{task.ask}</div>
            <div className="text-[13.5px] text-calm-muted mt-1.5" style={{ wordBreak: 'keep-all' }}>
                기억이 잘 안 나시면, 바로 아래 <b className="text-calm-ink">지킴이가 본 것</b>을 펼쳐서 언제 무슨 일이 있었는지 확인하고 정하세요.
            </div>
            <div className="flex items-center gap-2.5 mt-3.5 flex-wrap">
                <Btn kind="outline" onClick={() => { setMine(true); onAck(); }}>네, 제가 했어요</Btn>
                <Btn kind="danger" onClick={() => setMine(false)}>아니요 · 모르겠어요</Btn>
            </div>
            {mine === true && (
                <Card tone="ok" className="mt-5 p-5">
                    <div className="flex items-center gap-2 text-[14.5px]">
                        <Icon name="check" size={18} className="text-calm-accent" />
                        확인 처리했어요. 이 일은 목록에서 빠집니다.
                    </div>
                </Card>
            )}
            {mine === false && (
                <div className="mt-5 bg-calm-panel border border-calm-line border-l-[3px] border-l-calm-crit rounded-r-xl p-5">
                    <div className="text-[15px] font-semibold">순서대로 해주세요</div>
                    <div className="text-[13px] text-calm-muted mt-1 mb-3">확실하지 않으면 ‘아니요’로 보고 아래대로 하세요.</div>
                    <div className="grid gap-3">
                        {JUDGE_STEPS.map((s, i) => (
                            <div key={i} className="flex gap-3 items-start">
                                <div className="w-[22px] h-[22px] rounded-full bg-calm-bg border border-calm-line2 flex items-center justify-center text-[12px] text-calm-muted shrink-0">{i + 1}</div>
                                <div className="text-[14.5px] leading-relaxed" style={{ wordBreak: 'keep-all' }}>
                                    <b>{s.b}</b> <span className="text-calm-muted">{s.t}</span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

/** 순서대로 알려주는 일 */
function GuideFlow({ task, onAck }) {
    return (
        <div className="mt-7">
            <div className="text-[17px] font-semibold">이렇게 하시면 돼요</div>
            <div className="grid gap-3 mt-3">
                {task.steps.map((s, i) => (
                    <div key={i} className="flex gap-3 items-start">
                        <div className="w-[22px] h-[22px] rounded-full bg-calm-panel border border-calm-line2 flex items-center justify-center text-[12px] text-calm-muted shrink-0">{i + 1}</div>
                        <div className="text-[14.5px] leading-relaxed max-w-[74ch]" style={{ wordBreak: 'keep-all' }}>{s}</div>
                    </div>
                ))}
            </div>
            <div className="mt-6"><Btn kind="outline" onClick={onAck}>확인했어요</Btn></div>
        </div>
    );
}

/**
 * 지킴이가 실제로 본 것.
 *
 * 접어두되 '열 수 있다'가 분명히 보여야 한다. 사용자가 판단하려면 결국 여기까지 봐야 하는데,
 * 흐린 글씨 한 줄로 두면 그냥 지나친다. 그래서 (1) 카드로 만들고 (2) 닫혀 있을 때도 첫 줄을
 * 미리 보여주고 (3) 무엇이 들어 있는지와 몇 건인지를 적는다.
 * 펼친 상태로 시작하지는 않는다 — 20건짜리 묶음도 있어서, 펼쳐두면 그 아래 내용이 화면 밖으로 밀린다.
 */
function Evidence({ task }) {
    const [open, setOpen] = useState(false);
    const first = task.alerts[0];
    const teaser = first?.summary_ko || first?.title_ko || first?.title || '';

    return (
        <Card className="mt-8 overflow-hidden">
            <button onClick={() => setOpen(!open)} aria-expanded={open}
                className="w-full text-left px-5 py-4 flex items-start gap-3 cursor-pointer hover:bg-[#f7fbf9] font-kr">
                <span className="text-calm-accent mt-0.5 shrink-0"><Icon name="eye" size={20} /></span>
                <span className="flex-1 min-w-0">
                    <span className="flex items-center gap-2 flex-wrap">
                        <span className="text-[15.5px] font-semibold">지킴이가 본 것</span>
                        <span className="text-[12px] text-calm-accent bg-calm-accent-soft rounded-full px-2 py-0.5">{task.count}건</span>
                    </span>
                    <span className="block text-[13.5px] text-calm-muted mt-1" style={{ wordBreak: 'keep-all' }}>
                        {open ? '무엇을 보고 이렇게 판단했는지 그대로 보여드려요.'
                            : '무엇을 보고 이렇게 판단했는지 확인해 보세요. 직접 보시면 판단하기 쉬워요.'}
                    </span>
                </span>
                <span className="flex items-center gap-1.5 text-[13.5px] text-calm-accent shrink-0 pt-0.5">
                    {open ? '접기' : '열어보기'}
                    <Icon name="down" size={17} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
                </span>
            </button>

            {/* 닫혀 있어도 한 줄은 보인다 — 안에 뭔가 있다는 것이 눈에 보여야 열어본다 */}
            {!open && teaser && (
                <div onClick={() => setOpen(true)}
                    className="px-5 pb-4 -mt-1 cursor-pointer" >
                    <div className="border-l-2 border-calm-line2 pl-3 text-[13px] text-calm-muted line-clamp-2"
                        style={{ wordBreak: 'keep-all' }}>
                        {teaser}
                    </div>
                    {task.count > 1 && (
                        <div className="text-[12.5px] text-calm-muted mt-1.5 pl-3">…그리고 {task.count - 1}건 더</div>
                    )}
                </div>
            )}

            {open && (
                <div className="px-5 pb-5 grid gap-2.5">
                    {task.alerts.map((a, i) => (
                        <div key={a.id} className="border border-calm-line rounded-lg p-4 bg-calm-bg">
                            <div className="flex items-start gap-2">
                                <span className="text-[12px] text-calm-muted shrink-0 pt-0.5 tabular-nums">{i + 1}</span>
                                <div className="min-w-0">
                                    <div className="text-[13.5px] font-medium" style={{ wordBreak: 'keep-all' }}>{a.title_ko || a.title}</div>
                                    {a.summary_ko && <div className="text-[13px] text-calm-muted mt-1" style={{ wordBreak: 'keep-all' }}>{a.summary_ko}</div>}
                                    {a.evidence && <div className="text-[12px] text-calm-muted mt-1.5 font-mono break-all">{a.evidence}</div>}
                                    {a.last_seen_at && <div className="text-[12px] text-calm-muted mt-1.5">{fmtDateTime(a.last_seen_at)}</div>}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </Card>
    );
}

/**
 * 이해가 안 될 때: 세부 내용을 그대로 복사해 다른 곳에 물어볼 수 있게 한다.
 * 대시보드가 스스로 밖으로 보내는 것은 없다 — 사람이 붙여넣을 때만 나간다.
 * 그 사실을 버튼 옆에 적어둔다. 비전문가는 무엇이 복사되는지 모를 수 있다.
 */
function AskElsewhere({ task, host, accounts }) {
    const [state, setState] = useState('idle');   // idle | ok | fail
    const [shown, setShown] = useState(false);
    const [mask, setMask] = useState(true);       // 가리는 것이 기본이다
    const brief = buildBrief(task, host, mask, accounts);

    const copy = async () => {
        const ok = await copyText(brief);
        setState(ok ? 'ok' : 'fail');
        if (!ok) setShown(true);
        setTimeout(() => setState('idle'), 2500);
    };

    return (
        <Card className="mt-4 p-5">
            <div className="flex items-start gap-3 flex-wrap">
                <span className="text-calm-accent mt-0.5 shrink-0"><Icon name="chat" size={20} /></span>
                <div className="flex-1 min-w-[260px]">
                    <div className="text-[15.5px] font-semibold">설명이 어렵거나 더 묻고 싶으면</div>
                    <div className="text-[13.5px] text-calm-muted mt-1 leading-relaxed" style={{ wordBreak: 'keep-all' }}>
                        위 내용을 그대로 복사해서 Claude 같은 AI나 잘 아는 분에게 붙여넣어 물어보세요.
                        무엇을 물어보면 좋을지까지 함께 적어드려요.
                    </div>
                    <label className="flex items-start gap-2.5 mt-3 cursor-pointer select-none">
                        <input type="checkbox" checked={mask} onChange={(e) => setMask(e.target.checked)}
                            className="mt-0.5 w-4 h-4 accent-[#0e7c6b] cursor-pointer shrink-0" />
                        <span className="text-[13px]" style={{ wordBreak: 'keep-all' }}>
                            <b>중요한 정보 가리기</b>
                            <span className="text-calm-muted">
                                {' '}— 컴퓨터 이름, 계정 이름, 인터넷 주소를 <span className="font-mono">&lt;이렇게&gt;</span> 바꿔서 복사해요.
                                운영체제·프로그램 이름·포트 번호는 남겨요. 그게 있어야 제대로 된 답을 받을 수 있고, 그것만으로는 이 컴퓨터를 찾아낼 수 없거든요.
                            </span>
                        </span>
                    </label>
                    {!mask && (
                        <div className="text-[12.5px] text-calm-warn mt-2 flex items-start gap-1.5" style={{ wordBreak: 'keep-all' }}>
                            <Icon name="alert" size={14} className="mt-0.5 shrink-0" />
                            가리지 않고 복사하면 이 컴퓨터의 이름과 주소가 그대로 나갑니다. 믿을 수 있는 곳에만 붙여넣으세요.
                        </div>
                    )}
                </div>
                <div className="flex flex-col gap-2 shrink-0">
                    <Btn kind="primary" onClick={copy} className="h-11">
                        <Icon name="copy" size={16} />
                        {state === 'ok' ? '복사했어요' : state === 'fail' ? '복사 실패' : '복사하기'}
                    </Btn>
                    <button onClick={() => setShown(!shown)}
                        className="h-9 px-3 rounded-lg text-[13px] text-calm-muted hover:bg-calm-panel2 cursor-pointer font-kr">
                        {shown ? '내용 접기' : '무엇이 복사되는지 보기'}
                    </button>
                </div>
            </div>

            {shown && (
                <>
                    {state === 'fail' && (
                        <div className="text-[13px] text-calm-warn mt-3" style={{ wordBreak: 'keep-all' }}>
                            자동 복사가 막혀 있어요. 아래 글을 직접 끌어서 복사해 주세요.
                        </div>
                    )}
                    <pre className="mt-3 max-h-72 overflow-auto text-[12.5px] leading-relaxed bg-calm-bg border border-calm-line rounded-lg p-4 whitespace-pre-wrap font-mono select-all">
                        {brief}
                    </pre>
                </>
            )}
        </Card>
    );
}

export default function TaskDetail({ task, onBack, onChanged, host, accounts }) {
    const tone = toneOf(task.severity);
    const ackAll = async () => {
        try {
            await api('/api/alerts/ack-all', { method: 'POST', body: { ids: task.alerts.map((a) => a.id), by: '사용자', note: '쉬운 화면에서 확인' } });
        } catch { /* 확인 처리 실패는 화면을 막지 않는다 */ }
        onChanged?.(); onBack();
    };

    return (
        <div className="flex flex-col min-h-full">
            <div className="px-6 sm:px-10 py-3.5 border-b border-calm-line">
                <BackLink onClick={onBack} />
            </div>
            <div className="flex-1 px-6 sm:px-10 py-7 pb-10">
                <div className="flex items-start gap-4">
                    <div className={`${TONE[tone].ring} ${TONE[tone].fg} rounded-full flex items-center justify-center shrink-0 mt-0.5`} style={{ width: 46, height: 46 }}>
                        <Icon name={task.icon} size={24} />
                    </div>
                    <div className="min-w-0">
                        {task.severity === 'CRITICAL' && <div className="text-[13px] font-medium text-calm-crit tracking-wide">지금 확인하세요</div>}
                        <div className="text-[25px] font-semibold tracking-tight leading-snug" style={{ wordBreak: 'keep-all' }}>{task.title}</div>
                        {!task.known && <div className="text-[12.5px] text-calm-muted mt-1">아직 쉬운 말로 옮기지 못한 항목이에요. 아래 설명을 그대로 보여드려요.</div>}
                    </div>
                </div>

                <div className="grid gap-6 sm:grid-cols-2 mt-6">
                    <div>
                        <div className="text-[14px] font-semibold text-calm-accent mb-1.5">무슨 일인가요?</div>
                        <div className="text-[14.5px] leading-relaxed" style={{ wordBreak: 'keep-all' }}>{task.what || '자세한 내용은 아래 근거를 보세요.'}</div>
                    </div>
                    {task.why && (
                        <div>
                            <div className="text-[14px] font-semibold text-calm-accent mb-1.5">왜 문제인가요?</div>
                            <div className="text-[14.5px] leading-relaxed" style={{ wordBreak: 'keep-all' }}>{task.why}</div>
                        </div>
                    )}
                </div>

                {/* 질문·선택지가 먼저다. 근거는 길어질 수 있어서, 위로 올리면 답하러 스크롤해야 한다.
                    대신 근거 카드를 바로 아래에 붙이고, 접힌 상태에서도 눈에 띄게 만든다. */}
                {task.kind === KIND.FIX && <FixFlow task={task} onDone={() => { onChanged?.(); onBack(); }} />}
                {task.kind === KIND.JUDGE && <JudgeFlow task={task} onAck={ackAll} />}
                {task.kind === KIND.GUIDE && <GuideFlow task={task} onAck={ackAll} />}

                <Evidence task={task} />
                <AskElsewhere task={task} host={host} accounts={accounts} />
            </div>
        </div>
    );
}
