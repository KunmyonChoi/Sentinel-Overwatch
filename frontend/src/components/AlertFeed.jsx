import React, { useState } from 'react';
import { AlertTriangle, Terminal, Network, Shield, ChevronDown, Skull } from 'lucide-react';

const icons = {
    'INTRUSION_ATTEMPT': AlertTriangle,
    'MALWARE_DETECTED': Shield,
    'NETWORK_ANOMALY': Network,
    'PORT_SCAN': Network,
    'NETWORK_CONN': Network,
    'RESOURCE_ANOMALY': Terminal,
    'FILE_INTEGRITY': Shield,
    'SYSTEM': Terminal,
    'PRIVILEGE_ESCALATION': AlertTriangle,
};

const EVENT_TYPE_KO = {
    'INTRUSION_ATTEMPT': '침입 시도',
    'MALWARE_DETECTED': '악성코드 탐지',
    'NETWORK_ANOMALY': '네트워크 이상',
    'PORT_SCAN': '포트 스캔',
    'NETWORK_CONN': '외부 연결',
    'RESOURCE_ANOMALY': '리소스 이상',
    'FILE_INTEGRITY': '파일 무결성',
    'SYSTEM': '시스템',
    'INVALID_USER': '유효하지 않은 사용자',
    'SUCCESSFUL_LOGIN': '로그인 성공',
    'PRIVILEGE_ESCALATION': '권한 상승',
    'SOFTWARE_UPDATE': '소프트웨어 업데이트',
};

const SEVERITY_KO = {
    'CRITICAL': '긴급',
    'WARNING': '경고',
    'INFO': '정보',
};

const FILTERS = ['ALL', 'CRITICAL', 'WARNING', 'INFO'];

function renderWithLinks(text) {
    const parts = text.split(/(https?:\/\/[^\s]+)/g);
    return parts.map((part, i) =>
        part.match(/https?:\/\//) ?
            <a key={i} href={part} target="_blank" rel="noopener noreferrer" className="text-neon-blue hover:underline underline-offset-2 break-all" onClick={(e) => e.stopPropagation()}>{part}</a> :
            part
    );
}

function groupEvents(events) {
    // events arrive newest-first; group consecutive same type+source entries
    const groups = [];
    for (const event of events) {
        const last = groups[groups.length - 1];
        if (last && last.event_type === event.event_type && last.source === event.source) {
            last.count += 1;
            last.oldest = event; // keep track of oldest for expanded view
        } else {
            // first encountered = newest; use its fields as the representative
            groups.push({ ...event, count: 1, oldest: event });
        }
    }
    return groups;
}

function extractPid(description) {
    const m = description.match(/\(PID:\s*(\d+)\)/);
    return m ? parseInt(m[1], 10) : null;
}

export default function AlertFeed({ events }) {
    const [filter, setFilter] = useState('ALL');
    const [expanded, setExpanded] = useState(new Set());
    const [copied, setCopied] = useState({}); // {pid: true}

    const copyKillCmd = (pid) => {
        navigator.clipboard.writeText(`kill -9 ${pid}`);
        setCopied(s => ({ ...s, [pid]: true }));
        setTimeout(() => setCopied(s => ({ ...s, [pid]: false })), 2000);
    };

    const feedEvents = events.filter(e => e.event_type !== 'THREAT_INTEL');
    const filtered = filter === 'ALL' ? feedEvents : feedEvents.filter(e => e.severity === filter);
    const grouped = groupEvents(filtered);

    const toggleExpand = (id) => {
        setExpanded(prev => {
            const next = new Set(prev);
            next.has(id) ? next.delete(id) : next.add(id);
            return next;
        });
    };

    return (
        <div className="h-full border border-neon-green/30 bg-cyber-black/80 backdrop-blur-sm p-4 flex flex-col rounded-sm neon-border">
            <h2 className="text-xl font-bold text-neon-green mb-3 border-b border-neon-green/30 pb-2 flex items-center justify-between">
                <span>LIVE_FEED</span>
                <span className="text-xs blink">RECEIVING_DATA...</span>
            </h2>

            {/* Filter tabs */}
            <div className="flex gap-1 mb-3">
                {FILTERS.map(f => (
                    <button
                        key={f}
                        onClick={() => setFilter(f)}
                        className={`text-xs px-2 py-1 rounded border font-mono transition-colors ${
                            filter === f
                                ? 'bg-neon-green/20 border-neon-green text-neon-green'
                                : 'border-gray-700 text-gray-500 hover:border-gray-500 hover:text-gray-300'
                        }`}
                    >
                        {f}
                        {f !== 'ALL' && (
                            <span className="ml-1 opacity-60">
                                ({feedEvents.filter(e => e.severity === f).length})
                            </span>
                        )}
                    </button>
                ))}
            </div>

            <div className="flex-1 overflow-y-auto space-y-2 pr-2 scrollbar-hide">
                {grouped.map((event) => {
                    const Icon = icons[event.event_type] || Terminal;
                    const isCritical = event.severity === 'CRITICAL';
                    const isWarning = event.severity === 'WARNING';
                    const isGrouped = event.count > 1;
                    const isOpen = expanded.has(event.id);

                    const borderColor = isCritical ? 'border-neon-red neon-border-red' :
                        isWarning ? 'border-yellow-500' : 'border-neon-green/20';
                    const textColor = isCritical ? 'text-neon-red' :
                        isWarning ? 'text-yellow-500' : 'text-neon-green';
                    const labelKo = EVENT_TYPE_KO[event.event_type];
                    const severityKo = SEVERITY_KO[event.severity];

                    return (
                        <div
                            key={event.id}
                            className={`border-l-4 ${borderColor} bg-cyber-gray/50 p-3 font-mono text-sm w-full ${isGrouped ? 'cursor-pointer hover:bg-cyber-gray' : ''} transition-colors`}
                            onClick={isGrouped ? () => toggleExpand(event.id) : undefined}
                        >
                            <div className="flex items-center justify-between mb-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                    <Icon className={`w-4 h-4 ${textColor} flex-shrink-0`} />
                                    <span className={`${textColor} font-bold`}>[{event.event_type}]</span>
                                    {labelKo && <span className={`text-xs ${textColor} opacity-70`}>{labelKo}</span>}
                                    {isGrouped && (
                                        <span className={`text-xs px-1.5 py-0.5 rounded-full border ${textColor} border-current opacity-80 flex items-center gap-1`}>
                                            ×{event.count}
                                            <ChevronDown className={`w-3 h-3 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                                        </span>
                                    )}
                                    {event.description.includes('[SIMULATION]') && (
                                        <span className="bg-blue-500/20 text-blue-400 text-[10px] px-1 rounded border border-blue-500/30">TEST DATA</span>
                                    )}
                                </div>
                                <span className="text-xs text-gray-500 flex-shrink-0">
                                    {new Date(event.timestamp + "Z").toLocaleTimeString()}
                                </span>
                            </div>
                            <div className="text-gray-300 break-words">
                                {renderWithLinks(event.description.replace('[SIMULATION]', ''))}
                            </div>
                            {event.description_ko === null ? (
                                <div className="text-gray-600 text-xs mt-1 border-t border-gray-700/50 pt-1 italic">번역 중...</div>
                            ) : event.description_ko ? (
                                <div className="text-gray-400 text-xs break-words mt-1 border-t border-gray-700/50 pt-1" style={{ wordBreak: 'keep-all' }}>
                                    {renderWithLinks(event.description_ko)}
                                </div>
                            ) : null}
                            <div className="text-xs text-gray-600 mt-1 uppercase tracking-wider flex items-center justify-between flex-wrap gap-1">
                                <span>
                                    SOURCE: {event.source} | SEVERITY: {event.severity}{severityKo ? ` (${severityKo})` : ''}
                                    {isGrouped && !isOpen && (
                                        <span className="ml-2 text-gray-500">— 클릭하여 {event.count}개 그룹 확인</span>
                                    )}
                                </span>
                                {event.event_type === 'MALWARE_DETECTED' && (() => {
                                    const pid = extractPid(event.description);
                                    if (!pid) return null;
                                    const isCopied = copied[pid];
                                    return (
                                        <button
                                            onClick={(e) => { e.stopPropagation(); copyKillCmd(pid); }}
                                            className="flex items-center gap-1 px-2 py-0.5 rounded border border-neon-red/60 text-neon-red hover:bg-neon-red/20 transition-colors font-mono normal-case"
                                        >
                                            <Skull className="w-3 h-3" />
                                            {isCopied ? 'COPIED!' : `KILL PID ${pid}`}
                                        </button>
                                    );
                                })()}
                            </div>

                            {/* Expanded group: show all but first item */}
                            {isGrouped && isOpen && (
                                <div className="mt-2 space-y-1 border-t border-gray-700/50 pt-2">
                                    {filtered
                                        .filter(e => e.event_type === event.event_type && e.source === event.source)
                                        .slice(1)
                                        .map(e => (
                                            <div key={e.id} className="text-xs text-gray-500 pl-2 border-l border-gray-700">
                                                <span className="text-gray-600 mr-2">{new Date(e.timestamp + "Z").toLocaleTimeString()}</span>
                                                {e.description.replace('[SIMULATION]', '')}
                                            </div>
                                        ))
                                    }
                                </div>
                            )}
                        </div>
                    );
                })}
                {grouped.length === 0 && (
                    <div className="text-center text-gray-600 italic py-10">
                        {filter === 'ALL' ? 'No active threats detected. Systems nominal.' : `No ${filter} events.`}
                    </div>
                )}
            </div>
        </div>
    );
}
