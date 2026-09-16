// 전문가 모드. 예전 대시보드 그대로다 — 한 화면에 전부 펼쳐 놓는 레이아웃이라
// 익숙한 사람에게는 이쪽이 빠르다.
//
// 초보자 모드(쉬운 화면·자세히 보기)와는 ModeSwitch 로만 오간다. 레이아웃도
// 폴링 주기도 손대지 않았다 — '예전 그대로'가 이 화면의 존재 이유이기 때문이다.
import React, { useEffect, useRef, useState } from 'react';
import SystemHealth from './components/SystemHealth';
import AlertFeed from './components/AlertFeed';
import AlertsPanel from './components/AlertsPanel';
import ThreatIntel from './components/ThreatIntel';
import MonitorStatus from './components/MonitorStatus';
import BlockListPanel from './components/BlockListPanel';
import HighlightKorean from './components/HighlightKorean';
import TokenGate from './components/TokenGate';
import HardeningPanel from './components/HardeningPanel';
import MaintenanceControl from './components/MaintenanceControl';
import AccountsPanel from './components/AccountsPanel';
import ExposurePanel from './components/ExposurePanel';
import ConfigAuditPanel from './components/ConfigAuditPanel';
import { api, getToken } from './api';
import { ShieldAlert } from 'lucide-react';
import ModeSwitch from './ModeSwitch';
import InstanceBadge from './InstanceBadge';

// 목록은 서버에서 limit 으로 잘린다. 그래서 전체 건수도 같이 받는다 — 머리글 숫자를
// '불러온 행'으로 세면 목록이 잘리는 순간 시스템 상태 패널과 다른 숫자를 말하게 된다.
const ALERT_PAGE = 100;
const EVENT_PAGE = 150;

async function loadCore(limits) {
  const [stats, events, alerts, alertCount, eventCount] = await Promise.all([
    api('/api/stats'),
    api(`/api/events?limit=${limits.events}`),
    api(`/api/alerts?status=active&limit=${limits.alerts}`),
    api('/api/alerts/count?status=active'),
    api('/api/events/count'),
  ]);
  return { stats, events, alerts, alertCount, eventCount };
}

export default function Dashboard({ onMode }) {
  const [core, setCore] = useState({ stats: null, events: [], alerts: [], alertCount: null, eventCount: null });
  const [host, setHost] = useState(null);
  const [needToken, setNeedToken] = useState(() => !getToken());
  const [tick, setTick] = useState(0);
  const [limits, setLimits] = useState({ alerts: ALERT_PAGE, events: EVENT_PAGE });
  const aliveRef = useRef(true);
  // 폴링 타이머는 한 번만 만들고 최신 limit 은 ref 로 읽는다 — '더 보기'로 늘린 범위가
  // 다음 갱신에서 100건으로 되돌아가지 않아야 한다.
  const limitsRef = useRef(limits);
  useEffect(() => { limitsRef.current = limits; }, [limits]);

  // 주기 갱신: 토큰이 있을 때만. 401 이면 TokenGate 표시.
  useEffect(() => {
    aliveRef.current = true;
    const run = () => {
      if (!getToken()) return;
      loadCore(limitsRef.current)
        .then((d) => { if (aliveRef.current) { setCore(d); setNeedToken(false); } })
        .catch((err) => { if (err.status !== 401) console.error('refresh failed', err); });
      setTick((t) => t + 1);
    };
    const onUnauthorized = () => setNeedToken(true);
    const onToken = () => { setNeedToken(false); run(); };
    window.addEventListener('secdash:unauthorized', onUnauthorized);
    window.addEventListener('secdash:token-changed', onToken);
    const t0 = setTimeout(run, 0);
    const iv = setInterval(run, 5000);
    return () => {
      aliveRef.current = false;
      clearTimeout(t0); clearInterval(iv);
      window.removeEventListener('secdash:unauthorized', onUnauthorized);
      window.removeEventListener('secdash:token-changed', onToken);
    };
  }, []);

  useEffect(() => {
    if (needToken) return;
    let alive = true;
    const load = () => api('/api/host').then((h) => { if (alive) setHost(h); }).catch(() => {});
    const t0 = setTimeout(load, 0);
    const iv = setInterval(load, 60000);
    return () => { alive = false; clearTimeout(t0); clearInterval(iv); };
  }, [needToken]);

  const { stats, events, alerts, alertCount, eventCount } = core;
  const isDefcon1 = stats?.status === 'DEFCON 1';
  const isDefcon3 = stats?.status === 'DEFCON 3';
  const badge = isDefcon1 ? 'text-neon-red border-neon-red' : isDefcon3 ? 'text-yellow-400 border-yellow-400' : 'text-neon-green border-neon-green';
  const refreshNow = () => loadCore(limitsRef.current).then(setCore).catch(() => {});
  // 더 보기: 잘린 목록을 더 불러온다. 서버가 한 번에 보내는 최대치(max_limit)를 넘기지 않는다.
  const loadMore = (key) => {
    const max = (key === 'alerts' ? alertCount?.max_limit : eventCount?.max_limit) || 0;
    const step = key === 'alerts' ? ALERT_PAGE : EVENT_PAGE;
    const next = Math.min(limits[key] + step, max || limits[key]);
    if (next <= limits[key]) return;
    const nextLimits = { ...limits, [key]: next };
    setLimits(nextLimits);
    loadCore(nextLimits).then(setCore).catch(() => {});
  };

  return (
    <div className="min-h-screen cyber-grid p-6 flex flex-col gap-6">
      {needToken && <TokenGate />}
      <header className="flex items-center justify-between border-b border-neon-green/30 pb-4 mb-2 flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <ShieldAlert className={`w-8 h-8 ${isDefcon1 ? 'text-neon-red animate-pulse' : 'text-neon-green'}`} />
          <div>
            <h1 className="text-3xl font-bold tracking-widest text-neon-green neon-text">SENTINEL // OVERWATCH</h1>
            {host && (
              <div className="text-xs text-gray-500 font-mono mt-1">
                {host.hostname} · v{host.version} · {host.os} · 실행 계정 {host.running_as?.user || host.running_as?.uid}{host.running_as?.root ? ' (root)' : ''}
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <MaintenanceControl maintenance={stats?.maintenance} onChanged={refreshNow} />
          {stats && (
            <span className={`px-3 py-1 border rounded font-bold tracking-wider ${badge} ${isDefcon1 ? 'animate-pulse' : ''}`}>
              {stats.status} · {stats.status_ko}
            </span>
          )}
          <span className="text-neon-green/70 font-mono">{new Date().toLocaleTimeString('ko-KR', { hour12: false })}</span>
          <InstanceBadge host={host} tone="neon" />
          {/* 초보자 화면과 같은 조각, 같은 자리(오른쪽 끝). 여기서 바뀌는 것은 모드뿐이다. */}
          <ModeSwitch mode="dashboard" onChange={onMode} tone="neon" />
        </div>
      </header>

      <main className="grid grid-cols-1 lg:grid-cols-3 gap-6 flex-1 min-h-0">
        <section className="lg:col-span-1 flex flex-col gap-6 overflow-y-auto pr-2 scrollbar-hide">
          <HighlightKorean />
          <SystemHealth stats={stats} host={host} />
          <MonitorStatus />
          <ExposurePanel />
          <ConfigAuditPanel />
          <AccountsPanel />
          <HardeningPanel />
          <ThreatIntel />
        </section>
        <section className="lg:col-span-2 flex flex-col min-h-[500px] gap-4">
          <AlertsPanel alerts={alerts} counts={alertCount} limit={limits.alerts} onLoadMore={() => loadMore('alerts')} onChanged={refreshNow} />
          <BlockListPanel tick={tick} />
          <AlertFeed events={events} counts={eventCount} limit={limits.events} onLoadMore={() => loadMore('events')} />
        </section>
      </main>
    </div>
  );
}
