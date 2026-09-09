// 예전 전문가 대시보드. 한 화면에 전부 펼쳐 놓는 레이아웃이라
// 익숙한 사람에게는 이쪽이 빠르다 — 그래서 없애지 않고 세 번째 화면으로 남겼다.
// (쉬운 화면 ↔ 자세히 보기 ↔ 이 화면. 전환은 App.jsx 가 기억한다.)
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

async function loadCore() {
  const [stats, events, alerts] = await Promise.all([
    api('/api/stats'),
    api('/api/events?limit=150'),
    api('/api/alerts?status=active'),
  ]);
  return { stats, events, alerts };
}

export default function Dashboard({ onGo }) {
  const [core, setCore] = useState({ stats: null, events: [], alerts: [] });
  const [host, setHost] = useState(null);
  const [needToken, setNeedToken] = useState(() => !getToken());
  const [tick, setTick] = useState(0);
  const aliveRef = useRef(true);

  // 주기 갱신: 토큰이 있을 때만. 401 이면 TokenGate 표시.
  useEffect(() => {
    aliveRef.current = true;
    const run = () => {
      if (!getToken()) return;
      loadCore()
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

  const { stats, events, alerts } = core;
  const isDefcon1 = stats?.status === 'DEFCON 1';
  const isDefcon3 = stats?.status === 'DEFCON 3';
  const badge = isDefcon1 ? 'text-neon-red border-neon-red' : isDefcon3 ? 'text-yellow-400 border-yellow-400' : 'text-neon-green border-neon-green';
  const refreshNow = () => loadCore().then(setCore).catch(() => {});

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
          {/* 어느 화면에서든 나머지 두 화면이 보이게 한다 — 되돌아갈 길을 찾아 헤매지 않도록. */}
          <div className="flex items-center gap-2 font-kr">
            <button onClick={() => onGo('plain')}
              className="px-3 py-1.5 rounded border border-neon-green/40 text-neon-green/90 hover:bg-neon-green/10 cursor-pointer">
              쉬운 화면
            </button>
            <button onClick={() => onGo('expert')}
              className="px-3 py-1.5 rounded border border-neon-green/25 text-neon-green/60 hover:bg-neon-green/10 cursor-pointer">
              자세히 보기
            </button>
          </div>
          <MaintenanceControl maintenance={stats?.maintenance} onChanged={refreshNow} />
          {stats && (
            <span className={`px-3 py-1 border rounded font-bold tracking-wider ${badge} ${isDefcon1 ? 'animate-pulse' : ''}`}>
              {stats.status} · {stats.status_ko}
            </span>
          )}
          <span className="text-neon-green/70 font-mono">{new Date().toLocaleTimeString('ko-KR', { hour12: false })}</span>
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
          <AlertsPanel alerts={alerts} onChanged={refreshNow} />
          <BlockListPanel tick={tick} />
          <AlertFeed events={events} />
        </section>
      </main>
    </div>
  );
}
