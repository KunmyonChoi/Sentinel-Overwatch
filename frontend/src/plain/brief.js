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

/** task + host → 붙여넣기용 마크다운 */
export function buildBrief(task, host) {
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
