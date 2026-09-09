// 비전문가용 화면의 껍데기. 자료를 모아 사용자 언어로 바꾸고, 네 화면을 오간다.
// 백엔드는 건드리지 않는다 — 지금 있는 엔드포인트만 쓴다.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api, getToken } from '../api';
import TokenGate from '../components/TokenGate';
import MaintenanceControl from '../components/MaintenanceControl';
import Home from './Home';
import { doorCount } from './tokens';
import TaskDetail from './TaskDetail';
import HistoryView from './HistoryView';
import ExpertView from './ExpertView';
import { buildTasks, statusOf } from './tasks';

function agoKo(iso) {
    if (!iso) return '확인 중이에요';
    const sec = Math.max(0, (Date.now() - new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z').getTime()) / 1000);
    if (sec < 90) return '방금 확인했어요';
    if (sec < 3600) return `${Math.round(sec / 60)}분 전에 확인했어요`;
    if (sec < 86400) return `${Math.round(sec / 3600)}시간 전에 확인했어요`;
    return `${Math.round(sec / 86400)}일 전에 확인했어요`;
}

export default function PlainApp() {
    const [view, setView] = useState({ name: 'home' });
    const [needToken, setNeedToken] = useState(() => !getToken());
    const [d, setD] = useState({ stats: null, alerts: [], events: [], host: null, exposure: null, blocked: null, monitors: [] });
    const [tick, setTick] = useState(0);
    const alive = useRef(true);

    const load = useCallback(async () => {
        if (!getToken()) return;
        const get = (p) => api(p).catch(() => null);
        const [stats, alerts, events, host, exposure, blocked, monitors] = await Promise.all([
            get('/api/stats'), get('/api/alerts?status=active'), get('/api/events?limit=60&include_simulation=false'),
            get('/api/host'), get('/api/exposure'), get('/api/blocked'), get('/api/monitors'),
        ]);
        if (!alive.current) return;
        if (stats) setNeedToken(false);
        setD((p) => ({
            stats: stats ?? p.stats, alerts: alerts ?? p.alerts, events: events ?? p.events,
            host: host ?? p.host, exposure: exposure ?? p.exposure, blocked: blocked ?? p.blocked,
            monitors: monitors ?? p.monitors,
        }));
        setTick((t) => t + 1);
    }, []);

    useEffect(() => {
        alive.current = true;
        const onUnauth = () => setNeedToken(true);
        const onToken = () => { setNeedToken(false); load(); };
        window.addEventListener('secdash:unauthorized', onUnauth);
        window.addEventListener('secdash:token-changed', onToken);
        const first = setTimeout(load, 0);   // 렌더 직후가 아니라 다음 틱에 부른다
        const iv = setInterval(load, 15000);
        return () => {
            alive.current = false; clearTimeout(first); clearInterval(iv);
            window.removeEventListener('secdash:unauthorized', onUnauth);
            window.removeEventListener('secdash:token-changed', onToken);
        };
    }, [load]);

    const tasks = buildTasks(d.alerts);
    const status = statusOf(d.stats, tasks.length);

    // 홈의 안심 정보 세 칸
    const pending = d.host?.pending_updates || {};
    const doors = doorCount(d.exposure);
    // fail2ban 통계를 읽을 수 있을 때만 '시도 횟수'라고 말한다.
    // 못 읽으면 지금 막고 있는 상대 수를 보여주고, 그 사실을 그대로 적는다.
    const blockedStats = d.blocked?.fail2ban?.stats || {};
    const tried = blockedStats.total_failed ?? blockedStats.total_banned ?? null;
    const nowBlocking = (d.blocked?.items || []).filter((b) => b.status === 'ACTIVE').length;
    const lastCheck = agoKo((d.monitors || []).map((m) => m.last_check_at).filter(Boolean).sort().at(-1));

    const facts = {
        doors,
        doorsNote: doors === 0 ? '밖에서 들어올 수 있는 문이 없어요.'
            : d.exposure?.firewall?.available === false ? '잠겼는지 확인하지 못했어요. 자세히 보기에서 이유를 볼 수 있어요.'
                : '직접 열어두신 것이에요.',
        updates: pending.available === false ? '확인 못 함' : (pending.security ? `${pending.security}개` : '없음'),
        updatesNote: pending.available === false ? '업데이트 목록을 읽지 못했어요.'
            : pending.security ? '보안에 관한 것이라 먼저 설치하는 게 좋아요.'
                : pending.total ? `보안과 무관한 업데이트 ${pending.total}개가 남아 있어요.` : '밀린 것이 없어요.',
        blockedLabel: tried !== null ? '막은 접속 시도' : '지금 막고 있는 상대',
        blocked: tried !== null ? `${tried}번` : `${nowBlocking}곳`,
        blockedNote: tried !== null
            ? (tried ? '모두 들어오지 못했어요. 따로 하실 일은 없어요.' : '아직 막을 일이 없었어요.')
            : (nowBlocking ? '들어오려다 막힌 곳이에요. 따로 하실 일은 없어요.' : '지금 막고 있는 곳이 없어요.'),
    };

    const go = (name) => setView({ name });
    const openTask = (task) => setView({ name: 'task', task });

    return (
        <div className="min-h-screen bg-calm-bg text-calm-ink font-kr">
            {needToken && <TokenGate />}
            <div className="mx-auto max-w-[1080px] min-h-screen bg-calm-bg flex flex-col">
                {view.name === 'home' && (
                    <Home status={status} tasks={tasks} facts={facts} lastCheck={lastCheck}
                        onOpenTask={openTask} onGo={go} />
                )}
                {view.name === 'task' && (
                    <TaskDetail task={tasks.find((t) => t.id === view.task.id) || view.task}
                        onBack={() => go('home')} onChanged={load} host={d.host} />
                )}
                {view.name === 'history' && <HistoryView onBack={() => go('home')} />}
                {view.name === 'expert' && (
                    <ExpertView onBack={() => go('home')} stats={d.stats} host={d.host} events={d.events}
                        alerts={d.alerts} onChanged={load} tick={tick} />
                )}
            </div>

            {/* 점검 모드는 어느 화면에서나 필요하다 */}
            <div className="fixed bottom-4 right-4 z-10">
                <MaintenanceControl maintenance={d.stats?.maintenance} onChanged={load} />
            </div>
        </div>
    );
}
