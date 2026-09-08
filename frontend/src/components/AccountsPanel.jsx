import React, { useEffect, useState } from 'react';
import { Users, Lock, Unlock, KeyRound, ClipboardCopy, Check } from 'lucide-react';
import { api, fmtDateTime } from '../api';

const STATE = {
    active: { cls: 'text-neon-green border-neon-green/50', icon: Unlock },
    locked: { cls: 'text-yellow-400 border-yellow-500/50', icon: Lock },
    disabled: { cls: 'text-gray-500 border-gray-700', icon: Lock },
    unknown: { cls: 'text-gray-500 border-gray-700', icon: Lock },
};

function CopyBtn({ label, cmd }) {
    const [ok, setOk] = useState(false);
    return (
        <button onClick={() => { navigator.clipboard.writeText(cmd); setOk(true); setTimeout(() => setOk(false), 1500); }} title={cmd}
            className="text-[10px] border border-gray-700 hover:border-neon-green text-gray-400 hover:text-neon-green px-1 py-0.5 rounded flex items-center gap-1">
            {ok ? <Check className="w-3 h-3 text-neon-green" /> : <ClipboardCopy className="w-3 h-3" />} {label}
        </button>
    );
}

export default function AccountsPanel() {
    const [data, setData] = useState(null);
    useEffect(() => {
        let alive = true;
        const load = () => api('/api/accounts').then(d => { if (alive) setData({ ...d, fetched_at: Date.now() }); }).catch(() => {});
        load();
        const iv = setInterval(load, 60000);
        return () => { alive = false; clearInterval(iv); };
    }, []);
    if (!data) return null;
    const accounts = data.accounts || [];
    const active = accounts.filter(a => a.state === 'active').length;

    return (
        <div className="border border-neon-green/30 bg-cyber-black/80 backdrop-blur-sm p-4 rounded-sm neon-border text-sm">
            <h3 className="text-neon-green font-bold flex items-center gap-2 mb-2 border-b border-neon-green/30 pb-2">
                <Users className="w-4 h-4" /> 계정 상태
                <span className="ml-auto text-xs font-normal text-gray-500">활성 {active} / 전체 {accounts.length}</span>
            </h3>
            {!data.shadow_readable && <div className="text-[11px] text-yellow-400 mb-2">/etc/shadow 를 읽을 수 없어 잠김 여부를 알 수 없습니다 (CAP_DAC_READ_SEARCH 필요).</div>}
            <ul className="space-y-1.5">
                {accounts.map(a => {
                    const s = STATE[a.state] || STATE.unknown;
                    const Icon = s.icon;
                    const stale = a.last_login && (data.fetched_at - new Date(a.last_login).getTime()) > 180 * 86400000;
                    return (
                        <li key={a.name} className="text-xs border-l-2 pl-2 py-0.5" style={{ borderColor: a.state === 'active' ? '#00ff41' : a.state === 'locked' ? '#eab308' : '#374151' }}>
                            <div className="flex items-center gap-2 flex-wrap">
                                <span className="text-white font-mono">{a.name}</span>
                                <span className={`text-[10px] px-1 rounded border flex items-center gap-1 ${s.cls}`}><Icon className="w-3 h-3" />{a.state_ko}</span>
                                {a.privileged_groups.map(g => <span key={g} className={`text-[10px] px-1 rounded border ${g === 'sudo' || g === 'root' ? 'border-neon-red/50 text-neon-red' : 'border-gray-600 text-gray-400'}`}>{g}</span>)}
                                {a.has_ssh_keys && <span className="text-[10px] text-gray-400 flex items-center gap-0.5" title="authorized_keys 있음"><KeyRound className="w-3 h-3" /> 키</span>}
                                <span className="ml-auto flex gap-1">
                                    {a.state === 'active' && a.uid !== 0 && <CopyBtn label="잠금" cmd={a.commands.lock} />}
                                    {a.state === 'locked' && a.uid !== 0 && <CopyBtn label="되살리기" cmd={a.commands.unlock} />}
                                </span>
                            </div>
                            <div className={`text-[10px] mt-0.5 ${stale && a.state === 'active' ? 'text-yellow-400' : 'text-gray-500'}`}>
                                {a.last_login ? `마지막 로그인 ${fmtDateTime(a.last_login)}${a.last_login_host ? ` · ${a.last_login_host}` : ''}${stale && a.state === 'active' ? ' · 180일 이상 미사용' : ''}` : '로그인 기록 없음'}
                                {a.password_max_days && a.password_max_days < 99999 ? ` · 비밀번호 ${a.password_max_days}일 주기` : ''}
                            </div>
                        </li>
                    );
                })}
            </ul>
        </div>
    );
}
