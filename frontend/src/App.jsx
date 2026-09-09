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

function App() {
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

export default App;
