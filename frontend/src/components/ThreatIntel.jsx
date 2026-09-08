import React, { useEffect, useState } from 'react';
import { Globe, AlertTriangle, Flame, Info, ShieldAlert } from 'lucide-react';

const URGENCY_CONFIG = {
    CRITICAL: {
        icon: <Flame className="w-3.5 h-3.5" />,
        badge: '필독',
        badgeClass: 'bg-red-600 text-white animate-pulse',
        borderClass: 'border-red-600/60',
        labelClass: 'text-red-400',
    },
    HIGH: {
        icon: <AlertTriangle className="w-3.5 h-3.5" />,
        badge: '주목',
        badgeClass: 'bg-orange-500 text-white',
        borderClass: 'border-orange-500/40',
        labelClass: 'text-orange-400',
    },
    MEDIUM: {
        icon: <ShieldAlert className="w-3.5 h-3.5" />,
        badge: null,
        badgeClass: '',
        borderClass: 'border-yellow-600/20',
        labelClass: 'text-yellow-500',
    },
    LOW: {
        icon: <Info className="w-3.5 h-3.5" />,
        badge: null,
        badgeClass: '',
        borderClass: 'border-gray-800',
        labelClass: 'text-gray-500',
    },
};

function renderWithLinks(text) {
    const parts = text.split(/(https?:\/\/[^\s]+)/g);
    return parts.map((part, i) =>
        part.match(/https?:\/\//) ?
            <a key={i} href={part} target="_blank" rel="noopener noreferrer" className="text-neon-blue hover:underline underline-offset-2" onClick={(e) => e.stopPropagation()}>{part}</a> :
            part
    );
}

export default function ThreatIntel() {
    const [intelEvents, setIntelEvents] = useState([]);

    useEffect(() => {
        const fetch_ = async () => {
            try {
                const res = await fetch('http://localhost:8000/api/intel');
                if (res.ok) setIntelEvents(await res.json());
            } catch (e) {
                console.error("Failed to fetch intel", e);
            }
        };
        fetch_();
        const id = setInterval(fetch_, 60000);
        return () => clearInterval(id);
    }, []);

    const mustReads = intelEvents.filter(e => e.urgency === 'CRITICAL' || e.urgency === 'HIGH');

    return (
        <div className="flex-1 border border-neon-green/30 bg-cyber-black/80 backdrop-blur-sm p-4 neon-border mt-4 md:mt-0 flex flex-col min-h-[200px]">
            <h2 className="text-xl font-bold text-neon-green mb-4 border-b border-neon-green/30 pb-2 flex items-center gap-2">
                <Globe className="w-5 h-5" />
                <span>THREAT_INTEL</span>
                {mustReads.length > 0 && (
                    <span className="text-xs bg-red-600 text-white px-1.5 py-0.5 rounded animate-pulse font-bold">
                        필독 {mustReads.length}건
                    </span>
                )}
                <span className="text-xs text-gray-500 font-normal ml-auto">{intelEvents.length}건</span>
            </h2>
            <div className="flex-1 overflow-y-auto pr-1 scrollbar-hide">
                {intelEvents.length > 0 ? (
                    <ul className="space-y-3">
                        {intelEvents.map(event => {
                            const cfg = URGENCY_CONFIG[event.urgency] || null;
                            return (
                                <li key={event.id} className={`text-sm border-b pb-2 last:border-0 ${cfg ? cfg.borderClass : 'border-gray-800'}`}>
                                    <div className="flex items-center gap-1.5 mb-1">
                                        {cfg && (
                                            <span className={`flex items-center gap-0.5 ${cfg.labelClass}`}>
                                                {cfg.icon}
                                            </span>
                                        )}
                                        <span className="text-neon-blue font-bold text-xs">
                                            {new Date(event.timestamp + "Z").toLocaleDateString()}
                                        </span>
                                        {cfg?.badge && (
                                            <span className={`text-xs px-1.5 py-0.5 rounded font-bold ${cfg.badgeClass}`}>
                                                {cfg.badge}
                                            </span>
                                        )}
                                        {event.urgency && (
                                            <span className={`text-xs font-mono ml-auto ${cfg ? cfg.labelClass : 'text-gray-500'}`}>
                                                {event.urgency}
                                            </span>
                                        )}
                                    </div>
                                    <div className="text-gray-300 break-words line-clamp-2 hover:line-clamp-none">
                                        {renderWithLinks(event.description)}
                                    </div>
                                    {event.description_ko === null ? (
                                        <div className="text-gray-600 text-xs mt-1 pt-1 border-t border-gray-700/50 italic">번역 중...</div>
                                    ) : event.description_ko ? (
                                        <div className="text-gray-400 text-xs break-words mt-1 pt-1 border-t border-gray-700/50" style={{ wordBreak: 'keep-all' }}>
                                            {renderWithLinks(event.description_ko)}
                                        </div>
                                    ) : null}
                                </li>
                            );
                        })}
                    </ul>
                ) : (
                    <div className="flex items-center justify-center h-full text-gray-500 text-sm">
                        <p>No recent threat intelligence updates.</p>
                    </div>
                )}
            </div>
            <div className="mt-2 text-xs text-gray-600 border-t border-gray-800 pt-2">
                SOURCE: THE HACKER NEWS (RSS)
            </div>
        </div>
    );
}
