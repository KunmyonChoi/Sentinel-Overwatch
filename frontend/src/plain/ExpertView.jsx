import React, { useState } from 'react';
import { Icon, Card, Btn } from './ui';
import SystemHealth from '../components/SystemHealth';
import MonitorStatus from '../components/MonitorStatus';
import AccountsPanel from '../components/AccountsPanel';
import HardeningPanel from '../components/HardeningPanel';
import ExposurePanel from '../components/ExposurePanel';
import ConfigAuditPanel from '../components/ConfigAuditPanel';
import BlockListPanel from '../components/BlockListPanel';
import AlertsPanel from '../components/AlertsPanel';
import AlertFeed from '../components/AlertFeed';
import ThreatIntel from '../components/ThreatIntel';

/** 접힌 줄. 여기 요약은 펼치기 전에 비전문가가 읽는 곳이라 전문용어를 쓰지 않는다.
    열림 상태는 위에서 관리한다 — '모두 펼치기'로 예전 대시보드처럼 한눈에 볼 수 있어야 하기 때문이다. */
function Fold({ id, title, hint, right, isOpen, onToggle, children }) {
    const open = isOpen(id);
    const setOpen = () => onToggle(id);
    return (
        <>
            <div onClick={setOpen}
                className="flex items-center justify-between gap-4 px-5 py-4 border-t border-[#eef2f0] cursor-pointer hover:bg-[#f7fbf9] first:border-t-0">
                <div className="min-w-0">
                    <div className="text-[15px]">{title}</div>
                    <div className="text-[13px] text-calm-muted mt-0.5" style={{ wordBreak: 'keep-all' }}>{hint}</div>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                    {right && <span className="text-[13px] text-calm-muted">{right}</span>}
                    <Icon name="down" size={18} className={`text-calm-muted transition-transform ${open ? 'rotate-180' : ''}`} />
                </div>
            </div>
            {open && <div className="px-5 pb-5">{children}</div>}
        </>
    );
}

const FOLDS = ['exposure', 'config', 'accounts', 'blocked', 'monitors', 'hardening', 'alerts', 'health', 'feed', 'intel'];

export default function ExpertView({ stats, host, events, alerts, onChanged, tick }) {
    // 예전 대시보드의 장점은 '한 번에 다 보인다'였다. 그것을 되돌릴 수 있어야 한다.
    const [open, setOpen] = useState(new Set(['exposure']));
    const isOpen = (id) => open.has(id);
    const toggle = (id) => setOpen((s) => {
        const n = new Set(s);
        n.has(id) ? n.delete(id) : n.add(id);
        return n;
    });
    const allOpen = open.size >= FOLDS.length;
    const toggleAll = () => setOpen(allOpen ? new Set() : new Set(FOLDS));

    return (
        <div className="flex flex-col min-h-full">
            <div className="flex-1 px-6 sm:px-10 py-6 pb-12">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div className="text-[25px] font-semibold tracking-tight">자세히 보기</div>
                    <Btn kind="outline" className="h-11 px-4 text-[14px]" onClick={toggleAll}>
                        <Icon name={allOpen ? 'up' : 'down'} size={16} />
                        {allOpen ? '모두 접기' : '모두 펼치기'}
                    </Btn>
                </div>
                <div className="text-[14px] text-calm-muted mt-1.5 max-w-[74ch] leading-relaxed" style={{ wordBreak: 'keep-all' }}>
                    지킴이가 무엇을 보고 그렇게 판단했는지 전부 여기 있어요. 평소에는 접어둬요.
                    같은 내용을 한 화면에 펼쳐 보시려면 오른쪽 위에서 <b className="text-calm-ink">전문가 화면</b>으로 바꾸세요.
                </div>

                <Card className="mt-5 overflow-hidden">
                    <Fold id="exposure" isOpen={isOpen} onToggle={toggle} title="밖에서 들어올 수 있는 문"
                        hint="문마다 어디까지 열려 있는지, 잠금장치가 실제로 막고 있는지">
                        <ExposurePanel />
                        <div className="text-[12.5px] text-calm-muted mt-2.5" style={{ wordBreak: 'keep-all' }}>
                            홈에서 문이 <b className="text-calm-ink">1개</b>인데 여기 <b className="text-calm-ink">2</b>로 세어질 수 있어요.
                            문 하나가 두 갈래 길(IPv4·IPv6)로 나뉘어 있기 때문이에요.
                        </div>
                    </Fold>

                    <Fold id="config" isOpen={isOpen} onToggle={toggle} title="파일과 프로그램 설정"
                        hint="파일 자물쇠가 제대로 잠겨 있는지, 프로그램이 너무 큰 권한으로 돌지 않는지">
                        <ConfigAuditPanel />
                    </Fold>

                    <Fold id="accounts" isOpen={isOpen} onToggle={toggle} title="이 컴퓨터를 쓰는 사람"
                        hint="누가 쓸 수 있는 상태인지, 누가 관리자인지, 마지막으로 언제 들어왔는지">
                        <AccountsPanel />
                    </Fold>

                    <Fold id="blocked" isOpen={isOpen} onToggle={toggle} title="막은 상대" hint="들어오려다 막힌 곳과, 지금 막고 있는 목록">
                        <BlockListPanel tick={tick} />
                    </Fold>

                    <Fold id="monitors" isOpen={isOpen} onToggle={toggle} title="지킴이가 보고 있는 것"
                        hint="무엇을 어디서 보고 있는지, 못 보고 있는 것은 없는지">
                        <MonitorStatus />
                    </Fold>

                    <Fold id="hardening" isOpen={isOpen} onToggle={toggle} title="더 단단하게 만들 거리"
                        hint="지금 당장 문제는 아니지만 해두면 좋은 것들">
                        <HardeningPanel />
                    </Fold>

                    <Fold id="alerts" isOpen={isOpen} onToggle={toggle} title="알림 전체" hint="확인한 것까지 포함한 알림 목록">
                        <AlertsPanel alerts={alerts} onChanged={onChanged} />
                    </Fold>

                    <Fold id="health" isOpen={isOpen} onToggle={toggle} title="컴퓨터 상태" hint="처리 장치·메모리·저장 공간과 24시간 흐름">
                        <SystemHealth stats={stats} host={host} />
                    </Fold>

                    <Fold id="feed" isOpen={isOpen} onToggle={toggle} title="일어난 일 전부" hint="걸러내지 않은 기록. 수가 많아요">
                        <AlertFeed events={events} />
                    </Fold>

                    <Fold id="intel" isOpen={isOpen} onToggle={toggle} title="보안 소식" hint="내 컴퓨터에 해당하는 것만 위로 올려요">
                        <ThreatIntel />
                    </Fold>
                </Card>
            </div>
        </div>
    );
}
