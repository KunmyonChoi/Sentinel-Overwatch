import React, { useEffect, useState } from 'react';
import { ClipboardCheck, ChevronDown, MessageSquareShare, Check } from 'lucide-react';
import { api } from '../api';

function CopyBrief({ item, label, title }) {
    const [state, setState] = useState('idle');
    const copy = async () => {
        setState('busy');
        try {
            const r = await api(`/api/hardening/brief${item ? `?item=${encodeURIComponent(item)}` : ''}`);
            await navigator.clipboard.writeText(r.markdown);
            setState('ok');
        } catch { setState('err'); }
        setTimeout(() => setState('idle'), 1800);
    };
    return (
        <button onClick={copy} disabled={state === 'busy'} title={title}
            className={`text-[10px] px-1.5 py-0.5 rounded border flex items-center gap-1 ${state === 'ok' ? 'border-neon-green text-neon-green' : state === 'err' ? 'border-neon-red text-neon-red' : 'border-gray-700 text-gray-400 hover:border-neon-green hover:text-neon-green'}`}>
            {state === 'ok' ? <Check className="w-3 h-3" /> : <MessageSquareShare className="w-3 h-3" />}
            {state === 'ok' ? '복사됨' : state === 'err' ? '실패' : label}
        </button>
    );
}

export default function HardeningPanel() {
    const [data, setData] = useState(null);
    const [showSuggestions, setShowSuggestions] = useState(false);

    useEffect(() => {
        let alive = true;
        const load = () => api('/api/hardening').then(d => { if (alive) setData(d); }).catch(() => {});
        load();
        const iv = setInterval(load, 60000);
        return () => { alive = false; clearInterval(iv); };
    }, []);

    if (!data) return null;
    const idx = data.hardening_index ?? 0;
    const color = idx >= 75 ? 'text-neon-green' : idx >= 60 ? 'text-yellow-400' : 'text-neon-red';
    const warnings = data.warnings || [];
    const suggestions = data.suggestions || [];

    return (
        <div className="border border-neon-green/30 bg-cyber-black/80 backdrop-blur-sm p-4 rounded-sm neon-border text-sm">
            <h3 className="text-neon-green font-bold flex items-center gap-2 mb-2 border-b border-neon-green/30 pb-2">
                <ClipboardCheck className="w-4 h-4" /> 강화 작업 목록 (Lynis)
                {data.available && <span className={`ml-auto font-mono text-lg ${color}`}>{idx}<span className="text-xs text-gray-500">/100</span></span>}
            </h3>
            {!data.available ? (
                <div className="text-xs text-gray-400" style={{ wordBreak: 'keep-all' }}>
                    <div className="text-yellow-400">{data.health_reason || '감사 결과가 아직 없습니다.'}</div>
                    {data.fix_hint && <div className="text-gray-500 mt-1">해결: {data.fix_hint}</div>}
                </div>
            ) : (
                <>
                    <div className="flex items-center justify-between gap-2 mb-2">
                        <div className="text-[11px] text-gray-500 font-mono">최근 감사 {data.started} · Lynis {data.lynis_version}</div>
                        <CopyBrief label="Claude 에 붙여넣기용 복사" title="호스트 역할, 지수, 경고·제안 상세, 이미 건너뛴 항목과 분류 요청 문구를 마크다운으로 복사합니다" />
                    </div>
                    {warnings.length > 0 ? (
                        <ul className="space-y-1 mb-2">
                            {warnings.map(w => (
                                <li key={w.id} className="text-xs border-l-2 border-yellow-500 pl-2" style={{ wordBreak: 'keep-all' }}>
                                    <span className="text-yellow-400 font-mono">{w.id}</span> <span className="text-gray-200">{w.message}</span> <CopyBrief item={w.id} label="복사" title="이 항목만 붙여넣기용으로 복사" />
                                    {w.solution && <div className="text-gray-500">{w.solution}</div>}
                                </li>
                            ))}
                        </ul>
                    ) : <div className="text-xs text-gray-500 mb-2">경고 없음</div>}
                    <button onClick={() => setShowSuggestions(s => !s)} className="text-xs text-gray-400 hover:text-neon-green flex items-center gap-1">
                        강화 제안 {suggestions.length}건 <ChevronDown className={`w-3 h-3 transition-transform ${showSuggestions ? 'rotate-180' : ''}`} />
                    </button>
                    {showSuggestions && (
                        <ul className="mt-2 space-y-1 max-h-64 overflow-y-auto scrollbar-hide">
                            {suggestions.map((s, i) => (
                                <li key={`${s.id}-${i}`} className="text-[11px] border-l-2 border-gray-700 pl-2" style={{ wordBreak: 'keep-all' }}>
                                    <span className="text-gray-500 font-mono">{s.id}</span> <span className="text-gray-300">{s.message}</span> <CopyBrief item={s.id} label="복사" title="이 항목만 붙여넣기용으로 복사" />
                                    {s.details && <div className="text-gray-600">{s.details}</div>}
                                </li>
                            ))}
                        </ul>
                    )}
                    <div className="text-[10px] text-gray-600 mt-2">제안은 알림이 아닙니다. 새 경고와 지수 하락만 알림으로 올라옵니다. 결정한 항목은 <code>deploy/lynis-custom.prf</code> 에 skip-test 로 기록하세요. 상세: <code>sudo lynis show details &lt;ID&gt;</code></div>
                </>
            )}
        </div>
    );
}
