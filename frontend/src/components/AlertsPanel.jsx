import React, { useState } from 'react';
import { Bell, Check, CheckCheck, CheckSquare, ChevronDown, ClipboardCopy } from 'lucide-react';
import { api, fmtDateTime } from '../api';

const SEV = {
    CRITICAL: { label: '긴급', border: 'border-neon-red neon-border-red', text: 'text-neon-red' },
    WARNING: { label: '경고', border: 'border-yellow-500', text: 'text-yellow-400' },
    INFO: { label: '정보', border: 'border-neon-green/30', text: 'text-neon-green' },
};

function CopyButton({ text }) {
    const [ok, setOk] = useState(false);
    return (
        <button
            onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(text); setOk(true); setTimeout(() => setOk(false), 1500); }}
            className="text-gray-500 hover:text-neon-green" title="복사"
        >
            {ok ? <Check className="w-3.5 h-3.5 text-neon-green" /> : <ClipboardCopy className="w-3.5 h-3.5" />}
        </button>
    );
}

export default function AlertsPanel({ alerts, counts = null, limit = 0, onLoadMore, onChanged }) {
    const [open, setOpen] = useState(new Set());
    const [showAcked, setShowAcked] = useState(true);
    const [busy, setBusy] = useState(null);

    const visible = alerts.filter(a => showAcked || a.status === 'OPEN');

    // 머리글 숫자는 서버가 센 전체 건수(/api/alerts/count)다. 불러온 행을 세면 목록이 limit 에서
    // 잘리는 순간 시스템 상태 패널과 다른 숫자를 말하게 된다 — 같은 사실인데 숫자가 둘이 된다.
    // counts 가 아직 없는 첫 렌더에서만 불러온 행으로 대신한다.
    const fetchedOpen = alerts.filter(a => a.status === 'OPEN').length;
    const openCount = counts ? counts.open : fetchedOpen;
    const ackedCount = counts ? counts.acked : alerts.length - fetchedOpen;
    const simCount = counts ? counts.simulation : alerts.filter(a => a.is_simulation).length;

    // 지금 걸린 필터에서 '전부'는 몇 건인가. 확인된 알림을 숨기면 미확인 건수가 기준이 된다.
    const trueTotal = showAcked ? openCount + ackedCount : openCount;
    const hidden = Math.max(0, trueTotal - visible.length);
    const maxLimit = counts?.max_limit ?? 0;
    const canLoadMore = !!onLoadMore && limit > 0 && limit < maxLimit;

    // '모두 확인' 이 실제로 손댈 행. 목록이 잘렸으면 미확인 알림이 화면 밖에 있을 수 있으므로
    // 버튼이 말하는 숫자와 실제로 처리하는 숫자가 반드시 같아야 한다.
    const ackTargets = visible.filter(a => a.status === 'OPEN');

    const toggle = (id) => setOpen(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });

    const ackAll = async () => {
        const targets = ackTargets;
        if (targets.length === 0) return;
        const unseen = Math.max(0, openCount - targets.length);
        const note = prompt(
            `지금 화면에 있는 미확인 알림 ${targets.length}건을 확인 처리합니다.`
            + (unseen > 0 ? `\n미확인은 모두 ${openCount}건입니다. 아직 불러오지 않은 ${unseen}건은 그대로 남습니다 — "더 보기"로 불러온 뒤 다시 누르세요.` : '')
            + `\n같은 알림이 다시 생겨도 심각도가 오르지 않는 한 다시 알리지 않습니다.\n메모(선택):`, '');
        if (note === null) return;
        setBusy('all');
        try {
            await api('/api/alerts/ack-all', { method: 'POST', body: { by: 'dashboard', note, ids: targets.map(a => a.id) } });
            onChanged && onChanged();
        } catch (e) {
            alert(`처리 실패: ${e.message}`);
        } finally {
            setBusy(null);
        }
    };

    const act = async (a, action) => {
        let note = '';
        if (action === 'resolve') {
            note = prompt(`알림 "${a.title_ko || a.title}" 을(를) 해결 처리합니다. 메모(선택):`, '');
            if (note === null) return;
        }
        setBusy(a.id);
        try {
            await api(`/api/alerts/${a.id}/${action}`, { method: 'POST', body: { by: 'dashboard', note } });
            onChanged && onChanged();
        } catch (e) {
            alert(`처리 실패: ${e.message}`);
        } finally {
            setBusy(null);
        }
    };

    return (
        <div className="border border-neon-green/30 bg-cyber-black/80 backdrop-blur-sm p-4 rounded-sm neon-border">
            <h2 className="text-xl font-bold text-neon-green mb-3 border-b border-neon-green/30 pb-2 flex items-center justify-between">
                <span className="flex items-center gap-2"><Bell className="w-5 h-5" /> 알림 <span
                    className="text-sm font-normal text-gray-400"
                    title={`서버가 센 전체 건수입니다 (화면에 불러온 ${alerts.length}건이 아니라 DB 전체).`
                        + (simCount > 0 ? ` 테스트 데이터 ${simCount}건이 포함되어 있습니다 — 시스템 상태 패널의 숫자는 테스트를 제외합니다.` : '')}
                >(미확인 {openCount} / 진행 중 {ackedCount})</span></span>
                <span className="flex items-center gap-3 font-normal">
                    {ackTargets.length > 0 && (
                        <button onClick={ackAll} disabled={busy === 'all'} className="text-xs border border-blue-500/50 text-blue-300 hover:bg-blue-500/20 px-2 py-1 rounded flex items-center gap-1"
                            title={`지금 화면에 있는 미확인 알림 ${ackTargets.length}건만 확인 처리합니다`
                                + (openCount > ackTargets.length ? ` (미확인 전체 ${openCount}건 중 나머지는 아직 불러오지 않았습니다)` : '')}>
                            <CheckSquare className="w-3 h-3" /> 모두 확인 ({ackTargets.length})
                        </button>
                    )}
                    <label className="text-xs text-gray-500 flex items-center gap-1 cursor-pointer">
                        <input type="checkbox" checked={showAcked} onChange={(e) => setShowAcked(e.target.checked)} /> 확인된 알림 표시
                    </label>
                </span>
            </h2>
            {/* 잘린 목록은 완전해 보인다 — 그게 조용한 실패다. 몇 건을 못 보고 있는지 말해 준다. */}
            {hidden > 0 && (
                <div className="mb-2 flex items-center justify-between gap-2 border border-yellow-600/40 bg-yellow-900/10 px-2 py-1.5 rounded text-[11px] text-yellow-200">
                    <span style={{ wordBreak: 'keep-all' }}>
                        {showAcked ? `전체 ${trueTotal}건 중 ${visible.length}건 표시` : `미확인 ${trueTotal}건 중 ${visible.length}건 표시`}
                        {' · '}나머지 {hidden}건은 아직 불러오지 않았습니다
                    </span>
                    {canLoadMore ? (
                        <button onClick={onLoadMore} className="flex-shrink-0 border border-yellow-500/60 text-yellow-200 hover:bg-yellow-500/20 px-2 py-0.5 rounded">더 보기</button>
                    ) : (
                        <span className="flex-shrink-0 text-yellow-500/80">한 번에 최대 {maxLimit || visible.length}건까지 보냅니다</span>
                    )}
                </div>
            )}
            {visible.length === 0 ? (
                <div className="text-gray-500 text-sm py-3 text-center">
                    {hidden > 0 ? '불러온 범위에는 알림이 없습니다. 위의 "더 보기"를 눌러 주세요.' : '처리할 알림이 없습니다.'}
                </div>
            ) : (
                <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1 scrollbar-hide">
                    {visible.map(a => {
                        const s = SEV[a.severity] || SEV.INFO;
                        const isOpen = open.has(a.id);
                        const acked = a.status === 'ACKED';
                        return (
                            <div key={a.id} className={`border-l-4 ${s.border} bg-cyber-gray/60 p-3 text-sm ${acked ? 'opacity-70' : ''}`}>
                                <div className="flex items-start justify-between gap-2 cursor-pointer" onClick={() => toggle(a.id)}>
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <span className={`${s.text} font-bold text-xs`}>[{s.label}]</span>
                                            {a.count > 1 && <span className={`text-[10px] px-1.5 rounded-full border ${s.text} border-current`}>×{a.count}</span>}
                                            {acked && <span className="text-[10px] px-1 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30">확인됨 · {a.acked_by}</span>}
                                            {/* 쉬운 화면에서 사용자가 답한 것. 심각도만 올라가고 이유가 안 보이면 판단할 수 없다. */}
                                            {a.details?.user_response === 'not_me' && (
                                                <span className="text-[10px] px-1 rounded bg-neon-red/20 text-neon-red border border-neon-red/40"
                                                    title={`사용자가 본인이 한 일이 아니라고 답했습니다 (${a.details.user_response_at || ''})`}>
                                                    사용자: 내가 한 일 아님
                                                </span>
                                            )}
                                            {a.details?.user_response === 'unsure' && (
                                                <span className="text-[10px] px-1 rounded bg-yellow-500/20 text-yellow-300 border border-yellow-500/40"
                                                    title={`사용자가 판단을 보류했습니다 (${a.details.user_response_at || ''})`}>
                                                    사용자: 확인 중
                                                </span>
                                            )}
                                            {a.details?.user_response === 'mine' && (
                                                <span className="text-[10px] px-1 rounded bg-gray-700/40 text-gray-400 border border-gray-600"
                                                    title={`사용자가 본인이 한 일이라고 확인했습니다 (${a.details.user_response_at || ''})`}>
                                                    사용자: 본인 확인
                                                </span>
                                            )}
                                            {a.details?.package && <span className="text-[10px] px-1 rounded bg-gray-700/40 text-gray-400 border border-gray-600">패키지 {a.details.package}</span>}
                                            {a.is_simulation && <span className="text-[10px] px-1 rounded bg-blue-500/20 text-blue-400 border border-blue-500/30">TEST DATA</span>}
                                            <span className="text-[10px] text-gray-500 font-mono">{a.rule}</span>
                                        </div>
                                        <div className="text-gray-100 mt-1" style={{ wordBreak: 'keep-all' }}>{a.title_ko || a.title}</div>
                                        <div className="text-[11px] text-gray-500 mt-0.5">최근 {fmtDateTime(a.last_seen_at)}{a.count > 1 ? ` · 최초 ${fmtDateTime(a.created_at)}` : ''}</div>
                                    </div>
                                    <div className="flex items-center gap-1 flex-shrink-0">
                                        {!acked && (
                                            <button disabled={busy === a.id} onClick={(e) => { e.stopPropagation(); act(a, 'ack'); }}
                                                className="text-xs border border-blue-500/50 text-blue-300 hover:bg-blue-500/20 px-2 py-1 rounded flex items-center gap-1" title="확인: 인지했고 대응 중입니다. DEFCON 계산에서 빠지고, 같은 알림이 다시 생겨도 심각도가 올라가지 않는 한 다시 알리지 않습니다.">
                                                <Check className="w-3 h-3" /> 확인
                                            </button>
                                        )}
                                        <button disabled={busy === a.id} onClick={(e) => { e.stopPropagation(); act(a, 'resolve'); }}
                                            className="text-xs border border-neon-green/50 text-neon-green hover:bg-neon-green/20 px-2 py-1 rounded flex items-center gap-1" title="해결: 조치 완료 또는 오탐">
                                            <CheckCheck className="w-3 h-3" /> 해결
                                        </button>
                                        <ChevronDown className={`w-4 h-4 text-gray-500 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                                    </div>
                                </div>
                                {isOpen && (
                                    <div className="mt-2 pt-2 border-t border-gray-700/60 space-y-2">
                                        {a.summary_ko && <div className="text-gray-300 text-xs" style={{ wordBreak: 'keep-all' }}>{a.summary_ko}</div>}
                                        {a.action_ko && (
                                            <div className="bg-neon-green/5 border border-neon-green/30 rounded p-2 text-xs">
                                                <div className="flex items-center justify-between mb-1">
                                                    <span className="text-neon-green font-bold">지금 할 일</span>
                                                    <CopyButton text={a.action_ko} />
                                                </div>
                                                <div className="text-gray-200" style={{ wordBreak: 'keep-all' }}>{a.action_ko}</div>
                                            </div>
                                        )}
                                        {a.evidence && (
                                            <div>
                                                <div className="flex items-center justify-between text-[10px] text-gray-500 mb-1"><span>근거</span><CopyButton text={a.evidence} /></div>
                                                <pre className="text-[11px] text-gray-400 bg-black/40 p-2 rounded overflow-x-auto max-h-48 whitespace-pre-wrap break-all">{a.evidence}</pre>
                                            </div>
                                        )}
                                        <div className="text-[10px] text-gray-600 font-mono break-all">{a.title}</div>
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
