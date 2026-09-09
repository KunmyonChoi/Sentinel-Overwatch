import React, { useEffect, useState } from 'react';
import { Radar, ChevronDown, ShieldCheck, ShieldAlert, ShieldQuestion } from 'lucide-react';
import { api } from '../api';
import CopyBtn from './CopyBtn';

// 상태별 표시. '변화'가 아니라 '지금 상태'를 보여주는 패널이라 색으로 등급을 나눈다.
const STATE = {
    exposed: { cls: 'text-neon-red border-neon-red', border: '#ff0044', rank: 0 },
    unknown: { cls: 'text-yellow-400 border-yellow-500', border: '#eab308', rank: 1 },
    expected: { cls: 'text-neon-green border-neon-green/60', border: '#00ff41', rank: 2 },
    firewalled: { cls: 'text-gray-400 border-gray-600', border: '#4b5563', rank: 3 },
    loopback: { cls: 'text-gray-500 border-gray-700', border: '#374151', rank: 4 },
};

function FirewallLine({ fw }) {
    if (!fw) return null;
    if (!fw.available) {
        return (
            <div className="text-[11px] text-yellow-400 mb-2 border border-yellow-500/40 rounded px-2 py-1" style={{ wordBreak: 'keep-all' }}>
                <ShieldQuestion className="w-3 h-3 inline mr-1" />
                방화벽 상태를 읽지 못해 실제 도달 여부를 확정할 수 없습니다 — {fw.reason}
                {fw.fix_hint && <div className="text-gray-500 mt-0.5">해결: {fw.fix_hint}</div>}
            </div>
        );
    }
    const allowed = (fw.allowed || []).map(a => `${a.port}/${a.proto}`);
    return (
        <div className="text-[11px] text-gray-500 mb-2 font-mono flex flex-wrap items-center gap-x-2">
            <ShieldCheck className="w-3 h-3 text-neon-green" />
            <span className="text-gray-400">{fw.backend}{fw.active === false ? ' (비활성)' : ''}</span>
            <span>· 기본 {fw.default_incoming || '?'}</span>
            <span>· 허용 {allowed.length ? allowed.join(', ') : '없음'}</span>
        </div>
    );
}

function Row({ l }) {
    const s = STATE[l.state] || STATE.loopback;
    const fix = l.state === 'exposed'
        ? `sudo ufw delete allow ${l.port}/${l.proto}`
        : null;
    return (
        <li className="text-xs border-l-2 pl-2 py-0.5" style={{ borderColor: s.border }}>
            <div className="flex items-center gap-2 flex-wrap">
                <span className="text-white font-mono tabular-nums">{l.proto}/{l.port}</span>
                <span className="text-gray-500 font-mono text-[10px]">{l.address}</span>
                <span className={`text-[10px] px-1 rounded border ${s.cls}`}>{l.state_ko}</span>
                <span className="text-gray-400 font-mono text-[10px]">{l.process || '프로세스 미상'}</span>
                {fix && <span className="ml-auto"><CopyBtn label="방화벽 닫기" cmd={fix} /></span>}
            </div>
        </li>
    );
}

export default function ExposurePanel() {
    const [data, setData] = useState(null);
    const [showAll, setShowAll] = useState(false);

    useEffect(() => {
        let alive = true;
        const load = () => api('/api/exposure').then(d => { if (alive) setData(d); }).catch(() => {});
        load();
        const iv = setInterval(load, 60000);
        return () => { alive = false; clearInterval(iv); };
    }, []);

    if (!data) return null;
    const listeners = [...(data.listeners || [])].sort(
        (a, b) => (STATE[a.state]?.rank ?? 9) - (STATE[b.state]?.rank ?? 9) || a.port - b.port
    );
    const c = data.counts || {};
    const attention = (c.exposed || 0) + (c.unknown || 0);
    // 루프백은 대부분이고 조치 대상이 아니다. 기본은 접어둔다.
    const shown = showAll ? listeners : listeners.filter(l => l.state !== 'loopback');
    const hidden = listeners.length - shown.length;

    return (
        <div className="border border-neon-green/30 bg-cyber-black/80 backdrop-blur-sm p-4 rounded-sm neon-border text-sm">
            <h3 className="text-neon-green font-bold flex items-center gap-2 mb-2 border-b border-neon-green/30 pb-2">
                <Radar className="w-4 h-4" /> 노출 면
                <span className={`ml-auto text-xs font-normal ${attention ? 'text-neon-red' : 'text-gray-500'}`}>
                    {attention > 0
                        ? <><ShieldAlert className="w-3 h-3 inline mr-1" />조치 필요 {attention}</>
                        : `외부 바인딩 ${c.external_bind ?? 0} / 전체 ${c.total ?? 0}`}
                </span>
            </h3>

            <FirewallLine fw={data.firewall} />

            {data.health === 'degraded' && data.health_reason && !String(data.health_reason).includes('방화벽') && (
                <div className="text-[11px] text-yellow-400 mb-2" style={{ wordBreak: 'keep-all' }}>{data.health_reason}</div>
            )}

            {shown.length === 0 ? (
                <div className="text-xs text-gray-500">외부 인터페이스에 열린 포트가 없습니다.</div>
            ) : (
                <ul className="space-y-1">{shown.map(l => <Row key={`${l.proto}-${l.address}-${l.port}`} l={l} />)}</ul>
            )}

            {hidden > 0 && (
                <button onClick={() => setShowAll(true)} className="mt-2 text-xs text-gray-400 hover:text-neon-green flex items-center gap-1">
                    루프백 전용 {hidden}개 보기 <ChevronDown className="w-3 h-3" />
                </button>
            )}
            {showAll && (
                <button onClick={() => setShowAll(false)} className="mt-2 text-xs text-gray-400 hover:text-neon-green flex items-center gap-1">
                    루프백 접기 <ChevronDown className="w-3 h-3 rotate-180" />
                </button>
            )}

            <div className="text-[10px] text-gray-600 mt-2" style={{ wordBreak: 'keep-all' }}>
                바인딩 주소만으로는 노출을 알 수 없어 방화벽 규칙과 대조한 결과입니다. 의도된 공개는{' '}
                <code>SECDASH_EXPECTED_EXPOSED</code> 로 등록합니다. 컨테이너가 게시한 포트는 호스트 방화벽으로 막히지 않아 별도로 점검합니다.
            </div>
        </div>
    );
}
