import React from 'react';
import { Info } from 'lucide-react';

export default function InfoPanel() {
    return (
        <div className="border border-neon-green/30 bg-cyber-black/80 backdrop-blur-sm p-4 rounded-sm neon-border text-sm text-gray-400">
            <h3 className="text-neon-green font-bold flex items-center gap-2 mb-2">
                <Info className="w-4 h-4" />
                SYSTEM_CAPABILITIES
            </h3>
            <ul className="space-y-2 list-disc list-inside">
                <li>
                    <strong className="text-white">Intrusion Detection:</strong> Monitors SSH logs for failed login attempts (Brute Force).
                </li>
                <li>
                    <strong className="text-white">Malware Scan:</strong> Real-time process scanning for known hacking tools (e.g., nmap, wireshark).
                </li>
                <li>
                    <strong className="text-white">Threat Intel:</strong> Aggregates live security news and vulnerability reports (RSS).
                </li>
            </ul>
        </div>
    );
}
