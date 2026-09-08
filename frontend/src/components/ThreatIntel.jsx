import React, { useEffect, useState } from 'react';
import { Globe, AlertOctagon, PackageSearch } from 'lucide-react';
import { api, fmtDateTime } from '../api';

const URGENCY = {
    CRITICAL: { badge: '필독', badgeClass: 'bg-neon-red/20 text-neon-red border border-neon-red/50', labelClass: 'text-neon-red' },
    HIGH: { badge: '중요', badgeClass: 'bg-orange-500/20 text-orange-400 border border-orange-500/50', labelClass: 'text-orange-400' },
    MEDIUM: { badgeClass: '', labelClass: 'text-yellow-500' },
    LOW: { badgeClass: '', labelClass: 'text-gray-500' },
};

function withLinks(text) {
    return String(text || '').split(/(https?:\/\/[^\s]+)/g).map((part, i) =>
        /^https?:\/\//.test(part)
            ? <a key={i} href={part} target="_blank" rel="noopener noreferrer" className="text-neon-blue hover:underline break-all">{part}</a>
            : part
    );
}

export default function ThreatIntel() {
    const [items, setItems] = useState([]);
    const [tab, setTab] = useState('all');

    useEffect(() => {
        const load = () => api('/api/intel?limit=40').then(setItems).catch(() => {});
        load();
        const id = setInterval(load, 60000);
        return () => clearInterval(id);
    }, []);

    const affects = items.filter(i => i.affects_host);
    const mustRead = items.filter(i => !i.affects_host && (i.urgency === 'CRITICAL' || i.urgency === 'HIGH'));
    const shown = tab === 'host' ? affects : tab === 'usn' ? items.filter(i => i.feed === 'usn') : tab === 'news' ? items.filter(i => i.feed !== 'usn') : items;

    return (
        <div className="border border-neon-green/30 bg-cyber-black/80 backdrop-blur-sm p-4 rounded-sm neon-border flex flex-col max-h-[520px]">
            <h3 className="text-neon-green font-bold flex items-center gap-2 mb-2 border-b border-neon-green/30 pb-2">
                <Globe className="w-4 h-4" /> 위협 인텔
                {affects.length > 0 && <span className="ml-auto text-xs text-neon-red flex items-center gap-1"><AlertOctagon className="w-3.5 h-3.5" /> 이 서버 영향 {affects.length}</span>}
            </h3>
            <div className="flex gap-1 mb-2 text-[11px]">
                {[['all', '전체'], ['host', `이 서버 영향 (${affects.length})`], ['usn', 'Ubuntu USN'], ['news', '뉴스']].map(([k, l]) => (
                    <button key={k} onClick={() => setTab(k)} className={`px-2 py-0.5 rounded border ${tab === k ? 'border-neon-green text-neon-green bg-neon-green/10' : 'border-gray-700 text-gray-500 hover:text-gray-300'}`}>{l}</button>
                ))}
            </div>
            {mustRead.length > 0 && tab === 'all' && (
                <div className="text-[11px] text-orange-300 mb-2">필독/중요 {mustRead.length}건이 있습니다.</div>
            )}
            <div className="flex-1 overflow-y-auto scrollbar-hide">
                {shown.length === 0 ? (
                    <div className="text-gray-500 text-sm py-4 text-center">표시할 항목이 없습니다.</div>
                ) : (
                    <ul className="space-y-2">
                        {shown.map((it) => {
                            const cfg = URGENCY[it.urgency] || null;
                            return (
                                <li key={it.id} className={`text-xs border-l-2 pl-2 ${it.affects_host ? 'border-neon-red' : cfg && cfg.badge ? 'border-orange-500/60' : 'border-gray-700'}`}>
                                    <div className="flex items-center gap-2 flex-wrap mb-0.5">
                                        <span className="text-[10px] text-gray-500 font-mono">{fmtDateTime(it.timestamp)}</span>
                                        <span className={`text-[10px] px-1 rounded border ${it.feed === 'usn' ? 'border-blue-500/40 text-blue-300' : 'border-gray-700 text-gray-500'}`}>{it.feed === 'usn' ? 'USN' : 'NEWS'}</span>
                                        {it.affects_host && <span className="text-[10px] px-1 rounded bg-neon-red/20 text-neon-red border border-neon-red/50 flex items-center gap-1"><PackageSearch className="w-3 h-3" /> 이 서버 영향</span>}
                                        {cfg && cfg.badge && !it.affects_host && <span className={`text-[10px] px-1 rounded ${cfg.badgeClass}`}>{cfg.badge}</span>}
                                        {it.urgency && <span className={`text-[10px] ml-auto font-mono ${cfg ? cfg.labelClass : 'text-gray-500'}`}>{it.urgency}</span>}
                                    </div>
                                    <div className="text-gray-200">
                                        {it.link ? <a href={it.link} target="_blank" rel="noopener noreferrer" className="hover:text-neon-blue hover:underline">{it.title}</a> : it.title}
                                    </div>
                                    {it.affected?.length > 0 && (
                                        <div className="text-[11px] text-neon-red/90 font-mono mt-0.5">
                                            {it.affected.slice(0, 4).map(a => `${a.package} ${a.installed} → ${a.fixed}`).join(', ')}{it.affected.length > 4 ? ' …' : ''}
                                        </div>
                                    )}
                                    {it.description_ko === null ? (
                                        <div className="text-gray-600 italic mt-0.5">번역 중...</div>
                                    ) : it.description_ko ? (
                                        <div className="text-gray-400 mt-0.5" style={{ wordBreak: 'keep-all' }}>{withLinks(it.description_ko)}</div>
                                    ) : null}
                                </li>
                            );
                        })}
                    </ul>
                )}
            </div>
            <div className="mt-2 text-[10px] text-gray-600 border-t border-gray-800 pt-2">출처: 보안 뉴스 RSS · Ubuntu Security Notices (설치 패키지와 로컬 대조)</div>
        </div>
    );
}
