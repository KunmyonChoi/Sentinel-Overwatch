// 지금 보고 있는 화면이 운영인지 개발인지 알려준다.
//
// 두 인스턴스는 겉보기가 똑같다. 실제로 이것 때문에 개발 인스턴스의 '중단' 표시를
// 운영 장애로 읽는 일이 있었다 — 개발 쪽은 auth.log 를 읽을 권한이 없어서 정상적으로
// 중단이었는데, 화면만 보고는 구별할 수 없었다.
//
// 판별은 백엔드가 한다(/api/host 의 instance.mode). systemd 가 띄운 프로세스에만
// INVOCATION_ID 가 있으므로, 계정 이름이나 포트를 하드코딩해 맞히는 것보다 정확하다.
// 운영일 때는 아무것도 그리지 않는다 — 평소 화면을 어지럽히지 않기 위해서다.
import React from 'react';

export default function InstanceBadge({ host, tone = 'calm' }) {
    if (!host?.instance || host.instance.mode === 'service') return null;
    const { port, user } = host.instance;
    const label = `개발 인스턴스 · :${port} · ${user}`;
    const title = '이 화면은 개발용입니다. 운영 상태는 systemd 로 뜬 인스턴스에서 확인하세요.';

    if (tone === 'neon') {
        return (
            <span title={title} className="px-3 py-1.5 rounded border border-yellow-400 text-yellow-300 font-kr text-[13px] whitespace-nowrap">
                {label}
            </span>
        );
    }
    return (
        <span title={title} className="px-3 py-1.5 rounded-lg bg-calm-warn-soft text-calm-warn border border-calm-warn/40 font-kr text-[13px] whitespace-nowrap">
            {label}
        </span>
    );
}
