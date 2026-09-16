// 홈에서 바로 할 수 있는 조치. 전문가 화면에만 있던 USB 차단 해제와 계정 잠금을 여기로 올린다.
//
// 왜 홈에 두는가: 자세히 보기 → 항목 펼치기를 지나야 나왔다. 자주 쓸 수 있는 조작인데 경로가
// 가장 길었다 (목업 비교에서 세 걸음 → 한 걸음).
//
// 왜 버튼이 바로 실행하지 않는가: 이 조작들은 root 권한이 필요하고, 지킴이는 그 권한을 갖고
// 있지 않다. 그래서 하는 일은 '터미널에 붙여 넣을 명령을 알려주는 것'뿐이다. 버튼 이름과
// 설명이 그 사실을 그대로 말한다 (원칙 2: 한 일만 말한다).
//
// 줄은 최대 세 개까지만 둔다. 더 늘어나면 홈이 목록이 되고, '이상 없음'인 날의 여백이 사라진다.
import React, { useState } from 'react';
import { Icon, Card, Btn } from './ui';
import { copyText } from './brief';

const UNUSED_DAYS = 180;   // 전문가 화면의 계정 패널과 같은 기준
const MAX_ROWS = 3;

/** 명령 한 줄 + 왜 그런지 + 복사. 자동 복사가 막히면 직접 끌어 복사하도록 글을 남긴다. */
function CommandPanel({ cmd, why }) {
    const [state, setState] = useState('idle');   // idle | ok | fail

    const copy = async () => {
        const ok = await copyText(cmd);
        setState(ok ? 'ok' : 'fail');
        setTimeout(() => setState('idle'), 2500);
    };

    return (
        <div className="mt-3 rounded-lg border border-dashed border-calm-line2 bg-calm-bg p-4">
            <pre className="text-[12.5px] leading-relaxed font-mono whitespace-pre-wrap select-all bg-calm-panel border border-calm-line rounded-md px-3 py-2.5">{cmd}</pre>
            <div className="text-[13px] text-calm-muted mt-2.5 leading-relaxed" style={{ wordBreak: 'keep-all' }}>{why}</div>
            <div className="flex items-center gap-2.5 mt-3 flex-wrap">
                <Btn kind="primary" onClick={copy} className="h-10">
                    <Icon name="copy" size={15} />
                    {state === 'ok' ? '복사했어요' : state === 'fail' ? '복사 실패' : '명령 복사하기'}
                </Btn>
                <span className="text-[12.5px] text-calm-muted" style={{ wordBreak: 'keep-all' }}>
                    {state === 'fail'
                        ? '자동 복사가 막혀 있어요. 위 글을 직접 끌어서 복사해 주세요.'
                        : '터미널에 붙여 넣고 Enter 를 누르면 적용돼요.'}
                </span>
            </div>
        </div>
    );
}

function Row({ icon, title, pill, pillTone, what, actions, openId, setOpenId }) {
    const toneCls = pillTone === 'warn'
        ? 'text-calm-warn border-calm-warn bg-calm-warn-soft'
        : 'text-calm-accent2 border-calm-accent bg-calm-accent-soft';
    return (
        <div className="px-5 py-4 border-t border-calm-line first:border-t-0">
            <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="flex items-start gap-3 min-w-[240px] flex-1">
                    <span className="text-calm-muted mt-0.5 shrink-0"><Icon name={icon} size={19} /></span>
                    <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-[15.5px] font-semibold">{title}</span>
                            {pill && <span className={`text-[12px] border rounded-full px-2 py-0.5 whitespace-nowrap ${toneCls}`}>{pill}</span>}
                        </div>
                        <div className="text-[13.5px] text-calm-muted mt-1 leading-relaxed" style={{ wordBreak: 'keep-all' }}>{what}</div>
                    </div>
                </div>
                <div className="flex items-center gap-2 flex-wrap shrink-0">
                    {actions.map((a) => (
                        <Btn key={a.id} kind={a.primary ? 'outline' : 'ghost'}
                            aria-expanded={openId === a.id}
                            onClick={() => setOpenId(openId === a.id ? null : a.id)}>
                            {a.label}
                        </Btn>
                    ))}
                </div>
            </div>
            {actions.filter((a) => a.id === openId).map((a) => (
                <CommandPanel key={a.id} cmd={a.cmd} why={a.why} />
            ))}
        </div>
    );
}

/**
 * 홈의 '지금 할 수 있는 것'.
 *
 * host·accounts 를 못 읽었으면 아무것도 그리지 않는다. 빈 줄을 만들어 '할 수 있는 일이 없다'고
 * 말하는 것보다, 자리 자체를 비우는 편이 덜 거짓말이다.
 */
export default function QuickActions({ host, accounts = [], asOf = 0 }) {
    const [openId, setOpenId] = useState(null);
    const rows = [];
    const usb = host?.usb_storage;
    const cmds = usb?.commands || {};

    if (usb && usb.state !== 'unknown') {
        const blocked = usb.state === 'blocked';
        const temporarily = usb.state === 'temporarily_unblocked';
        const actions = [];
        if (blocked && cmds.temp_unblock) {
            actions.push({
                id: 'usb-temp', primary: true, label: '잠깐 쓰기',
                cmd: cmds.temp_unblock,
                why: '이 컴퓨터를 다시 켜면 자동으로 다시 막혀요. 쓰고 나서 바로 막으려면 아래 ‘다시 막기’를 누르세요.',
            });
        }
        if ((temporarily || !blocked) && cmds.reblock) {
            actions.push({
                id: 'usb-reblock', primary: true, label: '다시 막기',
                cmd: cmds.reblock,
                why: 'USB 저장장치를 지금 바로 다시 막아요. 꽂아둔 USB 가 있으면 먼저 빼세요.',
            });
        }
        if (blocked && cmds.permanent_unblock) {
            actions.push({
                id: 'usb-perm', label: '계속 쓰기로 바꾸기',
                cmd: cmds.permanent_unblock,
                why: '다음에 컴퓨터를 켜도 USB 가 열려 있어요. 파일을 몰래 빼가거나 넣는 것을 막지 못하게 되니, 꼭 필요할 때만 바꾸세요.',
            });
        }
        if (!blocked && cmds.permanent_block) {
            actions.push({
                id: 'usb-set-block', label: '항상 막기로 바꾸기',
                cmd: cmds.permanent_block,
                why: '다음에 켤 때부터도 USB 저장장치를 막아요.',
            });
        }
        if (actions.length) {
            rows.push({
                key: 'usb', icon: 'box', title: 'USB 저장장치',
                pill: usb.state_ko, pillTone: blocked ? 'ok' : 'warn',
                what: blocked
                    ? 'USB 메모리를 꽂아도 파일이 열리지 않아요. 잠깐 써야 할 때만 푸세요.'
                    : '지금은 USB 메모리를 꽂으면 파일이 열려요.',
                actions,
            });
        }
    }

    // 계정: 사람이 손댈 수 있는 것만 (root 는 제외). 안 쓰는 계정이 있으면 그 계정을 먼저 보여준다.
    //
    // '지금'은 그릴 때 시계를 읽지 않는다. 렌더 중에 Date.now() 를 읽으면 같은 값을 그려도
    // 결과가 달라지는 컴포넌트가 된다(react-hooks/purity). 화면을 새로 받은 시각을 기준으로 쓴다 —
    // 15초마다 갱신되므로 '180일 넘게 안 썼는가' 판정에는 충분하다.
    const people = (accounts || []).filter((a) => a.uid !== 0 && a.commands);
    // asOf 가 없으면(아직 한 번도 못 받았으면) 미사용 여부를 말하지 않는다. 기준 시각을 모르는데
    // "180일 넘게 안 썼다"고 적으면 지어낸 말이 된다.
    const unused = asOf ? people.find((a) => a.state === 'active' && a.last_login
        && asOf - new Date(a.last_login).getTime() > UNUSED_DAYS * 86400000) : null;
    const locked = people.find((a) => a.state === 'locked');
    const target = unused || locked;
    if (target) {
        const isLocked = target.state === 'locked';
        const actions = isLocked
            ? [{
                id: `acct-unlock-${target.name}`, primary: true, label: '다시 쓸 수 있게 하기',
                cmd: target.commands.unlock,
                why: `${target.name} 계정으로 다시 로그인할 수 있게 돼요.`,
            }]
            : [{
                id: `acct-lock-${target.name}`, primary: true, label: '이 계정 잠그기',
                cmd: target.commands.lock,
                why: `${target.name} 계정으로는 로그인할 수 없게 돼요. 파일은 그대로 남고, 되살릴 수도 있어요.`,
            }];
        rows.push({
            key: 'accounts', icon: 'lock',
            title: `계정 ${target.name}`,
            pill: target.state_ko, pillTone: isLocked ? 'ok' : 'warn',
            what: isLocked
                ? '지금은 이 계정으로 로그인할 수 없어요. 다시 쓰려면 풀어 주세요.'
                : `${UNUSED_DAYS}일 넘게 쓰지 않은 계정이에요. 안 쓰는 계정은 잠가두는 것이 안전해요.`,
            actions,
        });
    }

    if (!rows.length) return null;

    return (
        <Card className="overflow-hidden">
            <div className="flex items-baseline justify-between gap-3 px-5 pt-4 pb-1 flex-wrap">
                <span className="text-[13px] text-calm-muted tracking-[0.02em]">지금 할 수 있는 것</span>
                <span className="text-[12.5px] text-calm-muted" style={{ wordBreak: 'keep-all' }}>
                    누르면 터미널에 붙여 넣을 명령을 알려드려요
                </span>
            </div>
            {rows.slice(0, MAX_ROWS).map((r) => (
                <Row key={r.key} {...r} openId={openId} setOpenId={setOpenId} />
            ))}
        </Card>
    );
}
