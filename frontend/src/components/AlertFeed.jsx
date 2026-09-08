import React, { useState } from 'react';
import { AlertTriangle, Terminal, Network, Shield, ChevronDown, Check, ClipboardCopy, KeyRound, Package, User, Cpu } from 'lucide-react';
import { fmtTime } from '../api';

const ICONS = {
    AUTH_FAILURE: AlertTriangle, INVALID_USER: AlertTriangle, AUTH_SUCCESS: KeyRound, SUDO_COMMAND: Terminal, SUDO_FAILURE: AlertTriangle,
    ROOT_SESSION: User, ACCOUNT_CHANGE: User, IP_BLOCKED: Shield, IP_UNBLOCKED: Shield, IP_BLOCK_RECOMMENDED: Shield,
    NETWORK_LISTENER: Network, NETWORK_CONN: Network, PORT_SCAN: Network, PROCESS_TOOL: Cpu, PROCESS_INDICATOR: Cpu,
    FILE_INTEGRITY: Shield, PERSISTENCE: Shield, RESOURCE_ANOMALY: Cpu, SOFTWARE_UPDATE: Package, PENDING_UPDATES: Package,
};
const SEVERITY_KO = { CRITICAL: '긴급', WARNING: '경고', INFO: '정보' };
const FILTERS = ['ALL', 'CRITICAL', 'WARNING', 'INFO'];

function groupEvents(events) {
    const groups = [];
    for (const ev of events) {
        const last = groups[groups.length - 1];
        if (last && last.event_type === ev.event_type && last.severity === ev.severity && last.source === ev.source) {
            last.count += 1; last.items.push(ev);
        } else {
            groups.push({ ...ev, count: 1, items: [ev] });
        }
    }
    return groups;
}

export default function AlertFeed({ events }) {
    const [filter, setFilter] = useState('ALL');
    const [hideSim, setHideSim] = useState(false);
    const [expanded, setExpanded] = useState(new Set());
    const [copied, setCopied] = useState(null);

    const copy = (key, text) => { navigator.clipboard.writeText(text); setCopied(key); setTimeout(() => setCopied(null), 1500); };

    const base = events.filter(e => e.event_type !== 'THREAT_INTEL' && (!hideSim || !e.is_simulation));
    const filtered = filter === 'ALL' ? base : base.filter(e => e.severity === filter);
    const grouped = groupEvents(filtered);
    const toggle = (id) => setExpanded(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });

    const renderRow = (ev, compact = false) => {
        const d = ev.details || {};
        const pid = d.pid;
        return (
            <div className={compact ? 'py-1 border-b border-gray-800 last:border-0' : ''}>
                <div className="text-gray-100" style={{ wordBreak: 'keep-all' }}>{ev.description_ko || ev.description}</div>
                {ev.description_ko && <div className="text-[11px] text-gray-500 break-all mt-0.5">{ev.description}</div>}
                {d.command && ev.event_type === 'IP_BLOCK_RECOMMENDED' && (
                    <button onClick={(e) => { e.stopPropagation(); copy(`cmd${ev.id}`, d.command); }} className="mt-1 text-[11px] text-yellow-400 border border-yellow-600/50 px-1.5 py-0.5 rounded hover:bg-yellow-500/10 flex items-center gap-1">
                        {copied === `cmd${ev.id}` ? <Check className="w-3 h-3" /> : <ClipboardCopy className="w-3 h-3" />} 차단 명령 복사
                    </button>
                )}
                {pid && (ev.event_type === 'PROCESS_TOOL' || ev.event_type === 'PROCESS_INDICATOR') && (
                    <button onClick={(e) => { e.stopPropagation(); copy(`kill${ev.id}`, `sudo kill -9 ${pid}`); }} className="mt-1 text-[11px] text-neon-red border border-neon-red/50 px-1.5 py-0.5 rounded hover:bg-neon-red/10 flex items-center gap-1">
                        {copied === `kill${ev.id}` ? <Check className="w-3 h-3" /> : <ClipboardCopy className="w-3 h-3" />} kill -9 {pid} 복사
                    </button>
                )}
            </div>
        );
    };

    return (
        <div className="h-full border border-neon-green/30 bg-cyber-black/80 backdrop-blur-sm p-4 flex flex-col rounded-sm neon-border min-h-[400px]">
            <h2 className="text-xl font-bold text-neon-green mb-3 border-b border-neon-green/30 pb-2 flex items-center justify-between">
                <span>라이브 피드 <span className="text-xs text-gray-500 font-normal">원시 이벤트</span></span>
                <label className="text-xs text-gray-500 font-normal flex items-center gap-1 cursor-pointer"><input type="checkbox" checked={hideSim} onChange={e => setHideSim(e.target.checked)} /> 시뮬레이션 숨김</label>
            </h2>
            <div className="flex gap-1 mb-3">
                {FILTERS.map(f => (
                    <button key={f} onClick={() => setFilter(f)} className={`text-xs px-2 py-1 rounded border font-mono ${filter === f ? 'bg-neon-green/20 border-neon-green text-neon-green' : 'border-gray-700 text-gray-500 hover:border-gray-500 hover:text-gray-300'}`}>
                        {f === 'ALL' ? '전체' : SEVERITY_KO[f]}{f !== 'ALL' && <span className="ml-1 opacity-60">({base.filter(e => e.severity === f).length})</span>}
                    </button>
                ))}
            </div>
            <div className="flex-1 overflow-y-auto space-y-2 pr-2 scrollbar-hide max-h-[70vh]">
                {grouped.length === 0 && <div className="text-gray-600 text-sm text-center py-6">이벤트가 없습니다.</div>}
                {grouped.map((ev) => {
                    const Icon = ICONS[ev.event_type] || Terminal;
                    const isCritical = ev.severity === 'CRITICAL';
                    const isWarning = ev.severity === 'WARNING';
                    const isGrouped = ev.count > 1;
                    const isOpen = expanded.has(ev.id);
                    const border = isCritical ? 'border-neon-red' : isWarning ? 'border-yellow-500' : 'border-neon-green/20';
                    const color = isCritical ? 'text-neon-red' : isWarning ? 'text-yellow-500' : 'text-neon-green';
                    return (
                        <div key={ev.id} className={`border-l-4 ${border} bg-cyber-gray/50 p-3 font-mono text-sm w-full ${isGrouped ? 'cursor-pointer hover:bg-cyber-gray' : ''}`} onClick={isGrouped ? () => toggle(ev.id) : undefined}>
                            <div className="flex items-center justify-between mb-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                    <Icon className={`w-4 h-4 ${color} flex-shrink-0`} />
                                    <span className={`${color} font-bold`}>{ev.event_type_ko || ev.event_type}</span>
                                    <span className={`text-[10px] ${color} opacity-60`}>{SEVERITY_KO[ev.severity] || ev.severity}</span>
                                    {isGrouped && <span className={`text-xs px-1.5 py-0.5 rounded-full border ${color} border-current opacity-80 flex items-center gap-1`}>×{ev.count}<ChevronDown className={`w-3 h-3 transition-transform ${isOpen ? 'rotate-180' : ''}`} /></span>}
                                    {ev.is_simulation && <span className="bg-blue-500/20 text-blue-400 text-[10px] px-1 rounded border border-blue-500/30">TEST DATA</span>}
                                </div>
                                <span className="text-xs text-gray-500">{fmtTime(ev.timestamp)}</span>
                            </div>
                            {renderRow(ev)}
                            {isGrouped && isOpen && (
                                <div className="mt-2 pt-2 border-t border-gray-700 text-xs text-gray-400">
                                    {ev.items.slice(1).map(e => <div key={e.id} className="flex gap-2"><span className="text-gray-600 flex-shrink-0">{fmtTime(e.timestamp)}</span>{renderRow(e, true)}</div>)}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
