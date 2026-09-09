import React, { useEffect, useState } from 'react';
import { api } from '../api';
import { Icon, Card, Btn, BackLink, BeforeAfter, StatusHead } from './ui';
import { TONE, toneOf } from './tokens';
import { KIND, JUDGE_STEPS } from './tasks';

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
            <div className="flex items-center gap-2.5 mt-3 flex-wrap">
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

export default function TaskDetail({ task, onBack, onChanged }) {
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

                {task.kind === KIND.FIX && <FixFlow task={task} onDone={() => { onChanged?.(); onBack(); }} />}
                {task.kind === KIND.JUDGE && <JudgeFlow task={task} onAck={ackAll} />}
                {task.kind === KIND.GUIDE && <GuideFlow task={task} onAck={ackAll} />}

                {/* 근거: 지킴이가 실제로 본 것 */}
                <details className="mt-8 group">
                    <summary className="cursor-pointer text-[13.5px] text-calm-muted inline-flex items-center gap-1.5 select-none h-11">
                        <Icon name="down" size={15} className="group-open:rotate-180 transition-transform" />
                        지킴이가 본 것 {task.count > 1 ? `${task.count}건` : ''}
                    </summary>
                    <div className="mt-2 grid gap-2">
                        {task.alerts.map((a) => (
                            <Card key={a.id} className="p-4">
                                <div className="text-[13.5px] font-medium">{a.title_ko || a.title}</div>
                                {a.summary_ko && <div className="text-[13px] text-calm-muted mt-1" style={{ wordBreak: 'keep-all' }}>{a.summary_ko}</div>}
                                {a.evidence && <div className="text-[12px] text-calm-muted mt-1.5 font-mono break-all">{a.evidence}</div>}
                            </Card>
                        ))}
                    </div>
                </details>
            </div>
        </div>
    );
}
