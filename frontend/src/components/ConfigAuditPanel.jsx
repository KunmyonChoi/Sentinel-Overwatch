import React, { useEffect, useState } from 'react';
import { FileWarning, Boxes, Check, Wrench, AlertTriangle } from 'lucide-react';
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

/** 권한 일괄 조치: 먼저 무엇이 바뀔지 보여주고, 확인을 받은 뒤에만 적용한다. */
function FixControl({ count, onDone }) {
    const [preview, setPreview] = useState(null);   // dry-run 결과
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState(null);     // 적용 결과
    const [error, setError] = useState(null);

    const call = async (apply) => {
        setBusy(true); setError(null);
        try {
            const r = await api(`/api/permissions/fix?apply=${apply}`, { method: 'POST' });
            if (!r.ok) { setError(r); setPreview(null); return; }
            if (apply) { setResult(r); setPreview(null); onDone?.(); }
            else setPreview(r);
        } catch (e) {
            setError({ error: e.message || '요청 실패', fix_hint: '' });
        } finally { setBusy(false); }
    };

    if (!count) return null;

    return (
        <div className="mt-2">
            {!preview && !result && (
                <button onClick={() => call(false)} disabled={busy}
                    className="text-[11px] border border-gray-700 hover:border-neon-green text-gray-300 hover:text-neon-green px-2 py-1 rounded flex items-center gap-1 disabled:opacity-50">
                    <Wrench className="w-3 h-3" /> {busy ? '확인 중…' : `권한 일괄 조치 (${count}건 검토)`}
                </button>
            )}

            {error && (
                <div className="text-[11px] text-yellow-400 border border-yellow-500/40 rounded px-2 py-1 mt-1" style={{ wordBreak: 'keep-all' }}>
                    <AlertTriangle className="w-3 h-3 inline mr-1" />조치하지 못했습니다 — {error.error}
                    {error.fix_hint && <div className="text-gray-500 mt-0.5">해결: {error.fix_hint}</div>}
                </div>
            )}

            {preview && (
                <div className="border border-yellow-500/40 rounded p-2 mt-1 text-[11px]">
                    <div className="text-yellow-400 mb-1">아래 {preview.results?.length ?? 0}건의 권한을 좁힙니다. 넓히는 변경은 없습니다.</div>
                    <ul className="space-y-0.5 max-h-40 overflow-y-auto scrollbar-hide font-mono">
                        {(preview.results || []).map(r => (
                            <li key={r.path} className="text-gray-300 break-all">
                                <span className="text-neon-red">{r.before}</span>
                                <span className="text-gray-600"> → </span>
                                <span className="text-neon-green">{r.after}</span>
                                <span className="text-gray-500"> {r.path}</span>
                            </li>
                        ))}
                    </ul>
                    <div className="flex gap-2 mt-2">
                        <button onClick={() => call(true)} disabled={busy}
                            className="text-[11px] border border-neon-green text-neon-green px-2 py-0.5 rounded hover:bg-neon-green/10 disabled:opacity-50">
                            {busy ? '적용 중…' : '적용'}
                        </button>
                        <button onClick={() => setPreview(null)} className="text-[11px] border border-gray-700 text-gray-400 px-2 py-0.5 rounded hover:border-gray-500">
                            취소
                        </button>
                    </div>
                </div>
            )}

            {result && (
                <div className="text-[11px] text-neon-green mt-1 flex items-center gap-1">
                    <Check className="w-3 h-3" /> {result.changed}건 조치 완료 · 라이브 피드에 기록됨
                </div>
            )}
        </div>
    );
}

export default function ConfigAuditPanel() {
    const [perm, setPerm] = useState(null);
    const [cont, setCont] = useState(null);
    const [tick, setTick] = useState(0);

    useEffect(() => {
        let alive = true;
        const load = () => {
            api('/api/permissions').then(d => { if (alive) setPerm(d); }).catch(() => {});
            api('/api/containers').then(d => { if (alive) setCont(d); }).catch(() => {});
        };
        load();
        const iv = setInterval(load, 120000);
        return () => { alive = false; clearInterval(iv); };
    }, [tick]);

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
            <FixControl count={permCount} onDone={() => setTick(t => t + 1)} />

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
