import React, { useState } from 'react';
import { ClipboardCopy, Check } from 'lucide-react';

/** 조치 명령을 클립보드로 복사하는 작은 버튼. 명령 전문은 title 로 노출한다. */
export default function CopyBtn({ label = '복사', cmd, title }) {
    const [ok, setOk] = useState(false);
    if (!cmd) return null;
    return (
        <button
            onClick={() => { navigator.clipboard.writeText(cmd); setOk(true); setTimeout(() => setOk(false), 1500); }}
            title={title || cmd}
            className="text-[10px] border border-gray-700 hover:border-neon-green text-gray-400 hover:text-neon-green px-1 py-0.5 rounded flex items-center gap-1 shrink-0">
            {ok ? <Check className="w-3 h-3 text-neon-green" /> : <ClipboardCopy className="w-3 h-3" />} {ok ? '복사됨' : label}
        </button>
    );
}
