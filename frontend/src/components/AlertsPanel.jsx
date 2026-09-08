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

export default function AlertsPanel({ alerts, onChanged }) {
    const [open, setOpen] = useState(new Set());
    const [showAcked, setShowAcked] = useState(true);
    const [busy, setBusy] = useState(null);

    const visible = alerts.filter(a => showAcked || a.status === 'OPEN');
    const openCount = alerts.filter(a => a.status === 'OPEN').length;

    const toggle = (id) => setOpen(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });

    const ackAll = async () => {
        const targets = visible.filter(a => a.status === 'OPEN');
        if (targets.length === 0) return;
        const note = prompt(`표시된 미확인 알림 ${targets.length}건을 모두 확인 처리합니다. 메모(선택):`, '');
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
                <span className="flex items-center gap-2"><Bell className="w-5 h-5" /> 알림 <span className="text-sm font-normal text-gray-400">(미확인 {openCount} / 진행 중 {alerts.length - openCount})</span></span>
                <span className="flex items-center gap-3 font-normal">
                    {openCount > 0 && (
                        <button onClick={ackAll} disabled={busy === 'all'} className="text-xs border border-blue-500/50 text-blue-300 hover:bg-blue-500/20 px-2 py-1 rounded flex items-center gap-1" title="표시된 미확인 알림을 모두 확인 처리">
                            <CheckSquare className="w-3 h-3" /> 모두 확인 ({visible.filter(a => a.status === 'OPEN').length})
                        </button>
                    )}
                    <label className="text-xs text-gray-500 flex items-center gap-1 cursor-pointer">
                        <input type="checkbox" checked={showAcked} onChange={(e) => setShowAcked(e.target.checked)} /> 확인된 알림 표시
                    </label>
                </span>
            </h2>
            {visible.length === 0 ? (
                <div className="text-gray-500 text-sm py-3 text-center">처리할 알림이 없습니다.</div>
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
                                                className="text-xs border border-blue-500/50 text-blue-300 hover:bg-blue-500/20 px-2 py-1 rounded flex items-center gap-1" title="확인: 인지했고 대응 중입니다. DEFCON 계산에서 제외됩니다.">
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
