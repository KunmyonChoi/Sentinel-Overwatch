import React, { useState, useEffect } from 'react';
import { Activity, Cpu, HardDrive } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

export default function SystemHealth({ stats }) {
    const isDefcon1 = stats?.status === 'DEFCON 1';
    const statusText = stats?.status || "ANALYZING...";

    const [timeline, setTimeline] = useState([]);
    useEffect(() => {
        const fetchTimeline = () => {
            fetch('http://localhost:8000/api/stats/timeline')
                .then(r => r.json())
                .then(setTimeline)
                .catch(() => {});
        };
        fetchTimeline();
        const iv = setInterval(fetchTimeline, 30000);
        return () => clearInterval(iv);
    }, []);

    return (
        <div className={`border ${isDefcon1 ? 'neon-border-red border-neon-red' : 'neon-border border-neon-green'} bg-cyber-black/80 backdrop-blur-sm p-4 rounded-sm`}>
            <h2 className={`text-xl font-bold mb-4 border-b pb-2 flex justify-between ${isDefcon1 ? 'text-neon-red border-neon-red' : 'text-neon-green border-neon-green'}`}>
                <span>SYSTEM_STATUS</span>
                <span className={isDefcon1 ? 'animate-pulse' : ''}>{statusText}</span>
            </h2>

            <div className="flex gap-4 mb-4">
                <div className="flex-1 bg-cyber-gray/50 p-3 rounded border border-gray-700">
                    <div className="flex items-center gap-2 mb-2 text-gray-400">
                        <Cpu className="w-4 h-4" /> CPU
                    </div>
                    <div className={`text-2xl font-bold ${(stats?.cpu_percent ?? 0) > 90 ? 'text-neon-red' : (stats?.cpu_percent ?? 0) > 70 ? 'text-yellow-400' : 'text-white'}`}>
                        {stats?.cpu_percent != null ? `${stats.cpu_percent}%` : '---'}
                    </div>
                </div>
                <div className="flex-1 bg-cyber-gray/50 p-3 rounded border border-gray-700">
                    <div className="flex items-center gap-2 mb-2 text-gray-400">
                        <HardDrive className="w-4 h-4" /> RAM
                    </div>
                    <div className={`text-2xl font-bold ${(stats?.mem_percent ?? 0) > 85 ? 'text-neon-red' : (stats?.mem_percent ?? 0) > 70 ? 'text-yellow-400' : 'text-white'}`}>
                        {stats?.mem_used_gb != null ? `${stats.mem_used_gb}G` : '---'}
                    </div>
                    <div className="text-xs text-gray-500 mt-1">/ {stats?.mem_total_gb ?? '?'} GB ({stats?.mem_percent ?? '?'}%)</div>
                </div>
                <div className="flex-1 bg-cyber-gray/50 p-3 rounded border border-gray-700">
                    <div className="flex items-center gap-2 mb-2 text-gray-400">
                        <Activity className="w-4 h-4" /> DISK
                    </div>
                    <div className={`text-2xl font-bold ${(stats?.disk_percent ?? 0) > 90 ? 'text-neon-red' : (stats?.disk_percent ?? 0) > 75 ? 'text-yellow-400' : 'text-white'}`}>
                        {stats?.disk_percent != null ? `${stats.disk_percent}%` : '---'}
                    </div>
                </div>
            </div>

            <div className="mb-2">
                <div className="text-xs text-gray-500 mb-1 font-mono">EVENT TIMELINE (24H)</div>
                <div className="h-36 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={timeline} barCategoryGap={1}>
                            <XAxis
                                dataKey="hour"
                                tick={{ fill: '#6b7280', fontSize: 9 }}
                                axisLine={{ stroke: '#374151' }}
                                tickLine={false}
                                interval={2}
                            />
                            <YAxis
                                tick={{ fill: '#6b7280', fontSize: 9 }}
                                axisLine={false}
                                tickLine={false}
                                width={24}
                                allowDecimals={false}
                            />
                            <Tooltip
                                contentStyle={{ backgroundColor: '#0a0a0f', border: '1px solid #00ff41', fontSize: 11 }}
                                labelStyle={{ color: '#9ca3af' }}
                                itemStyle={{ padding: 0 }}
                            />
                            <Bar dataKey="critical" stackId="a" fill="#ff0033" name="Critical" />
                            <Bar dataKey="warning" stackId="a" fill="#eab308" name="Warning" />
                            <Bar dataKey="info" stackId="a" fill="#00ff4180" name="Info" radius={[2, 2, 0, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Actionable Advice Section */}
            {(stats?.reason && stats.status !== 'SAFE') && (
                <div className="mb-4 p-2 bg-red-900/20 border border-red-900/50 rounded text-xs">
                    <div className="text-neon-red font-bold mb-1">⚠️ THREAT DETECTED</div>
                    <div className="text-gray-300 mb-1">{stats.reason}</div>
                    <div className="flex gap-1 mt-2">
                        <span className="text-gray-400 font-bold">RECOMMENDED ACTION:</span>
                        <span className="text-white bg-red-600/20 px-1 rounded">{stats.action}</span>
                    </div>
                </div>
            )}

            <div className="mt-2 text-center text-xs">
                <div className="text-gray-500 border-t border-gray-800 pt-2">
                    <p><strong>DEFCON 1</strong> = Critical Threat Active</p>
                    <p><strong>DEFCON 3</strong> = Warning Level</p>
                    <p><strong>SAFE</strong> = Normal Operations</p>
                </div>
            </div>
        </div>
    );
}
