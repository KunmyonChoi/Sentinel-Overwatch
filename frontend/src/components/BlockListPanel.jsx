import React, { useEffect, useState } from 'react';
import { ShieldBan, Unlock } from 'lucide-react';

export default function BlockListPanel() {
    const [blockedIps, setBlockedIps] = useState([]);

    const fetchBlockedIps = async () => {
        try {
            const res = await fetch('http://localhost:8000/api/blocked');
            if (res.ok) {
                const data = await res.json();
                setBlockedIps(data);
            }
        } catch (e) {
            console.error("Failed to fetch blocked IPs", e);
        }
    };

    useEffect(() => {
        fetchBlockedIps();
        const interval = setInterval(fetchBlockedIps, 5000);
        return () => clearInterval(interval);
    }, []);

    const handleUnblock = async (ip) => {
        if (!confirm(`Are you sure you want to unblock ${ip}?`)) return;

        try {
            const res = await fetch(`http://localhost:8000/api/unblock/${ip}`, { method: 'POST' });
            if (res.ok) {
                fetchBlockedIps(); // Refresh list
            } else {
                alert("Failed to unblock IP");
            }
        } catch (e) {
            console.error(e);
        }
    };

    if (blockedIps.length === 0) return null;

    return (
        <div className="border border-neon-red/50 bg-cyber-black/90 p-4 rounded-sm neon-border-red mt-4">
            <h3 className="text-neon-red font-bold flex items-center gap-2 mb-2 uppercase tracking-wider">
                <ShieldBan className="w-5 h-5 animate-pulse" />
                Active IP Blocks ({blockedIps.length})
            </h3>
            <div className="overflow-x-auto">
                <table className="w-full text-xs text-left text-gray-400">
                    <thead className="text-gray-500 uppercase border-b border-gray-800">
                        <tr>
                            <th className="py-2">IP Address</th>
                            <th className="py-2">Reason</th>
                            <th className="py-2">Time</th>
                            <th className="py-2">Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {blockedIps.map((ip) => (
                            <tr key={ip.id} className="border-b border-gray-800 last:border-0 hover:bg-white/5">
                                <td className="py-2 px-1 text-white font-mono">{ip.ip_address}</td>
                                <td className="py-2 px-1">{ip.reason}</td>
                                <td className="py-2 px-1">{new Date(ip.blocked_at + "Z").toLocaleTimeString()}</td>
                                <td className="py-2 px-1">
                                    <button
                                        onClick={() => handleUnblock(ip.ip_address)}
                                        className="text-neon-green hover:text-white flex items-center gap-1 border border-neon-green/30 px-2 py-1 rounded hover:bg-neon-green/20 transition-colors"
                                    >
                                        <Unlock className="w-3 h-3" /> Unblock
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
