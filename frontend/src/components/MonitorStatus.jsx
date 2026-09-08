import React, { useEffect, useState } from 'react';
import { Activity, HelpCircle, X } from 'lucide-react';

const MONITOR_INFO = {
    AuthLogWatcher: {
        title: 'SSH/Auth 침입 탐지',
        desc: '/var/log/auth.log를 실시간 감시합니다.',
        details: [
            'SSH 로그인 실패 (Failed password, authentication failure) 감지',
            '존재하지 않는 사용자로의 접근 시도 (Invalid user) 감지',
            '30분 내 5회 이상 실패 시 자동 IP 차단 (BanManager)',
            'sudo 명령어 실행 및 권한 상승 감시',
            'root 세션 오픈 감지 (CRON/systemd 제외)',
        ],
    },
    NetworkWatcher: {
        title: '네트워크 연결 감시',
        desc: '15초 간격으로 시스템의 네트워크 연결 상태를 점검합니다.',
        details: [
            '새로운 리스닝 포트 오픈 감지 (알려진 서비스 포트 제외)',
            '새로운 외부 IP 연결 추적 (클라우드 IP는 파일 로그만)',
            '포트 스캔 탐지: 동일 IP가 5개 이상 서비스 포트 접촉 시 경고',
            'Private/Loopback 주소는 자동 제외',
        ],
    },
    MalwareMonitor: {
        title: '악성 프로세스 스캔',
        desc: '30초 간격으로 실행 중인 프로세스를 검사합니다.',
        details: [
            '알려진 악성 프로세스 이름 패턴 매칭 (cryptominer, reverse shell 등)',
            'PID 기반 중복 탐지 방지 (종료 후 재실행 시 재감지)',
            '탐지 시 CRITICAL 경보 + Slack 알림',
            'KILL PID 명령어 클립보드 복사 기능 제공',
        ],
    },
    IntelMonitor: {
        title: '위협 인텔 RSS 수집',
        desc: '1시간 간격으로 보안 위협 RSS 피드를 수집합니다.',
        details: [
            'The Hacker News, CISA, US-CERT 등 주요 보안 피드 구독',
            'GUID 기반 DB 중복 방지 (재시작 후에도 유지)',
            '새로운 위협 정보를 Threat Intel 패널에 표시',
            '한국어 자동 번역 제공',
        ],
    },
    ResourceMonitor: {
        title: '시스템 리소스 감시',
        desc: '30초 간격으로 CPU, 메모리, 디스크, 프로세스 수를 점검합니다.',
        details: [
            'CPU 90% 이상 2회 연속 시 WARNING',
            '메모리 85% 초과 시 WARNING',
            '디스크 90% 초과 시 WARNING',
            '프로세스 수 급증 (직전 대비 +50) 시 WARNING',
        ],
    },
    IntegrityMonitor: {
        title: '파일 무결성 감시',
        desc: '60초 간격으로 핵심 시스템 파일의 SHA-256 해시를 검증합니다.',
        details: [
            '감시 대상: /etc/passwd, /etc/shadow, /etc/sudoers, sshd_config, authorized_keys',
            '파일 변조 시 CRITICAL 경보 + Slack 알림',
            '파일 삭제 또는 새 파일 생성 감지',
            '최초 실행 시 베이스라인 해시 자동 생성',
        ],
    },
    UpdateMonitor: {
        title: '소프트웨어 업데이트 감시',
        desc: '/var/log/dpkg.log를 실시간 감시합니다.',
        details: [
            '패키지 설치 (install) → INFO',
            '패키지 업그레이드 (upgrade) → INFO (이전/이후 버전 표시)',
            '패키지 제거 (remove/purge) → WARNING',
            '시스템 시작 이후 새로운 dpkg 활동만 추적',
        ],
    },
};

export default function MonitorStatus() {
    const [monitors, setMonitors] = useState([]);
    const [openInfo, setOpenInfo] = useState(null);

    useEffect(() => {
        const fetch_ = async () => {
            try {
                const res = await fetch('http://localhost:8000/api/monitors');
                if (res.ok) setMonitors(await res.json());
            } catch (e) {
                console.error("Failed to fetch monitor status", e);
            }
        };
        fetch_();
        const id = setInterval(fetch_, 5000);
        return () => clearInterval(id);
    }, []);

    const info = openInfo ? MONITOR_INFO[openInfo] : null;

    return (
        <div className="border border-neon-green/30 bg-cyber-black/80 backdrop-blur-sm p-4 rounded-sm neon-border text-sm relative">
            <h3 className="text-neon-green font-bold flex items-center gap-2 mb-3 border-b border-neon-green/30 pb-2">
                <Activity className="w-4 h-4" />
                MONITOR_STATUS
            </h3>
            <ul className="space-y-2">
                {monitors.map((m) => {
                    const alive = m.running && m.thread_alive;
                    return (
                        <li key={m.name} className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <span className={`w-2 h-2 rounded-full flex-shrink-0 ${alive ? 'bg-neon-green animate-pulse' : 'bg-neon-red'}`} />
                                <span className="text-gray-300">{m.label}</span>
                                <button
                                    onClick={() => setOpenInfo(openInfo === m.name ? null : m.name)}
                                    className={`text-gray-600 hover:text-neon-green transition-colors ${openInfo === m.name ? 'text-neon-green' : ''}`}
                                    title="동작 설명 보기"
                                >
                                    <HelpCircle className="w-3.5 h-3.5" />
                                </button>
                            </div>
                            <span className={`text-xs font-mono ${alive ? 'text-neon-green' : 'text-neon-red'}`}>
                                {alive ? 'ACTIVE' : 'DOWN'}
                            </span>
                        </li>
                    );
                })}
                {monitors.length === 0 && (
                    <li className="text-gray-600 italic">모니터 상태 로딩 중...</li>
                )}
            </ul>

            {/* Info overlay */}
            {info && (
                <div className="mt-3 border border-neon-green/40 bg-cyber-gray/80 rounded p-3 animate-in fade-in">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-neon-green font-bold text-xs">{info.title}</span>
                        <button onClick={() => setOpenInfo(null)} className="text-gray-500 hover:text-gray-300">
                            <X className="w-3.5 h-3.5" />
                        </button>
                    </div>
                    <p className="text-gray-400 text-xs mb-2">{info.desc}</p>
                    <ul className="space-y-1">
                        {info.details.map((d, i) => (
                            <li key={i} className="text-xs text-gray-500 flex gap-1.5">
                                <span className="text-neon-green/60 flex-shrink-0">&#8250;</span>
                                <span>{d}</span>
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
}
