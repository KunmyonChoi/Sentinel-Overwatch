import React, { useEffect, useState, useCallback } from 'react';
import { MessageSquare, RefreshCw } from 'lucide-react';

export default function HighlightKorean() {
    const [highlight, setHighlight] = useState("데이터를 분석 중입니다...");
    const [refreshing, setRefreshing] = useState(false);

    const fetchHighlight = useCallback(async () => {
        try {
            const res = await fetch('http://localhost:8000/api/highlight/korean');
            const data = await res.json();
            setHighlight(data.highlight);
        } catch (e) {
            console.error("Failed to fetch highlight", e);
            setHighlight("현재 하이라이트 데이터를 불러올 수 없습니다.");
        }
    }, []);

    const handleRefresh = async () => {
        setRefreshing(true);
        await fetchHighlight();
        setRefreshing(false);
    };

    useEffect(() => {
        fetchHighlight();
        const interval = setInterval(fetchHighlight, 10000);
        return () => clearInterval(interval);
    }, [fetchHighlight]);

    return (
        <div className="border border-neon-green/30 bg-cyber-black/80 backdrop-blur-sm p-4 neon-border rounded-sm animate-pulse-slow">
            <h2 className="text-lg font-bold text-neon-green mb-2 flex items-center gap-2 border-b border-neon-green/30 pb-2">
                <MessageSquare className="w-5 h-5" />
                <span className="tracking-wide flex-1">오늘의 하이라이트</span>
                <button
                    onClick={handleRefresh}
                    disabled={refreshing}
                    className="text-neon-green/50 hover:text-neon-green transition-colors disabled:cursor-wait"
                    title="강제 갱신"
                >
                    <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
                </button>
            </h2>
            <p className="text-gray-300 text-sm leading-relaxed mt-2" style={{ wordBreak: 'keep-all' }}>
                {highlight}
            </p>
        </div>
    );
}
