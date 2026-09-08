import React, { useEffect, useState } from 'react';
import { ShieldBan, Unlock, Plus, ClipboardCopy, AlertTriangle } from 'lucide-react';
import { api, fmtTime } from '../api';

export default function BlockListPanel({ tick }) {
    const [data, setData] = useState({ fail2ban: {}, items: [] });
    const [newIp, setNewIp] = useState('');
    const [err, setErr] = useState('');

    const load = async () => {
        try { setData(await api('/api/blocked')); } catch (e) { if (e.status !== 401) console.error(e); }
    };
    useEffect(() => {
        let alive = true;
        api('/api/blocked').then(d => { if (alive) setData(d); }).catch(() => {});
        return () => { alive = false; };
    }, [tick]);

    const unblock = async (ip) => {
        if (!confirm(`${ip} 차단을 해제할까요?`)) return;
        try { await api(`/api/blocked/${ip}/unblock`, { method: 'POST' }); setErr(''); load(); }
        catch (e) { setErr(e.message); }
    };
    const block = async (e) => {
        e.preventDefault();
        if (!newIp.trim()) return;
        try { const r = await api('/api/blocked', { method: 'POST', body: { ip: newIp.trim(), reason: '대시보드에서 수동 차단' } }); setNewIp(''); setErr(r.status === 'RECOMMENDED' ? `fail2ban 을 제어할 수 없어 권고로만 기록됨 (${r.why})` : ''); load(); }
        catch (e) { setErr(e.message); }
    };

    const f2b = data.fail2ban || {};
    const healthy = f2b.health === 'ok';
    const items = data.items || [];

    return (
        <div className={`border ${healthy ? 'border-neon-green/30' : 'border-yellow-500/50'} bg-cyber-black/90 p-4 rounded-sm`}>
            <h3 className={`${healthy ? 'text-neon-green' : 'text-yellow-400'} font-bold flex items-center gap-2 mb-2 uppercase tracking-wider`}>
                <ShieldBan className="w-5 h-5" />
                IP 차단 (fail2ban · jail {f2b.jail || '?'}) — 활성 {items.filter(i => i.status === 'ACTIVE').length}
                {items.some(i => i.status === 'RECOMMENDED') && <span className="text-xs normal-case text-yellow-400">권고 {items.filter(i => i.status === 'RECOMMENDED').length}</span>}
            </h3>
            {!healthy && (
                <div className="text-xs text-yellow-300 bg-yellow-900/20 border border-yellow-700/40 rounded p-2 mb-2 flex gap-2" style={{ wordBreak: 'keep-all' }}>
                    <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                    <div>
                        <div>fail2ban 연동 불가: {f2b.reason || '상태 확인 중'}</div>
                        {f2b.fix_hint && <div className="text-gray-400 mt-1">해결: {f2b.fix_hint}</div>}
                        <div className="text-gray-500 mt-1">이 상태에서는 자동 차단이 이뤄지지 않고 '권고' 로만 기록됩니다.</div>
                    </div>
                </div>
            )}
            {f2b.stats && Object.keys(f2b.stats).length > 0 && (
                <div className="text-[11px] text-gray-500 font-mono mb-2">
                    현재 실패 {f2b.stats.currently_failed ?? '-'} · 누적 실패 {f2b.stats.total_failed ?? '-'} · 누적 차단 {f2b.stats.total_banned ?? '-'}
                </div>
            )}
            {items.length > 0 && (
                <div className="overflow-x-auto">
                    <table className="w-full text-xs text-left text-gray-400">
                        <thead className="text-gray-500 uppercase border-b border-gray-800">
                            <tr><th className="py-2">IP</th><th className="py-2">상태</th><th className="py-2">사유</th><th className="py-2">시각</th><th className="py-2">조치</th></tr>
                        </thead>
                        <tbody>
                            {items.map((b) => (
                                <tr key={b.id} className="border-b border-gray-800 last:border-0 hover:bg-white/5">
                                    <td className="py-2 px-1 text-white font-mono">{b.ip_address}</td>
                                    <td className="py-2 px-1">
                                        {b.status === 'ACTIVE'
                                            ? <span className="text-neon-red">차단 중 ({b.source})</span>
                                            : <span className="text-yellow-400 flex items-center gap-1">차단 권고
                                                {b.manual_command && <button onClick={() => navigator.clipboard.writeText(b.manual_command)} title={b.manual_command} className="text-gray-500 hover:text-neon-green"><ClipboardCopy className="w-3 h-3" /></button>}
                                              </span>}
                                    </td>
                                    <td className="py-2 px-1" style={{ wordBreak: 'keep-all' }}>{b.reason}</td>
                                    <td className="py-2 px-1">{fmtTime(b.blocked_at)}</td>
                                    <td className="py-2 px-1">
                                        <button onClick={() => unblock(b.ip_address)} className="text-neon-green hover:text-white flex items-center gap-1 border border-neon-green/30 px-2 py-1 rounded hover:bg-neon-green/20">
                                            <Unlock className="w-3 h-3" /> {b.status === 'ACTIVE' ? '해제' : '권고 취소'}
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
            <form onSubmit={block} className="flex items-center gap-2 mt-2">
                <input value={newIp} onChange={(e) => setNewIp(e.target.value)} placeholder="수동 차단할 IP" className="flex-1 bg-cyber-gray border border-gray-700 focus:border-neon-green outline-none px-2 py-1 text-xs font-mono text-white" />
                <button type="submit" className="text-xs border border-neon-red/50 text-neon-red hover:bg-neon-red/20 px-2 py-1 rounded flex items-center gap-1"><Plus className="w-3 h-3" /> 차단</button>
            </form>
            {err && <div className="text-xs text-yellow-400 mt-1" style={{ wordBreak: 'keep-all' }}>{err}</div>}
        </div>
    );
}
