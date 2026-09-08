import React, { useEffect, useState } from 'react';
import { Activity, HelpCircle, X, ClipboardCopy } from 'lucide-react';
import { api, fmtTime } from '../api';

const MONITOR_INFO = {
    AuthLogWatcher: {
        desc: 'auth.log 를 tail 하며 SSH/sudo/계정 변경을 구조화해 기록합니다.',
        details: ['브루트포스: 같은 IP 가 30분 내 5회 이상 실패 → 경고 알림 + fail2ban 차단 요청', '실패 이력이 있는 IP 에서 로그인 성공 → 긴급 알림', '처음 보는 공인 IP 로그인 성공, root 직접 로그인 → 경고 알림', 'sudo 실패, useradd/usermod/그룹 추가 → 알림', '로그를 읽을 수 없으면 대체 파일로 넘어가지 않고 DOWN 으로 표시'],
    },
    Fail2banSync: {
        desc: 'fail2ban 이 실제로 차단한 IP 목록을 30초마다 동기화합니다. 차단의 진실 원천은 fail2ban 입니다.',
        details: ['root 가 아니면 sudo -n fail2ban-client 로 호출 (deploy/sudoers-secdash)', '연동 불가 시 자동 차단 대신 "차단 권고" 로 기록'],
    },
    NetworkWatcher: {
        desc: '15초마다 소켓 상태를 점검합니다.',
        details: ['외부 인터페이스에 새 리스닝 포트 → 경고 알림 (프로세스/사용자/실행 파일 포함)', '루프백 리스너는 정보 이벤트만', '새 외부 연결은 프로세스명과 함께 정보 이벤트', '포트 스캔 휴리스틱(SYN_RECV/ESTABLISHED 기반, 신뢰도 낮음)'],
    },
    ProcessAudit: {
        desc: '30초마다 프로세스를 검사합니다. 이름 부분 일치로 "악성코드" 라 부르지 않습니다.',
        details: ['실행 파일 이름이 nmap/hydra/tcpdump 등 도구와 정확히 일치 → 경고(감사)', '셸의 표준 입출력이 소켓 → 긴급 (리버스 셸)', '/tmp, /dev/shm 에서 실행 → 경고 (root 면 긴급)', '실행 파일이 삭제됨 → 정보 (업그레이드 후 재시작 필요 가능)'],
    },
    IntegrityMonitor: {
        desc: '60초마다 핵심 파일 SHA-256 을 검증하고 기준선을 DB 에 보관합니다.',
        details: ['passwd/group/shadow/sudoers(.d)/sshd_config(.d)/authorized_keys/ld.so.preload/hosts', '변경 시 diff 와 의미 요약(추가된 키, 추가된 계정)을 알림에 첨부', '서비스가 꺼져 있던 동안의 변경도 시작 시 탐지', '읽을 수 없는 파일은 "정상" 이 아니라 DEGRADED 로 표시'],
    },
    PersistenceMonitor: {
        desc: '5분마다 cron, systemd 유닛, SUID/SGID 바이너리 변화를 확인합니다.',
        details: ['새/변경된 cron 파일과 systemd 유닛 → 경고 (curl|sh, /dev/tcp 패턴이면 긴급)', '새 SUID/SGID 바이너리 → 긴급'],
    },
    UpdateMonitor: {
        desc: 'dpkg.log 를 tail 하고 6시간마다 apt 미적용 업데이트를 확인합니다.',
        details: ['패키지 제거 → 경고, 보안 패키지(fail2ban, openssh-server 등) 제거 → 긴급', '미적용 보안 업데이트가 있으면 경고 알림, 적용되면 자동 해결'],
    },
    ResourceMonitor: { desc: '30초마다 CPU/메모리/디스크/프로세스 수를 점검합니다.', details: ['CPU 90% 2회 연속, 메모리 85%, 디스크 90%, 프로세스 +50 → 경고 알림', '조건 해소 시 자동 해결'] },
    IntelMonitor: {
        desc: '1시간마다 보안 뉴스와 Ubuntu 보안 공지(USN)를 수집합니다.',
        details: ['USN 의 영향 패키지/수정 버전을 이 호스트의 설치 버전과 대조 → 취약하면 경고 알림', '패키지 목록은 외부로 전송하지 않음 (공개 URL 읽기만)', '뉴스 제목만 외부 번역/긴급도 평가에 사용 (호스트 로그는 절대 전송 안 함)'],
    },
};

const HEALTH = {
    ok: { dot: 'bg-neon-green', text: 'text-neon-green', label: '정상' },
    degraded: { dot: 'bg-yellow-400', text: 'text-yellow-400', label: '제한' },
    down: { dot: 'bg-neon-red', text: 'text-neon-red', label: '중단' },
    starting: { dot: 'bg-gray-500', text: 'text-gray-400', label: '시작 중' },
};

export default function MonitorStatus() {
    const [monitors, setMonitors] = useState([]);
    const [openInfo, setOpenInfo] = useState(null);

    useEffect(() => {
        const load = async () => { try { setMonitors(await api('/api/monitors')); } catch { /* ignore */ } };
        load();
        const id = setInterval(load, 5000);
        return () => clearInterval(id);
    }, []);

    const problems = monitors.filter(m => m.health !== 'ok');

    return (
        <div className="border border-neon-green/30 bg-cyber-black/80 backdrop-blur-sm p-4 rounded-sm neon-border text-sm relative">
            <h3 className="text-neon-green font-bold flex items-center gap-2 mb-3 border-b border-neon-green/30 pb-2">
                <Activity className="w-4 h-4" /> 모니터 상태
                {problems.length > 0 && <span className="text-xs font-normal text-yellow-400 ml-auto">탐지 공백 {problems.length}</span>}
            </h3>
            <ul className="space-y-2">
                {monitors.map((m) => {
                    const h = HEALTH[m.health] || HEALTH.starting;
                    return (
                        <li key={m.name}>
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2 min-w-0">
                                    <span className={`w-2 h-2 rounded-full flex-shrink-0 ${h.dot} ${m.health === 'ok' ? 'animate-pulse' : ''}`} />
                                    <span className="text-gray-300 truncate">{m.label}</span>
                                    <button onClick={() => setOpenInfo(openInfo === m.name ? null : m.name)} className={`text-gray-600 hover:text-neon-green ${openInfo === m.name ? 'text-neon-green' : ''}`} title="동작 설명">
                                        <HelpCircle className="w-3.5 h-3.5" />
                                    </button>
                                </div>
                                <span className={`text-xs font-mono ${h.text} flex-shrink-0`} title={m.last_event_at ? `마지막 이벤트 ${fmtTime(m.last_event_at)}` : ''}>{h.label}</span>
                            </div>
                            {m.health !== 'ok' && m.health !== 'starting' && (
                                <div className="ml-4 mt-1 text-xs text-gray-400 border-l border-gray-700 pl-2" style={{ wordBreak: 'keep-all' }}>
                                    <div className={h.text}>{m.health_reason}</div>
                                    {m.fix_hint && (
                                        <div className="text-gray-500 flex items-start gap-1 mt-0.5">
                                            <span className="flex-1">해결: {m.fix_hint}</span>
                                            <button onClick={() => navigator.clipboard.writeText(m.fix_hint)} className="text-gray-600 hover:text-neon-green flex-shrink-0" title="복사"><ClipboardCopy className="w-3 h-3" /></button>
                                        </div>
                                    )}
                                </div>
                            )}
                            {openInfo === m.name && MONITOR_INFO[m.name] && (
                                <div className="ml-4 mt-2 border border-neon-green/40 bg-cyber-gray/80 rounded p-3">
                                    <div className="flex items-center justify-between mb-1">
                                        <span className="text-neon-green font-bold text-xs">{m.label}</span>
                                        <button onClick={() => setOpenInfo(null)} className="text-gray-500 hover:text-gray-300"><X className="w-3.5 h-3.5" /></button>
                                    </div>
                                    <p className="text-gray-400 text-xs mb-2" style={{ wordBreak: 'keep-all' }}>{MONITOR_INFO[m.name].desc}</p>
                                    <div className="text-[10px] text-gray-600 font-mono mb-2 break-all">소스: {m.source}</div>
                                    <ul className="space-y-1">
                                        {MONITOR_INFO[m.name].details.map((d, i) => (
                                            <li key={i} className="text-xs text-gray-500 flex gap-1.5" style={{ wordBreak: 'keep-all' }}><span className="text-neon-green/60 flex-shrink-0">›</span><span>{d}</span></li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                        </li>
                    );
                })}
                {monitors.length === 0 && <li className="text-gray-600 italic">모니터 상태 로딩 중...</li>}
            </ul>
        </div>
    );
}
