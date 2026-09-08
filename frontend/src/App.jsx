import React, { useEffect, useState } from 'react';
import SystemHealth from './components/SystemHealth';
import AlertFeed from './components/AlertFeed';
import ThreatIntel from './components/ThreatIntel';
import MonitorStatus from './components/MonitorStatus';
import BlockListPanel from './components/BlockListPanel';
import HighlightKorean from './components/HighlightKorean';
import { ShieldAlert } from 'lucide-react';

function App() {
  const [events, setEvents] = useState([]);
  const [stats, setStats] = useState(null);

  const fetchData = async () => {
    try {
      const eventRes = await fetch('http://localhost:8000/api/events');
      const eventData = await eventRes.json();
      setEvents(eventData);

      const statsRes = await fetch('http://localhost:8000/api/stats');
      const statsData = await statsRes.json();
      setStats(statsData);
    } catch (e) {
      console.error("Failed to fetch data", e);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000); // Poll every 5s
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen cyber-grid p-6 flex flex-col gap-6">
      <header className="flex items-center justify-between border-b border-neon-green/30 pb-4 mb-2">
        <div className="flex items-center gap-3">
          <ShieldAlert className="w-8 h-8 text-neon-green animate-pulse" />
          <h1 className="text-3xl font-bold tracking-widest text-neon-green neon-text">
            SENTINEL // OVERWATCH
          </h1>
        </div>
        <div className="text-sm text-neon-green/70">
          SYS.TIME: {new Date().toLocaleTimeString()}
        </div>
      </header>

      <main className="grid grid-cols-1 md:grid-cols-3 gap-6 flex-1 min-h-0">
        {/* Left Column: System Status */}
        <section className="md:col-span-1 flex flex-col gap-6 overflow-y-auto pr-2 scrollbar-hide">
          <HighlightKorean />
          <SystemHealth stats={stats} />
          <MonitorStatus />
          <ThreatIntel />
        </section>

        {/* Right Column: Alert Feed */}
        <section className="md:col-span-2 h-full flex flex-col min-h-[500px] gap-4">
          <BlockListPanel />
          <AlertFeed events={events} />
        </section>
      </main>
    </div>
  );
}

export default App;
