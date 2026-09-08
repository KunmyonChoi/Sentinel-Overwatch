import React, { useState } from 'react';
import { KeyRound } from 'lucide-react';
import { setToken } from '../api';

export default function TokenGate() {
    const [value, setValue] = useState('');
    return (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-6">
            <form
                onSubmit={(e) => { e.preventDefault(); if (value.trim()) setToken(value); }}
                className="border border-neon-green neon-border bg-cyber-black p-6 rounded-sm w-full max-w-md"
            >
                <h2 className="text-neon-green font-bold flex items-center gap-2 mb-3">
                    <KeyRound className="w-5 h-5" /> API 토큰 필요
                </h2>
                <p className="text-gray-400 text-sm mb-3" style={{ wordBreak: 'keep-all' }}>
                    대시보드 API 는 토큰으로 보호됩니다. 서버의 <code className="text-gray-200">backend/.api_token</code> 파일 내용
                    (또는 <code className="text-gray-200">SECDASH_API_TOKEN</code>)을 입력하세요. 이 브라우저에만 저장됩니다.
                </p>
                <input
                    autoFocus
                    type="password"
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                    placeholder="API token"
                    className="w-full bg-cyber-gray border border-gray-700 focus:border-neon-green outline-none px-3 py-2 text-sm text-white font-mono mb-3"
                />
                <button type="submit" className="w-full border border-neon-green text-neon-green hover:bg-neon-green/20 py-2 text-sm font-bold">
                    연결
                </button>
            </form>
        </div>
    );
}
