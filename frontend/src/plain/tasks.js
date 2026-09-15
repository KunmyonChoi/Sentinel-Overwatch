// 알림(전문가 언어) → 할 일(사용자 언어) 사전.
//
// 규칙 하나마다 "무슨 일인가 / 왜 문제인가 / 무엇을 할 수 있나"를 정해둔다.
// 여기에 없는 규칙도 반드시 화면에 나온다 (fallback). 모르는 알림을 숨기는 것이
// 가장 나쁜 실패이기 때문이다.
//
// kind
//   fix    버튼 하나로 끝난다. 누르기 전에 무엇이 바뀌는지 보여준다.
//   guide  시스템이 대신 못 한다. 순서대로 할 일을 알려준다.
//   judge  본인만 아는 일이다. 본인 여부를 묻고, 아니라면 할 일을 알려준다.

export const KIND = { FIX: 'fix', GUIDE: 'guide', JUDGE: 'judge' };

// 같은 종류는 한 가지 일로 묶는다. 파일 3개는 "할 일 3개"가 아니라 "할 일 1개"다.
// 묶지 않으면 크론 작업 변경 21건이 카드 21장이 되어, 기획서 §1 이 경고한 '무뎌진다'가 그대로 일어난다.
// 개별 건은 상세 화면의 '지킴이가 본 것'에 전부 남는다.

const RULES = {
  // ---- 버튼 하나로 끝나는 것 ----
  file_permission: {
    kind: KIND.FIX, icon: 'lock',
    title: (n) => `다른 사람이 고칠 수 있는 파일이 ${n}개 있어요`,
    what: '파일에는 누가 열고 고칠 수 있는지를 정해두는 자물쇠가 있어요. 이 파일들은 자물쇠가 풀려 있어서, 이 컴퓨터를 쓰는 다른 사람이 내용을 바꿀 수 있어요.',
    why: '이 파일들은 로그인할 때마다 자동으로 실행되는 것이 많아요. 누가 내용을 몰래 바꿔 놓으면, 내가 로그인하는 순간 그 프로그램이 내 이름으로 함께 실행돼요.',
    fix: { verb: '잠그기', done: '잠갔어요', note: '잠그기만 해요. 지금 쓰시던 기능이 안 되는 일은 없어요.' },
  },

  // ---- 순서대로 알려주는 것 ----
  exposed_port: {
    kind: KIND.GUIDE, icon: 'door',
    title: (n) => (n > 1 ? `밖에서 들어올 수 있는 문이 ${n}개 열려 있어요` : '밖에서 들어올 수 있는 문이 열려 있어요'),
    what: '이 컴퓨터의 어떤 프로그램이 바깥에서 접속할 수 있게 문을 열어두었고, 잠금장치도 그 문을 막지 않고 있어요.',
    why: '의도해서 연 문이면 괜찮아요. 그렇지 않다면 인터넷에 있는 누구나 이 문을 두드려볼 수 있어요.',
    steps: [
      '이 문을 쓰는 프로그램이 무엇인지 아래에서 확인하세요.',
      '내가 쓰려고 열어둔 것이면 그대로 두셔도 돼요.',
      '모르는 것이면 그 프로그램을 끄거나, 도움을 받을 수 있는 사람에게 이 화면을 보여주세요.',
    ],
  },
  new_listener: {
    kind: KIND.GUIDE, icon: 'door',
    title: (n) => (n > 1 ? `새 프로그램이 문을 ${n}개 열었어요` : '새 프로그램이 문을 하나 열었어요'),
    what: '지금까지 없던 문이 새로 생겼어요.',
    why: '방금 프로그램을 설치하셨다면 자연스러운 일이에요. 그런 적이 없다면 무엇이 문을 열었는지 확인하는 게 좋아요.',
    steps: ['방금 새 프로그램을 설치하거나 켜셨나요? 그렇다면 그대로 두셔도 돼요.', '아니라면 아래 프로그램 이름을 확인하고, 모르는 것이면 도움을 받으세요.'],
  },
  container_config: {
    kind: KIND.GUIDE, icon: 'box',
    title: (n) => (n > 1 ? `관리자 권한으로 도는 프로그램이 ${n}개 있어요` : '관리자 권한으로 도는 프로그램이 있어요'),
    what: '이 프로그램은 컴퓨터의 거의 모든 것을 건드릴 수 있는 권한으로 돌고 있어요.',
    why: '그 프로그램에 문제가 생기면 컴퓨터 전체가 함께 위험해져요. 필요할 때만 켜는 게 안전해요.',
    steps: ['지금 이 프로그램을 쓰고 계신가요? 쓰지 않는다면 꺼두세요.', '무엇인지 모르겠다면 아래 이름을 도움 주실 분께 보여주세요.'],
  },
  pending_security_updates: {
    kind: KIND.GUIDE, icon: 'update',
    title: () => '밀린 보안 업데이트가 있어요',
    what: '이미 알려진 허점을 막는 수정이 나와 있는데 아직 설치되지 않았어요.',
    why: '알려진 허점은 공격하기 가장 쉬운 곳이에요. 보통은 자동으로 설치되지만, 밀려 있다면 확인이 필요해요.',
    steps: ['컴퓨터를 한 번 다시 켜면 설치가 마무리되는 경우가 많아요.', '그래도 남아 있으면 도움 주실 분께 이 화면을 보여주세요.'],
  },
  usn_affects_host: {
    kind: KIND.GUIDE, icon: 'update',
    title: () => '내 컴퓨터에 해당하는 보안 문제가 발표됐어요',
    what: '이 컴퓨터에 설치된 프로그램에서 문제가 발견됐다는 공지가 나왔어요.',
    why: '고치는 업데이트가 이미 나와 있는 경우가 대부분이에요.',
    steps: ['밀린 보안 업데이트가 있는지 홈 화면에서 확인하세요.', '있다면 먼저 설치하세요.'],
  },
  lynis_warning: {
    kind: KIND.GUIDE, icon: 'check',
    title: (n) => (n > 1 ? `점검 도구가 새로 알려온 것이 ${n}가지 있어요` : '점검 도구가 새로 알려온 것이 있어요'),
    what: '바깥 점검 도구가 이 컴퓨터에서 고쳐두면 좋을 점을 찾았어요.',
    why: '지금 당장 위험한 것은 아니지만, 해두면 더 단단해져요.',
    steps: ['급한 일이 아니에요. 시간이 날 때 도움 주실 분과 함께 보세요.'],
  },
  lynis_index_drop: {
    kind: KIND.GUIDE, icon: 'check',
    title: () => '보안 점검 점수가 떨어졌어요',
    what: '지난번보다 점검 점수가 낮아졌어요. 설정이 느슨해졌거나 새 프로그램이 늘었을 수 있어요.',
    why: '점수 자체가 위험을 뜻하지는 않지만, 무엇이 달라졌는지 볼 만해요.',
    steps: ['최근에 새 프로그램을 설치하셨는지 떠올려 보세요.', '자세히 보기에서 무엇이 늘었는지 확인할 수 있어요.'],
  },
  port_scan: {
    kind: KIND.GUIDE, icon: 'door',
    title: () => '누가 문을 하나씩 두드려 봤어요',
    what: '바깥의 누군가가 이 컴퓨터의 문을 여러 개 확인해 봤어요.',
    why: '인터넷에 연결된 컴퓨터에는 흔히 있는 일이에요. 열린 문이 없으면 아무 일도 일어나지 않아요.',
    steps: ['홈 화면에서 열린 문이 의도한 것뿐인지 확인하세요.', '그렇다면 따로 하실 일은 없어요.'],
  },
  brute_force: {
    kind: KIND.GUIDE, icon: 'shield',
    title: () => '비밀번호를 계속 찍어보는 시도가 있었어요',
    what: '누군가 비밀번호를 여러 번 맞혀보려 했고, 지킴이가 그 상대를 자동으로 막았어요.',
    why: '막혔기 때문에 들어오지 못했어요. 자주 반복되면 문을 아예 닫는 것을 고려해 보세요.',
    steps: ['이미 막았어요. 지금 하실 일은 없어요.', '기록에서 언제 어떤 상대였는지 볼 수 있어요.'],
  },

  // '밀린 업데이트 없음'과 '할 일 없음'은 다르다. 설치해 두고 다시 시작하지 않으면
  // 고쳐진 문제가 그대로 살아 있는데, apt 는 "밀린 것 없음"이라고 답한다.
  reboot_required: {
    kind: KIND.GUIDE, icon: 'update',
    title: () => '업데이트를 마치려면 컴퓨터를 다시 시작해야 해요',
    what: '새 버전은 이미 설치됐어요. 그런데 지금 켜져 있는 프로그램들은 아직 옛 버전을 쓰고 있어요.',
    why: '다시 시작하기 전까지는 고쳐진 문제가 그대로 남아 있어요. 설치만으로는 끝난 게 아니에요.',
    steps: [
      '저장하지 않은 것이 있으면 먼저 저장하세요.',
      '편한 시간에 컴퓨터를 다시 시작하세요.',
      '다시 시작하고 나면 이 카드는 저절로 사라져요.',
    ],
  },

  // 감시가 멈춘 자리. 이건 '이상 없음'이 아니라 '모름'이라서, 다른 알림보다
  // 오히려 먼저 알려야 한다 — 여기서 무슨 일이 생겨도 지킴이가 못 본다.
  monitor_blind_spot: {
    kind: KIND.JUDGE, icon: 'eye',
    title: (n) => (n > 1 ? `지킴이가 못 보는 곳이 ${n}군데 생겼어요` : '지킴이가 못 보는 곳이 생겼어요'),
    what: '권한이 막혀서 몇 군데를 읽지 못했어요. 그곳은 지금 감시되지 않아요. '
        + '"괜찮다"가 아니라 "모른다"는 뜻이에요 — 거기에 무언가 새로 생겨도 알 수 없어요.',
    ask: '최근에 그 폴더의 권한을 직접 바꾸셨나요?',
  },

  persistence_cron: {
    kind: KIND.JUDGE, icon: 'clock',
    title: (n) => (n > 1 ? `정해진 시각에 자동 실행되는 작업이 ${n}가지 바뀌었어요` : '정해진 시각에 자동 실행되는 작업이 바뀌었어요'),
    what: '컴퓨터가 정해진 시각마다 알아서 실행하는 일의 목록이 달라졌어요. 프로그램을 설치하거나 지울 때 함께 바뀌는 경우가 많아요.',
    ask: '최근에 프로그램을 설치하거나 지우셨나요?',
  },
  persistence_systemd: {
    kind: KIND.JUDGE, icon: 'clock',
    title: (n) => (n > 1 ? `컴퓨터를 켤 때 자동으로 도는 프로그램이 ${n}가지 바뀌었어요` : '컴퓨터를 켤 때 자동으로 도는 프로그램이 바뀌었어요'),
    what: '컴퓨터가 켜질 때 스스로 실행하는 프로그램 목록이 달라졌어요.',
    ask: '최근에 프로그램을 설치하거나 지우셨나요?',
  },
  proc_exec_from_tmp: {
    kind: KIND.JUDGE, icon: 'alert',
    title: (n) => (n > 1 ? `임시 폴더에 있던 프로그램이 ${n}번 실행됐어요` : '임시 폴더에 있던 프로그램이 실행됐어요'),
    what: '잠깐 쓰고 지우는 폴더에서 프로그램이 실행됐어요. 내려받은 파일을 바로 실행할 때도 생기지만, 공격에서도 흔한 방식이에요.',
    ask: '방금 내려받은 프로그램을 실행하셨나요?',
  },

  // ---- 본인만 아는 것 ----
  new_login_ip: {
    kind: KIND.JUDGE, icon: 'alert',
    title: () => '처음 보는 곳에서 로그인에 성공했어요',
    what: '지금까지 접속한 적 없는 곳에서 이 컴퓨터에 들어왔어요.',
    ask: '이때 직접 접속하셨나요?',
  },
  login_after_failures: {
    kind: KIND.JUDGE, icon: 'alert',
    title: () => '여러 번 실패한 뒤에 로그인에 성공했어요',
    what: '같은 상대가 여러 번 틀리다가 결국 들어왔어요. 비밀번호를 맞혔을 수 있어요.',
    ask: '이때 직접 접속하셨나요? (비밀번호를 여러 번 틀리신 적이 있나요?)',
  },
  root_ssh_login: {
    kind: KIND.JUDGE, icon: 'alert',
    title: () => '최고 관리자 계정으로 바로 접속했어요',
    what: '보통은 쓰지 않는, 무엇이든 할 수 있는 계정으로 곧바로 들어왔어요.',
    ask: '이 접속을 직접 하셨나요?',
  },
  account_change: {
    kind: KIND.JUDGE, icon: 'alert',
    title: () => '계정이나 권한이 바뀌었어요',
    what: '이 컴퓨터를 쓸 수 있는 사람이나 그 사람이 할 수 있는 일이 달라졌어요.',
    ask: '직접 바꾸셨나요?',
  },
  integrity_change: {
    kind: KIND.JUDGE, icon: 'alert',
    title: () => '중요한 설정 파일이 바뀌었어요',
    what: '컴퓨터가 어떻게 동작할지 정하는 파일이 달라졌어요.',
    ask: '설정을 바꾸거나 프로그램을 설치하셨나요?',
  },
  persistence_suid: {
    kind: KIND.JUDGE, icon: 'alert',
    title: () => '특별한 권한을 가진 프로그램이 새로 생겼어요',
    what: '누가 실행해도 관리자처럼 동작하는 프로그램이 추가됐어요.',
    ask: '방금 프로그램을 설치하셨나요?',
  },
  kernel_module: {
    kind: KIND.JUDGE, icon: 'alert',
    title: () => '시스템 깊은 곳에 부품이 추가되거나 빠졌어요',
    what: '컴퓨터의 가장 안쪽에서 도는 부품이 바뀌었어요. 보통은 장치 드라이버를 설치할 때 생겨요.',
    ask: '새 장치나 드라이버를 설치하셨나요?',
  },
  ld_preload_write: {
    kind: KIND.JUDGE, icon: 'alert',
    title: () => '프로그램을 가로챌 수 있는 자리가 바뀌었어요',
    what: '모든 프로그램이 시작할 때 함께 불러오는 자리에 무언가 쓰였어요. 정상적인 컴퓨터에는 보통 비어 있는 자리예요.',
    ask: '이 변경을 직접 하셨나요?',
  },
  security_tool: {
    kind: KIND.JUDGE, icon: 'alert',
    title: () => '점검·해킹에 쓰이는 도구가 실행됐어요',
    what: '보안 점검에도, 공격에도 쓰이는 도구가 이 컴퓨터에서 실행됐어요.',
    ask: '직접 실행하셨나요?',
  },
  sudo_failure: {
    kind: KIND.JUDGE, icon: 'alert',
    title: () => '관리자 권한을 얻으려다 실패한 기록이 있어요',
    what: '누군가 관리자 권한이 필요한 일을 하려다 막혔어요.',
    ask: '비밀번호를 잘못 입력하신 적이 있나요?',
  },
};

// 본인이 한 일이 아닐 때의 공통 안내
export const JUDGE_STEPS = [
  { b: '인터넷 선을 잠시 뽑으세요.', t: '무선이면 와이파이를 끄면 돼요.' },
  { b: '다른 기기에서 이 계정의 비밀번호를 바꾸세요.', t: '휴대폰으로 하셔도 돼요.' },
  { b: '아래 버튼으로 기록을 저장해 두세요.', t: '도움을 받을 때 그대로 보여주시면 돼요.' },
];

const FALLBACK = {
  kind: KIND.GUIDE, icon: 'alert',
  steps: ['무슨 일인지 아래 설명을 읽어보세요.', '모르겠으면 이 화면을 저장해 도움 주실 분께 보여주세요.'],
};

/** 알림 목록을 사용자 언어의 할 일 목록으로 바꾼다. 모르는 규칙도 반드시 남는다. */
export function buildTasks(alerts) {
  const open = (alerts || []).filter((a) => a.status === 'OPEN' && !a.is_simulation);
  const groups = new Map();

  for (const a of open) {
    const key = a.rule;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(a);
  }

  const tasks = [];
  for (const [key, items] of groups) {
    const rule = items[0].rule;
    const spec = RULES[rule] || FALLBACK;
    const n = items.length;
    const worst = items.some((i) => i.severity === 'CRITICAL') ? 'CRITICAL' : 'WARNING';
    tasks.push({
      id: key,
      rule,
      kind: spec.kind,
      icon: spec.icon || 'alert',
      severity: worst,
      count: n,
      // 사전에 없는 규칙은 백엔드가 만든 한국어 제목을 그대로 쓴다 (숨기지 않는다)
      title: spec.title ? spec.title(n) : (n > 1
        ? `${items[0].title_ko || items[0].title} 외 ${n - 1}건`
        : items[0].title_ko || items[0].title),
      what: spec.what || items[0].summary_ko || '',
      why: spec.why || '',
      ask: spec.ask || '',
      steps: spec.steps || FALLBACK.steps,
      fix: spec.fix || null,
      known: Boolean(RULES[rule]),
      // 사용자가 이미 답한 일인지 (확인 중 표시에 쓴다)
      response: items.map((i) => i.details?.user_response).find(Boolean) || null,
      alerts: items,
      seenAt: items.map((i) => i.last_seen_at).sort().at(-1),
    });
  }

  const rank = { CRITICAL: 0, WARNING: 1 };
  tasks.sort((a, b) => rank[a.severity] - rank[b.severity] || String(b.seenAt).localeCompare(String(a.seenAt)));
  return tasks;
}

/**
 * DEFCON → 사용자 언어의 3단계.
 *
 * stats 를 못 읽었으면 '이상 없음'이라고 말하면 안 된다. 지킴이가 죽어 있는데
 * 큰 글씨로 안전하다고 말하는 것이 이 화면이 저지를 수 있는 가장 나쁜 거짓말이다.
 */
export function statusOf(stats, taskCount, conn = 'ok') {
  if (!stats || conn !== 'ok') {
    return conn === 'down'
      ? { key: 'unknown', label: '상태를 알 수 없어요', lead: '지킴이와 연결하지 못했어요. 안전한지 아닌지 지금은 말씀드릴 수 없어요.' }
      : { key: 'unknown', label: '확인하고 있어요', lead: '지킴이에게 지금 상태를 물어보는 중이에요.' };
  }
  const s = stats?.status;
  if (s === 'DEFCON 1') return { key: 'crit', label: '지금 확인하세요', lead: '바로 살펴봐야 할 일이 있어요.' };
  if (s === 'DEFCON 3' || taskCount > 0) {
    return { key: 'warn', label: '살펴보세요', lead: `손볼 일이 ${taskCount === 1 ? '한' : taskCount} 가지 있어요. 급하지는 않지만 오늘 중에 해두는 게 좋아요.` };
  }
  return { key: 'ok', label: '이상 없음', lead: '지금 손볼 일이 없어요. 이 창을 닫으셔도 돼요.' };
}

/** 이벤트 유형 → 기록 화면의 평문 한 줄 */
export const EVENT_KO = {
  FILE_PERMISSION: { icon: 'lock', who: '자동 점검' },
  PERMISSION_FIXED: { icon: 'lock', who: '내가 함' },
  PORT_EXPOSURE: { icon: 'door', who: '자동 점검' },
  PORT_CLOSED: { icon: 'door', who: '자동 점검' },
  CONTAINER_CONFIG: { icon: 'box', who: '자동 점검' },
  IP_BLOCKED: { icon: 'shield', who: '자동 차단' },
  IP_UNBLOCKED: { icon: 'shield', who: '내가 함' },
  IP_BLOCK_SKIPPED: { icon: 'shield', who: '자동 점검' },
  SOFTWARE_UPDATE: { icon: 'update', who: '자동' },
  PENDING_UPDATES: { icon: 'update', who: '자동 점검' },
  AUTH_SUCCESS: { icon: 'alert', who: '접속' },
  AUTH_FAILURE: { icon: 'shield', who: '접속 실패' },
  ACCOUNT_CHANGE: { icon: 'alert', who: '계정 변경' },
  FILE_INTEGRITY: { icon: 'alert', who: '자동 점검' },
  PERSISTENCE: { icon: 'alert', who: '자동 점검' },
  NETWORK_LISTENER: { icon: 'door', who: '자동 점검' },
};
