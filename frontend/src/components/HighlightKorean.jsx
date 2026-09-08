import React, { useCallback, useEffect, useState } from 'react';
import { MessageSquare, RefreshCw } from 'lucide-react';
import { api } from '../api';

export default function HighlightKorean() {
    const [highlight, setHighlight] = useState('데이터를 분석 중입니다...');
    const [refreshing, setRefreshing] = useState(false);

    const fetchHighlight = useCallback(async () => {
        try {
            const data = await api('/api/summary/korean');
            setHighlight(data.highlight);
        } catch (e) {
            if (e.status !== 401) setHighlight('요약을 불러올 수 없습니다. 백엔드 연결을 확인하세요.');
        }
    }, []);

    useEffect(() => {
        let alive = true;
        const load = () => api('/api/summary/korean').then(d => { if (alive) setHighlight(d.highlight); }).catch(() => {});
        load();
        const iv = setInterval(load, 15000);
        return () => { alive = false; clearInterval(iv); };
    }, []);

    return (
        <div className="border border-neon-green/30 bg-cyber-black/80 backdrop-blur-sm p-4 neon-border rounded-sm">
            <h2 className="text-lg font-bold text-neon-green mb-2 flex items-center gap-2 border-b border-neon-green/30 pb-2">
                <MessageSquare className="w-5 h-5" />
                <span className="tracking-wide flex-1">현재 상황 요약</span>
                <button
                    onClick={async () => { setRefreshing(true); await fetchHighlight(); setRefreshing(false); }}
                    disabled={refreshing}
                    className="text-neon-green/50 hover:text-neon-green transition-colors disabled:cursor-wait"
                    title="갱신"
                >
                    <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
                </button>
            </h2>
            <p className="text-gray-300 text-sm leading-relaxed mt-2" style={{ wordBreak: 'keep-all' }}>{highlight}</p>
        </div>
    );
}
