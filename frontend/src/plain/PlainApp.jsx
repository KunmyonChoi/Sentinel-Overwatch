// 비전문가용 화면의 껍데기. 자료를 모아 사용자 언어로 바꾸고, 네 화면을 오간다.
// 백엔드는 건드리지 않는다 — 지금 있는 엔드포인트만 쓴다.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api, getToken } from '../api';
import TokenGate from '../components/TokenGate';
import MaintenanceControl from '../components/MaintenanceControl';
import Home from './Home';
import { Icon } from './ui';
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

export default function PlainApp({ mode = 'plain', onGo }) {
    // 홈과 '자세히 보기'는 App 이 기억하는 화면이라 바깥에서 시작 지점을 받는다.
    // 할 일 상세·기록은 잠깐 들르는 곳이라 여기서만 들고 있는다.
    const [view, setView] = useState(() => ({ name: mode === 'expert' ? 'expert' : 'home' }));
    const [needToken, setNeedToken] = useState(() => !getToken());
    const [d, setD] = useState({ stats: null, alerts: [], events: [], host: null, exposure: null, blocked: null, monitors: [], accounts: [] });
    const [tick, setTick] = useState(0);
    const [conn, setConn] = useState('loading');   // loading | ok | down
    const alive = useRef(true);

    const load = useCallback(async () => {
        if (!getToken()) return;
        const get = (p) => api(p).catch(() => null);
        const [stats, alerts, events, host, exposure, blocked, monitors, accounts] = await Promise.all([
            get('/api/stats'), get('/api/alerts?status=active'), get('/api/events?limit=60&include_simulation=false'),
            get('/api/host'), get('/api/exposure'), get('/api/blocked'), get('/api/monitors'),
            get('/api/accounts'),   // 붙여넣기용 글에서 계정 이름을 가리는 데 쓴다
        ]);
        if (!alive.current) return;
        if (stats) { setNeedToken(false); setConn('ok'); }
        else setConn('down');   // 못 읽었으면 '이상 없음'이라고 말하지 않는다
        setD((p) => ({
            stats: stats ?? p.stats, alerts: alerts ?? p.alerts, events: events ?? p.events,
            host: host ?? p.host, exposure: exposure ?? p.exposure, blocked: blocked ?? p.blocked,
            monitors: monitors ?? p.monitors,
            accounts: accounts?.accounts ?? p.accounts,
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
    const status = statusOf(d.stats, tasks.length, conn);

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
        doors: d.exposure ? doors : '—',
        doorsNote: !d.exposure ? '아직 확인하지 못했어요.'
            : doors === 0 ? '밖에서 들어올 수 있는 문이 없어요.'
            : d.exposure?.firewall?.available === false ? '잠겼는지 확인하지 못했어요. 자세히 보기에서 이유를 볼 수 있어요.'
                : '직접 열어두신 것이에요.',
        // 못 읽은 것을 '없음'이라고 말하지 않는다. 0 과 '모름'은 다른 말이다.
        updates: !d.host ? '—' : pending.available === false ? '확인 못 함' : (pending.security ? `${pending.security}개` : '없음'),
        updatesNote: !d.host ? '아직 확인하지 못했어요.'
            : pending.available === false ? '업데이트 목록을 읽지 못했어요.'
                : pending.security ? '보안에 관한 것이라 먼저 설치하는 게 좋아요.'
                    : pending.total ? `보안과 무관한 업데이트 ${pending.total}개가 남아 있어요.` : '밀린 것이 없어요.',
        blockedLabel: tried !== null ? '막은 접속 시도' : '지금 막고 있는 상대',
        blocked: !d.blocked ? '—' : tried !== null ? `${tried}번` : `${nowBlocking}곳`,
        blockedNote: !d.blocked ? '아직 확인하지 못했어요.'
            : tried !== null
                ? (tried ? '모두 들어오지 못했어요. 따로 하실 일은 없어요.' : '아직 막을 일이 없었어요.')
                : (nowBlocking ? '들어오려다 막힌 곳이에요. 따로 하실 일은 없어요.' : '지금 막고 있는 곳이 없어요.'),
    };

    const go = (name) => {
        setView({ name });
        // 홈과 자세히 보기만 기억한다. 상세·기록에서 새로고침하면 홈으로 돌아오는 게 맞다.
        if (name === 'home') onGo?.('plain');
        if (name === 'expert') onGo?.('expert');
    };
    const atHome = view.name === 'home';
    const atExpert = view.name === 'expert';
    const openTask = (task) => setView({ name: 'task', task });

    return (
        <div className="min-h-screen bg-calm-bg text-calm-ink font-kr">
            {needToken && <TokenGate />}
            <div className="mx-auto max-w-[1080px] min-h-screen bg-calm-bg flex flex-col">
                {/* 어느 화면에서든 같은 자리. 전문가 화면을 홈까지 돌아가야만 열 수 있으면 안 된다. */}
                <div className="flex items-center justify-between gap-3 px-6 sm:px-10 py-3.5 border-b border-calm-line">
                    {atHome ? (
                        <div className="flex items-center gap-2.5 min-w-0">
                            <span className="text-calm-accent shrink-0"><Icon name="shield" size={22} /></span>
                            <span className="text-[16px] font-semibold tracking-tight truncate">내 컴퓨터 지킴이</span>
                        </div>
                    ) : (
                        <button onClick={() => go('home')}
                            className="h-11 -ml-3 px-3 rounded-lg inline-flex items-center gap-1.5 text-[14px] text-calm-muted hover:bg-calm-panel2 cursor-pointer font-kr">
                            <Icon name="back" size={17} />돌아가기
                        </button>
                    )}
                    <div className="flex items-center gap-3 shrink-0">
                        {atHome && (
                            <span className="hidden sm:flex items-center gap-1.5 text-calm-muted text-[13px]">
                                <Icon name="clock" size={15} />{lastCheck}
                            </span>
                        )}
                        <button onClick={() => go(atExpert ? 'home' : 'expert')}
                            className={`h-11 px-3 rounded-lg inline-flex items-center gap-1.5 text-[14px] cursor-pointer font-kr
                                ${atExpert ? 'text-calm-accent bg-calm-accent-soft' : 'text-calm-muted hover:bg-calm-panel2'}`}>
                            <Icon name="eye" size={16} />{atExpert ? '쉬운 화면으로' : '자세히 보기'}
                        </button>
                        {/* 예전 전문가 화면. 익숙한 사람은 여기서 바로 건너뛴다. */}
                        <button onClick={() => onGo?.('dashboard')} title="예전 전문가 화면 — 한 화면에 전부 펼쳐 보기"
                            className="h-11 px-3 rounded-lg inline-flex items-center gap-1.5 text-[14px] cursor-pointer font-kr text-calm-muted hover:bg-calm-panel2">
                            <Icon name="grid" size={16} /><span className="hidden sm:inline">대시보드</span>
                        </button>
                    </div>
                </div>

                {view.name === 'home' && (
                    <Home status={status} tasks={tasks} facts={facts} onOpenTask={openTask} onGo={go} />
                )}
                {view.name === 'task' && (
                    <TaskDetail task={tasks.find((t) => t.id === view.task.id) || view.task}
                        onBack={() => go('home')} onChanged={load} host={d.host} accounts={d.accounts} />
                )}
                {view.name === 'history' && <HistoryView />}
                {view.name === 'expert' && (
                    <ExpertView stats={d.stats} host={d.host} events={d.events}
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
