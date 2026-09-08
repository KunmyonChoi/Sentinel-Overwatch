import React, { useEffect, useState } from 'react';
import { ClipboardCheck, ChevronDown } from 'lucide-react';
import { api } from '../api';

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
                    <div className="text-[11px] text-gray-500 font-mono mb-2">최근 감사 {data.started} · Lynis {data.lynis_version}</div>
                    {warnings.length > 0 ? (
                        <ul className="space-y-1 mb-2">
                            {warnings.map(w => (
                                <li key={w.id} className="text-xs border-l-2 border-yellow-500 pl-2" style={{ wordBreak: 'keep-all' }}>
                                    <span className="text-yellow-400 font-mono">{w.id}</span> <span className="text-gray-200">{w.message}</span>
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
                                    <span className="text-gray-500 font-mono">{s.id}</span> <span className="text-gray-300">{s.message}</span>
                                    {s.details && <div className="text-gray-600">{s.details}</div>}
                                </li>
                            ))}
                        </ul>
                    )}
                    <div className="text-[10px] text-gray-600 mt-2">제안은 알림이 아닙니다. 새 경고와 지수 하락만 알림으로 올라옵니다. 상세: <code>sudo lynis show details &lt;ID&gt;</code></div>
                </>
            )}
        </div>
    );
}
