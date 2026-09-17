// 버전 표시 조각. 앱 버전은 처음 한 번만 읽는다 (실행 중에 바뀌지 않는다).
import React, { useEffect, useState } from 'react';
import { readAppVersion, versionLabel } from './version';

// 이 파일 안에서만 쓴다. 내보내면 컴포넌트가 아닌 것을 섞어 내보내게 되어 Fast Refresh 가 깨진다.
function useAppVersion() {
    const [app, setApp] = useState(null);
    useEffect(() => {
        let alive = true;
        readAppVersion().then((v) => { if (alive) setApp(v); });
        return () => { alive = false; };
    }, []);
    return app;
}

/** 쉬운 화면 하단: "앱 0.1.1 · 서버 1.0.0". 아무것도 모르면 그리지 않는다. */
export function VersionLine({ server, className = '' }) {
    const app = useAppVersion();
    const text = versionLabel({ app, server });
    if (!text) return null;
    return (
        <span className={className} title="문제를 물어볼 때 이 번호를 함께 알려주세요">{text}</span>
    );
}

/** 전문가 화면 머리글에 덧붙이는 " · 앱 v0.1.1". 브라우저에서는 그리지 않는다. */
export function AppVersionTag() {
    const app = useAppVersion();
    return app ? <> · 앱 v{app}</> : null;
}
