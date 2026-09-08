import React, { useState } from 'react';
import { Wrench, X } from 'lucide-react';
import { api } from '../api';

export default function MaintenanceControl({ maintenance, onChanged }) {
    const [open, setOpen] = useState(false);
    const [minutes, setMinutes] = useState(60);
    const [note, setNote] = useState('');
    const [busy, setBusy] = useState(false);

    const start = async (e) => {
        e.preventDefault();
        setBusy(true);
        try { await api('/api/maintenance', { method: 'POST', body: { minutes: Number(minutes), note, by: 'dashboard' } }); setOpen(false); setNote(''); onChanged && onChanged(); }
        catch (err) { alert(`시작 실패: ${err.message}`); }
        finally { setBusy(false); }
    };
    const stop = async () => {
        setBusy(true);
        try { await api('/api/maintenance', { method: 'DELETE' }); onChanged && onChanged(); }
        catch (err) { alert(`종료 실패: ${err.message}`); }
        finally { setBusy(false); }
    };

    if (maintenance?.active) {
        const min = Math.ceil((maintenance.remaining_seconds || 0) / 60);
        return (
            <div className="flex items-center gap-2 text-xs border border-blue-500/50 bg-blue-500/10 text-blue-200 px-2 py-1 rounded">
                <Wrench className="w-3.5 h-3.5" />
                <span>점검 모드 · {min}분 남음{maintenance.note ? ` · ${maintenance.note}` : ''}</span>
                <button onClick={stop} disabled={busy} className="ml-1 text-blue-300 hover:text-white" title="점검 모드 종료"><X className="w-3.5 h-3.5" /></button>
            </div>
        );
    }
    return (
        <div className="relative">
            <button onClick={() => setOpen(o => !o)} className="flex items-center gap-1 text-xs border border-gray-700 hover:border-blue-400 text-gray-400 hover:text-blue-200 px-2 py-1 rounded" title="계획 작업 중 설정·패키지·영속화 알림을 자동 확인 처리합니다. 침입 신호는 계속 올라옵니다.">
                <Wrench className="w-3.5 h-3.5" /> 점검 모드
            </button>
            {open && (
                <form onSubmit={start} className="absolute right-0 mt-1 z-40 w-72 border border-blue-500/50 bg-cyber-black p-3 rounded text-xs space-y-2 shadow-lg">
                    <div className="text-blue-200 font-bold">점검 모드 시작</div>
                    <div className="text-gray-500" style={{ wordBreak: 'keep-all' }}>이 시간 동안 무결성·영속화·패키지·리스너·모듈·Lynis 알림은 "점검 모드"로 자동 확인됩니다. 브루트포스, 실패 후 로그인, 리버스 셸, 새 로그인 IP 는 그대로 알립니다.</div>
                    <label className="flex items-center gap-2">시간(분)
                        <select value={minutes} onChange={e => setMinutes(e.target.value)} className="bg-cyber-gray border border-gray-700 px-1 py-0.5">
                            {[15, 30, 60, 120, 240].map(m => <option key={m} value={m}>{m}</option>)}
                        </select>
                    </label>
                    <input value={note} onChange={e => setNote(e.target.value)} placeholder="메모 (예: harden.sh 적용, 커널 업그레이드)" className="w-full bg-cyber-gray border border-gray-700 focus:border-blue-400 outline-none px-2 py-1 text-white" />
                    <div className="flex gap-2 justify-end">
                        <button type="button" onClick={() => setOpen(false)} className="text-gray-500 hover:text-gray-300">취소</button>
                        <button type="submit" disabled={busy} className="border border-blue-400 text-blue-200 hover:bg-blue-500/20 px-2 py-0.5 rounded">시작</button>
                    </div>
                </form>
            )}
        </div>
    );
}
