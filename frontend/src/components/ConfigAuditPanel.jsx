import React, { useEffect, useState } from 'react';
import { FileWarning, Boxes, Check } from 'lucide-react';
import { api } from '../api';
import CopyBtn from './CopyBtn';

const SEV = {
    CRITICAL: { cls: 'text-neon-red border-neon-red', border: '#ff0044' },
    WARNING: { cls: 'text-yellow-400 border-yellow-500', border: '#eab308' },
    INFO: { cls: 'text-gray-400 border-gray-600', border: '#4b5563' },
};

function Unavailable({ reason, hint }) {
    if (!reason) return null;
    return (
        <div className="text-[11px] text-gray-500" style={{ wordBreak: 'keep-all' }}>
            {reason}
            {hint && <div className="text-gray-600 mt-0.5">{hint}</div>}
        </div>
    );
}

function PermissionRows({ data }) {
    const rows = data?.findings || [];
    if (!rows.length) {
        return <div className="text-[11px] text-gray-500 flex items-center gap-1"><Check className="w-3 h-3 text-neon-green" />world-writable 설정 파일·노출된 시크릿 없음</div>;
    }
    return (
        <ul className="space-y-1">
            {rows.map(f => {
                const s = SEV[f.severity] || SEV.INFO;
                return (
                    <li key={f.path} className="text-xs border-l-2 pl-2 py-0.5" style={{ borderColor: s.border }}>
                        <div className="flex items-center gap-2 flex-wrap">
                            <span className={`text-[10px] px-1 rounded border font-mono ${s.cls}`}>{f.mode}</span>
                            <span className="text-white font-mono text-[11px] break-all">{f.path}</span>
                            <span className="ml-auto"><CopyBtn cmd={f.fix} label="chmod" /></span>
                        </div>
                        <div className="text-[10px] text-gray-500 mt-0.5" style={{ wordBreak: 'keep-all' }}>{f.title_ko}</div>
                    </li>
                );
            })}
        </ul>
    );
}

function ContainerRows({ data }) {
    if (data && data.available === false) return <Unavailable reason={data.reason} hint={data.fix_hint} />;
    const containers = (data?.containers || []).map(c => ({
        ...c, actionable: (c.findings || []).filter(f => f.severity !== 'INFO'),
    }));
    const flagged = containers.filter(c => c.actionable.length);
    if (!flagged.length) {
        return (
            <div className="text-[11px] text-gray-500 flex items-center gap-1">
                <Check className="w-3 h-3 text-neon-green" />
                실행 중 컨테이너 {containers.length}개 — 특권·소켓 마운트·전체 공개 없음
            </div>
        );
    }
    return (
        <ul className="space-y-1">
            {flagged.map(c => c.actionable.map(f => {
                const s = SEV[f.severity] || SEV.INFO;
                return (
                    <li key={`${c.name}-${f.code}`} className="text-xs border-l-2 pl-2 py-0.5" style={{ borderColor: s.border }}>
                        <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-white font-mono">{c.name}</span>
                            <span className={`text-[10px] px-1 rounded border ${s.cls}`}>{f.code}</span>
                            <span className="text-gray-500 font-mono text-[10px] break-all">{c.image}</span>
                        </div>
                        <div className="text-[10px] text-gray-400 mt-0.5" style={{ wordBreak: 'keep-all' }}>{f.title_ko}</div>
                        <div className="text-[10px] text-gray-600 mt-0.5" style={{ wordBreak: 'keep-all' }}>{f.fix_ko}</div>
                    </li>
                );
            }))}
        </ul>
    );
}

export default function ConfigAuditPanel() {
    const [perm, setPerm] = useState(null);
    const [cont, setCont] = useState(null);

    useEffect(() => {
        let alive = true;
        const load = () => {
            api('/api/permissions').then(d => { if (alive) setPerm(d); }).catch(() => {});
            api('/api/containers').then(d => { if (alive) setCont(d); }).catch(() => {});
        };
        load();
        const iv = setInterval(load, 120000);
        return () => { alive = false; clearInterval(iv); };
    }, []);

    if (!perm && !cont) return null;
    const permCount = perm?.counts?.total ?? 0;
    const contCount = cont?.counts?.actionable ?? 0;
    const total = permCount + contCount;

    return (
        <div className="border border-neon-green/30 bg-cyber-black/80 backdrop-blur-sm p-4 rounded-sm neon-border text-sm">
            <h3 className="text-neon-green font-bold flex items-center gap-2 mb-2 border-b border-neon-green/30 pb-2">
                <FileWarning className="w-4 h-4" /> 설정 점검
                <span className={`ml-auto text-xs font-normal ${total ? 'text-yellow-400' : 'text-gray-500'}`}>
                    {total ? `조치 필요 ${total}` : '문제 없음'}
                </span>
            </h3>

            <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">파일 권한</div>
            <PermissionRows data={perm} />

            <div className="text-[10px] text-gray-500 uppercase tracking-wider mt-3 mb-1 flex items-center gap-1">
                <Boxes className="w-3 h-3" /> 컨테이너 설정
            </div>
            <ContainerRows data={cont} />

            <div className="text-[10px] text-gray-600 mt-2" style={{ wordBreak: 'keep-all' }}>
                권한을 좁히기 전에 이미 심어진 것이 없는지 함께 확인하세요 (autostart 항목, gitconfig 훅 경로는 알림 근거에 포함됩니다).
            </div>
        </div>
    );
}
