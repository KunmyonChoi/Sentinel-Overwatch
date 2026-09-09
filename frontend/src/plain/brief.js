// 할 일 하나를 '그대로 붙여넣어 물어볼 수 있는' 자기완결 텍스트로 만든다.
//
// 저장소에 이미 같은 패턴이 있다 (강화 작업 목록의 /api/hardening/brief).
// 여기서는 화면이 이미 들고 있는 자료만 쓰므로 백엔드를 부르지 않는다.
//
// 주의: 이 텍스트에는 이 컴퓨터의 파일 경로·주소·계정 이름이 들어간다.
// 대시보드가 스스로 외부로 보내는 일은 없고, 사람이 직접 붙여넣을 때만 나간다.
// 그래서 버튼 옆에 그 사실을 적어둔다.

function section(title, lines) {
    const body = lines.filter(Boolean);
    return body.length ? [`## ${title}`, '', ...body, ''] : [];
}

/**
 * 밖으로 나가면 곤란한 것을 가린다.
 *
 * 무엇을 가리나: 이 컴퓨터의 이름, 계정 이름, 내부·외부 인터넷 주소, 장치 주소, 메일 주소.
 * 무엇을 남기나: 운영체제와 버전, 포트 번호, 프로그램 이름, 파일이 어떤 종류인지, 시각.
 *   — 이것들이 없으면 제대로 된 답을 받을 수 없고, 이것만으로는 이 컴퓨터를 찾아낼 수 없다.
 *
 * 같은 주소는 같은 이름으로 바꾼다(<외부주소 1> 이 세 번 나오면 같은 상대다).
 * 그래야 "같은 곳에서 반복해서 시도했다" 같은 판단이 가려도 살아남는다.
 */
// 이 낱말들은 컴퓨터 이름이어도 가리지 않는다. 흔한 말이라 가리면 엉뚱한 곳까지 바뀐다.
const GENERIC_HOST = new Set(['ubuntu', 'debian', 'linux', 'localhost', 'server', 'desktop', 'laptop', 'pc', 'host', 'home', 'user', 'admin']);
// 어느 컴퓨터에나 있는 기본 계정. 가려도 알려주는 것이 없고, 가리면 'Ubuntu 24.04' 같은
// 문장까지 망가져서 오히려 답을 못 받는다.
const GENERIC_ACCOUNT = new Set(['ubuntu', 'debian', 'admin', 'user', 'guest', 'pi', 'vagrant', 'ec2-user', 'root', 'test']);

export function redact(text, host, accounts = []) {
    let s = String(text || '');

    // 1) 이 컴퓨터의 이름 (흔한 낱말이면 그대로 둔다 — 가리면 본문이 망가진다)
    const hn = host?.hostname;
    if (hn && hn.length >= 4 && !GENERIC_HOST.has(hn.toLowerCase())) {
        s = s.split(hn).join('<내-컴퓨터>');
    }

    // 2) 계정 이름과 실명.
    //    사람 계정(uid 1000 이상)만 가린다. root·syslog 같은 시스템 계정은 프로그램 이름이라
    //    가릴 것이 없고, 가리면 오히려 무슨 일인지 알아볼 수 없게 된다.
    //    ubuntu 처럼 어느 컴퓨터에나 있는 기본 계정도 그대로 둔다 — 아무것도 알려주지 않는다.
    //    계정마다 다른 이름표를 붙여 "누가 누구인지"의 관계는 남긴다.
    const names = new Map();
    const label = () => `<사용자 ${String.fromCharCode(65 + names.size)}>`;
    const add = (n) => {
        const v = String(n || '').trim();
        if (v.length < 3 || names.has(v) || GENERIC_ACCOUNT.has(v.toLowerCase())) return;
        names.set(v, label());
    };
    const addAlias = (n, of) => {   // 실명은 로그인 이름과 같은 이름표를 쓴다
        const v = String(n || '').trim();
        if (v.length < 3 || names.has(v) || GENERIC_ACCOUNT.has(v.toLowerCase())) return;
        names.set(v, names.get(of) || label());
    };

    for (const a of accounts) {
        if (!a || !(a.uid >= 1000 && a.uid < 60000)) continue;
        add(a.name);
        addAlias(a.gecos, a.name);
    }
    // 지금은 없는 계정도 알림 본문(passwd/group 변경 내역)에는 남아 있다.
    // 계정 목록만으로는 못 잡으므로 본문에서도 뽑는다.
    for (const m of s.matchAll(/^[-+ ]?([A-Za-z0-9._-]+):x:(\d+):(\d+):([^:]*):/gm)) {
        const uid = Number(m[2]);
        if (uid >= 1000 && uid < 60000) {
            add(m[1]);
            addAlias((m[4] || '').split(',')[0], m[1]);   // GECOS 첫 칸이 실명이다
        }
    }
    for (const m of s.matchAll(/\/(?:home|Users)\/([A-Za-z0-9._-]+)/g)) add(m[1]);

    // 긴 이름부터 바꿔야 짧은 이름이 긴 이름의 일부를 먼저 갉아먹지 않는다
    for (const n of [...names.keys()].sort((a, b) => b.length - a.length)) {
        s = s.split(n).join(names.get(n));
    }

    // 3) 장치 주소 → 인터넷 주소(IPv6) → 인터넷 주소(IPv4) 순서 (겹쳐 매칭되지 않게)
    s = s.replace(/\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b/g, '<장치주소>');
    s = s.replace(/\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b/g, (m) => (m === '::1' ? m : '<인터넷주소>'));

    const seen = new Map();
    s = s.replace(/\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b/g, (full, a, b) => {
        const A = Number(a), B = Number(b);
        if (A > 255 || B > 255) return full;                       // 버전 번호 등
        if (A === 127) return full;                                 // 이 컴퓨터 안쪽 — 가릴 것 없음
        if (A === 0 || A === 255) return full;
        if (A === 10 || (A === 172 && B >= 16 && B <= 31) || (A === 192 && B === 168) || (A === 169 && B === 254)) {
            return '<집·회사 안쪽 주소>';
        }
        if (!seen.has(full)) seen.set(full, `<외부주소 ${seen.size + 1}>`);
        return seen.get(full);
    });

    // 4) 메일 주소
    s = s.replace(/\b[\w.+-]+@[\w-]+\.[\w.-]+\b/g, '<메일주소>');

    return s;
}

/** task + host → 붙여넣기용 마크다운. mask=true 면 중요한 정보를 가린 판을 돌려준다. */
export function buildBrief(task, host, mask = true, accounts = []) {
    const raw = buildBriefRaw(task, host);
    if (!mask) return raw;
    const masked = redact(raw, host, accounts);
    return masked.replace(
        '전문 용어를 쓰지 말고 쉬운 말로 설명해 주세요.',
        '전문 용어를 쓰지 말고 쉬운 말로 설명해 주세요.\n'
        + '(컴퓨터 이름·계정 이름·인터넷 주소는 <이렇게> 가려서 올렸어요. 같은 표시는 같은 대상입니다.)',
    );
}

function buildBriefRaw(task, host) {
    const sev = task.severity === 'CRITICAL' ? '긴급' : '주의';
    const kindKo = { fix: '프로그램이 대신 고칠 수 있는 일', guide: '제가 직접 해야 하는 일', judge: '제가 한 일인지 판단해야 하는 일' }[task.kind] || '';

    const out = [
        '# 제 컴퓨터에 이런 알림이 떴는데, 어떻게 해야 하나요?',
        '',
        '저는 보안을 잘 모르는 사람이고, 제 개인 컴퓨터를 혼자 관리하고 있어요.',
        '아래는 컴퓨터에 설치된 보안 감시 프로그램이 알려준 내용을 그대로 옮긴 것입니다.',
        '전문 용어를 쓰지 말고 쉬운 말로 설명해 주세요.',
        '',
    ];

    out.push(...section('내 컴퓨터', [
        host?.os ? `- 운영체제: ${host.os}` : null,
        host?.kernel ? `- 커널: ${host.kernel}` : null,
        host?.uptime_hours ? `- 켜둔 시간: 약 ${Math.round(host.uptime_hours)}시간` : null,
        '- 용도: 개인 작업용 컴퓨터',
    ]));

    out.push(...section('알림 내용', [
        `**${task.title}**`,
        '',
        `- 심각도: ${sev}`,
        `- 건수: ${task.count}건`,
        kindKo ? `- 프로그램의 분류: ${kindKo}` : null,
        task.what ? `- 무슨 일인가: ${task.what}` : null,
        task.why ? `- 왜 문제인가: ${task.why}` : null,
    ]));

    // 20건짜리 묶음도 있다. 붙여넣기 좋은 길이로 자르고, 자른 사실을 적는다.
    const MAX = 12;
    const shown = (task.alerts || []).slice(0, MAX);
    const items = shown.map((a, i) => {
        const lines = [`${i + 1}. ${a.title_ko || a.title}`];
        if (a.summary_ko) lines.push(`   - 설명: ${a.summary_ko}`);
        if (a.action_ko) lines.push(`   - 프로그램이 제안한 조치: ${a.action_ko}`);
        if (a.evidence) lines.push(`   - 근거: ${String(a.evidence).slice(0, 400)}`);
        if (a.last_seen_at) lines.push(`   - 마지막 발생: ${a.last_seen_at}`);
        return lines.join('\n');
    });
    if (task.count > MAX) items.push(`\n(같은 종류가 ${task.count}건 있어서 앞의 ${MAX}건만 옮겼어요.)`);
    out.push(...section(`보안 프로그램이 실제로 본 것 (${task.count}건)`, items));

    out.push(...section('물어보고 싶은 것', [
        '1. 이게 실제로 위험한 상황인가요? 지금 바로 해야 하나요, 아니면 천천히 해도 되나요?',
        '2. 제가 직접 할 수 있는 일이 있다면 순서대로 알려주세요. 터미널 명령이 필요하면 그 명령이 무엇을 하는지도 함께 설명해 주세요.',
        '3. 반대로 하면 안 되는 일, 조심해야 할 것이 있나요?',
        '4. 이 상황이 왜 생겼을지 짐작되는 이유가 있나요?',
    ]));

    return out.join('\n').trim() + '\n';
}

/** 클립보드 복사. 권한이 막힌 환경(비 HTTPS 등)에서도 되도록 대비한다. */
export async function copyText(text) {
    try {
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(text);
            return true;
        }
    } catch { /* 아래 방법으로 다시 시도 */ }
    try {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', '');
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        const ok = document.execCommand('copy');
        document.body.removeChild(ta);
        return ok;
    } catch {
        return false;
    }
}

/** 붙여넣기용 글을 파일로 저장한다. 도움을 받을 때 그대로 보여주면 된다. */
export function downloadText(filename, text) {
    try {
        const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        a.click();
        URL.revokeObjectURL(a.href);
        return true;
    } catch {
        return false;
    }
}
