import React, { useEffect, useState } from 'react';
import { Activity, Cpu, HardDrive, ShieldCheck, ShieldOff, Usb, ClipboardCopy, Check } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { api } from '../api';

function CopyCmd({ label, cmd }) {
    const [ok, setOk] = useState(false);
    return (
        <button
            onClick={() => { navigator.clipboard.writeText(cmd); setOk(true); setTimeout(() => setOk(false), 1500); }}
            title={cmd}
            className="flex items-center gap-1 text-[11px] border border-gray-700 hover:border-neon-green text-gray-300 hover:text-neon-green px-1.5 py-0.5 rounded"
        >
            {ok ? <Check className="w-3 h-3 text-neon-green" /> : <ClipboardCopy className="w-3 h-3" />} {label}
        </button>
    );
}

function UsbPolicy({ usb, blocked }) {
    if (!usb) return null;
    const c = usb.commands || {};
    const tone = usb.state === 'blocked' ? 'text-neon-green' : usb.state === 'temporarily_unblocked' ? 'text-yellow-400' : 'text-gray-300';
    return (
        <div className="border-t border-gray-800 pt-2 mt-2 text-[11px]">
            <div className="flex items-center gap-1 mb-1">
                <Usb className={`w-3.5 h-3.5 ${tone}`} />
                <span className="text-gray-400">USB 저장장치:</span>
                <span className={`${tone} font-bold`}>{usb.state_ko}</span>
            </div>
            <div className="flex flex-wrap gap-1">
                {usb.state === 'blocked' && <CopyCmd label="일시 해제 (재부팅까지)" cmd={c.temp_unblock} />}
                {usb.state === 'temporarily_unblocked' && <CopyCmd label="다시 차단" cmd={c.reblock} />}
                {usb.blocked_by_config && <CopyCmd label="영구 해제" cmd={c.permanent_unblock} />}
                {!usb.blocked_by_config && <CopyCmd label="차단 설정" cmd={c.permanent_block} />}
            </div>
            {blocked && blocked.length > 0 && (
                <div className="text-gray-600 mt-1">차단 모듈: {blocked.join(', ')} · 해제 시 auditd 가 모듈 로드를 기록해 알림이 올라옵니다</div>
            )}
        </div>
    );
}

export default function SystemHealth({ stats, host }) {
    const isDefcon1 = stats?.status === 'DEFCON 1';
    const isDefcon3 = stats?.status === 'DEFCON 3';
    const statusText = stats ? `${stats.status}` : 'ANALYZING...';
    const [timeline, setTimeline] = useState([]);

    useEffect(() => {
        const load = () => api('/api/stats/timeline').then(setTimeline).catch(() => {});
        load();
        const iv = setInterval(load, 30000);
        return () => clearInterval(iv);
    }, []);

    const border = isDefcon1 ? 'neon-border-red border-neon-red' : isDefcon3 ? 'border-yellow-500' : 'neon-border border-neon-green';
    const text = isDefcon1 ? 'text-neon-red border-neon-red' : isDefcon3 ? 'text-yellow-400 border-yellow-500' : 'text-neon-green border-neon-green';
    const priv = host?.privileges;

    return (
        <div className={`border ${border} bg-cyber-black/80 backdrop-blur-sm p-4 rounded-sm`}>
            <h2 className={`text-xl font-bold mb-3 border-b pb-2 flex justify-between ${text}`}>
                <span>시스템 상태</span>
                <span className={isDefcon1 ? 'animate-pulse' : ''}>{statusText}</span>
            </h2>

            {stats && (
                <div className="grid grid-cols-3 gap-2 mb-3 text-center text-xs">
                    <div className="bg-cyber-gray/50 p-2 rounded border border-gray-700"><div className="text-neon-red text-lg font-bold">{stats.open_critical}</div><div className="text-gray-500">미확인 긴급</div></div>
                    <div className="bg-cyber-gray/50 p-2 rounded border border-gray-700"><div className="text-yellow-400 text-lg font-bold">{stats.open_warning}</div><div className="text-gray-500">미확인 경고</div></div>
                    <div className="bg-cyber-gray/50 p-2 rounded border border-gray-700"><div className="text-blue-300 text-lg font-bold">{stats.acked}</div><div className="text-gray-500">대응 중</div></div>
                </div>
            )}

            {stats && stats.status !== 'SAFE' && (
                <div className={`mb-3 p-2 rounded text-xs border ${isDefcon1 ? 'bg-red-900/20 border-red-900/50' : 'bg-yellow-900/10 border-yellow-800/50'}`}>
                    <div className={`${isDefcon1 ? 'text-neon-red' : 'text-yellow-400'} font-bold mb-1`}>{stats.status_ko}</div>
                    <div className="text-gray-300 mb-1" style={{ wordBreak: 'keep-all' }}>{stats.reason}</div>
                    <div className="mt-1"><span className="text-gray-400 font-bold">조치: </span><span className="text-white" style={{ wordBreak: 'keep-all' }}>{stats.action}</span></div>
                </div>
            )}

            <div className="flex gap-3 mb-3">
                {[
                    { icon: Cpu, label: 'CPU', val: stats?.cpu_percent, warn: 70, crit: 90, fmt: v => `${v}%` },
                    { icon: HardDrive, label: 'RAM', val: stats?.mem_percent, warn: 70, crit: 85, fmt: v => `${v}%`, sub: stats ? `${stats.mem_used_gb}/${stats.mem_total_gb} GB` : '' },
                    { icon: Activity, label: 'DISK', val: stats?.disk_percent, warn: 75, crit: 90, fmt: v => `${v}%` },
                ].map(({ icon, label, val, warn, crit, fmt, sub }) => (
                    <div key={label} className="flex-1 bg-cyber-gray/50 p-2 rounded border border-gray-700">
                        <div className="flex items-center gap-1 mb-1 text-gray-400 text-xs">{React.createElement(icon, { className: 'w-3.5 h-3.5' })} {label}</div>
                        <div className={`text-xl font-bold ${(val ?? 0) > crit ? 'text-neon-red' : (val ?? 0) > warn ? 'text-yellow-400' : 'text-white'}`}>{val != null ? fmt(val) : '---'}</div>
                        {sub && <div className="text-[10px] text-gray-500">{sub}</div>}
                    </div>
                ))}
            </div>

            <div className="mb-2">
                <div className="text-xs text-gray-500 mb-1 font-mono">이벤트 타임라인 (24H, 시뮬레이션 제외)</div>
                <div className="h-32 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={timeline} barCategoryGap={1}>
                            <XAxis dataKey="hour" tick={{ fill: '#6b7280', fontSize: 9 }} axisLine={{ stroke: '#374151' }} tickLine={false} interval={2} />
                            <YAxis tick={{ fill: '#6b7280', fontSize: 9 }} axisLine={false} tickLine={false} width={24} allowDecimals={false} />
                            <Tooltip contentStyle={{ backgroundColor: '#0a0a0f', border: '1px solid #00ff41', fontSize: 11 }} labelStyle={{ color: '#9ca3af' }} itemStyle={{ padding: 0 }} />
                            <Bar dataKey="critical" stackId="a" fill="#ff0033" name="긴급" />
                            <Bar dataKey="warning" stackId="a" fill="#eab308" name="경고" />
                            <Bar dataKey="info" stackId="a" fill="#00ff4180" name="정보" radius={[2, 2, 0, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {priv && (
                <div className="text-[11px] text-gray-500 border-t border-gray-800 pt-2 space-y-0.5">
                    {[
                        ['auth.log 읽기', priv.auth_log_readable],
                        ['/etc/shadow 감시', priv.shadow_readable],
                        ['fail2ban 제어', priv.fail2ban_control],
                    ].map(([label, ok]) => (
                        <div key={label} className="flex items-center gap-1">
                            {ok ? <ShieldCheck className="w-3 h-3 text-neon-green" /> : <ShieldOff className="w-3 h-3 text-yellow-400" />}
                            <span className={ok ? 'text-gray-400' : 'text-yellow-400'}>{label}: {ok ? '가능' : '불가'}</span>
                        </div>
                    ))}
                    <UsbPolicy usb={host.usb_storage} blocked={host.blocked_modules} />
                    {host.pending_updates?.available && (
                        <div className={host.pending_updates.security > 0 ? 'text-yellow-400' : 'text-gray-400'}>
                            미적용 업데이트 {host.pending_updates.total} (보안 {host.pending_updates.security})
                        </div>
                    )}
                </div>
            )}

            <div className="mt-2 text-center text-[10px] text-gray-600 border-t border-gray-800 pt-2">
                DEFCON 1 = 미확인 긴급 알림 있음 · DEFCON 3 = 미확인 경고 알림 있음 · SAFE = 미확인 알림 없음. 알림을 확인(ack)하면 레벨에서 제외됩니다.
            </div>
        </div>
    );
}
