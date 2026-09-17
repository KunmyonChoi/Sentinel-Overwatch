// 쉬운 화면의 판정. 이 파일이 지키는 것은 '무엇을 보여주는가'가 아니라
// '무엇을 말하는가'다 — 사용자가 읽는 문장이 규칙에 맞게 골라지는지 본다.
//
// 특히 두 가지는 안전 속성이라 명시해서 잡아둔다.
//   1) 사전에 없는 규칙은 조용히 '급하지 않음'이 되지 않는다 (UNKNOWN 으로 올라간다).
//   2) 받아온 알림이 서버가 센 것보다 적으면 "0 가지"라고 말하지 않고, 못 불러왔다고 말한다.
import { describe, it, expect } from 'vitest'
import { URGENCY, KIND, urgencyOf, buildTasks, statusOf } from './tasks'

// 알림 한 건. 테스트마다 달라지는 것만 넘긴다.
const alert = (over = {}) => ({
  id: 1,
  rule: 'file_permission',
  severity: 'WARNING',
  status: 'OPEN',
  is_simulation: false,
  title: 'Something happened',
  title_ko: '무슨 일이 있었어요',
  last_seen_at: '2026-09-16T10:00:00Z',
  ...over,
})

describe('urgencyOf', () => {
  // 로그인·권한·침입 흔적. 이 이름들이 CARE 로 떨어지면 홈 첫 문장이
  // "급하지는 않지만"으로 바뀌어 거짓 안심을 준다.
  it.each([
    'new_login_ip', 'login_after_failures', 'root_ssh_login', 'sudo_failure', 'account_change',
    'integrity_change', 'persistence_suid', 'kernel_module', 'ld_preload_write',
    'security_tool', 'security_package_removed',
    'scan_then_auth', 'scan_then_connection', 'internal_scan',
  ])('침입 신호 %s 는 SIGNAL 이다', (rule) => {
    expect(urgencyOf(rule)).toBe(URGENCY.SIGNAL)
  })

  // 백엔드가 이름을 조립해서 만드는 계열. 앞자리로 잡으므로 아직 없는 이름도 잡혀야 한다.
  it.each([
    'persistence_cron', 'persistence_systemd', 'persistence_brand_new',
    'proc_exec_from_tmp', 'proc_shell_over_socket', 'proc_brand_new',
  ])('계열 이름 %s 은 앞자리로 잡아 SIGNAL 이다', (rule) => {
    expect(urgencyOf(rule)).toBe(URGENCY.SIGNAL)
  })

  it('앞자리는 밑줄까지 정확히 맞아야 한다 (엉뚱한 이름을 침입 신호로 만들지 않는다)', () => {
    expect(urgencyOf('persistence')).toBe(URGENCY.UNKNOWN)
    expect(urgencyOf('process_listing')).toBe(URGENCY.UNKNOWN)
  })

  it.each([
    'file_permission', 'exposed_port', 'new_listener', 'container_config',
    'pending_security_updates', 'reboot_required', 'usn_affects_host',
    'lynis_warning', 'lynis_index_drop',
    'port_scan', 'brute_force',
    'high_cpu', 'high_memory', 'disk_full', 'process_spike', 'time_unsynced',
  ])('위생 작업 %s 은 CARE 다', (rule) => {
    expect(urgencyOf(rule)).toBe(URGENCY.CARE)
  })

  it('감시가 멈춘 자리는 UNKNOWN 이다 — 침입 신호도, 괜찮음도 아니다', () => {
    expect(urgencyOf('monitor_blind_spot')).toBe(URGENCY.UNKNOWN)
  })

  // 안전 속성: 처음 보는 알림을 조용히 '급하지 않음'으로 만드는 것이 가장 나쁜 실패다.
  it('사전에 없는 규칙은 CARE 로 내려가지 않고 UNKNOWN 이 된다', () => {
    expect(urgencyOf('totally_unheard_of_rule')).toBe(URGENCY.UNKNOWN)
    expect(urgencyOf('totally_unheard_of_rule')).not.toBe(URGENCY.CARE)
  })

  it('규칙 이름이 비어 있어도 UNKNOWN 이다', () => {
    expect(urgencyOf(undefined)).toBe(URGENCY.UNKNOWN)
    expect(urgencyOf(null)).toBe(URGENCY.UNKNOWN)
    expect(urgencyOf('')).toBe(URGENCY.UNKNOWN)
  })
})

describe('buildTasks', () => {
  it('같은 규칙은 한 가지 일로 묶는다 (파일 3개는 할 일 1개)', () => {
    const tasks = buildTasks([
      alert({ id: 1, rule: 'file_permission' }),
      alert({ id: 2, rule: 'file_permission' }),
      alert({ id: 3, rule: 'file_permission' }),
    ])
    expect(tasks).toHaveLength(1)
    expect(tasks[0].count).toBe(3)
    expect(tasks[0].alerts).toHaveLength(3)
  })

  it('규칙이 다르면 따로 묶는다', () => {
    const tasks = buildTasks([
      alert({ id: 1, rule: 'file_permission' }),
      alert({ id: 2, rule: 'pending_security_updates' }),
    ])
    expect(tasks).toHaveLength(2)
    expect(tasks.map((t) => t.rule).sort()).toEqual(['file_permission', 'pending_security_updates'])
  })

  it('한 건이라도 긴급이면 묶음 전체가 긴급이다', () => {
    const [task] = buildTasks([
      alert({ id: 1, rule: 'file_permission', severity: 'WARNING' }),
      alert({ id: 2, rule: 'file_permission', severity: 'CRITICAL' }),
    ])
    expect(task.severity).toBe('CRITICAL')
  })

  it('긴급이 먼저다 — 위생 작업이라도 긴급이면 침입 신호보다 위에 온다', () => {
    const tasks = buildTasks([
      alert({ id: 1, rule: 'new_login_ip', severity: 'WARNING' }),
      alert({ id: 2, rule: 'file_permission', severity: 'CRITICAL' }),
    ])
    expect(tasks.map((t) => t.rule)).toEqual(['file_permission', 'new_login_ip'])
  })

  it('같은 심각도면 침입 신호 → 판단 못 한 것 → 위생 작업 순서다', () => {
    const tasks = buildTasks([
      alert({ id: 1, rule: 'pending_security_updates' }),
      alert({ id: 2, rule: 'monitor_blind_spot' }),
      alert({ id: 3, rule: 'new_login_ip' }),
    ])
    expect(tasks.map((t) => t.urgency)).toEqual([URGENCY.SIGNAL, URGENCY.UNKNOWN, URGENCY.CARE])
    expect(tasks.map((t) => t.rule)).toEqual(['new_login_ip', 'monitor_blind_spot', 'pending_security_updates'])
  })

  it('연습용(시뮬레이션) 알림은 할 일이 되지 않는다', () => {
    const tasks = buildTasks([
      alert({ id: 1, rule: 'new_login_ip', is_simulation: true }),
      alert({ id: 2, rule: 'file_permission', is_simulation: false }),
    ])
    expect(tasks.map((t) => t.rule)).toEqual(['file_permission'])
  })

  it('이미 확인한 알림은 할 일이 되지 않는다', () => {
    const tasks = buildTasks([
      alert({ id: 1, rule: 'new_login_ip', status: 'ACKED' }),
      alert({ id: 2, rule: 'file_permission', status: 'OPEN' }),
    ])
    expect(tasks.map((t) => t.rule)).toEqual(['file_permission'])
  })

  // 모르는 알림을 숨기는 것이 가장 나쁜 실패다. 사전에 없어도 카드는 반드시 남는다.
  it('사전에 없는 규칙도 숨기지 않고, 백엔드가 만든 한국어 제목을 그대로 쓴다', () => {
    const [task] = buildTasks([
      alert({ id: 1, rule: 'brand_new_rule', title_ko: '처음 보는 일이 생겼어요', summary_ko: '설명입니다' }),
    ])
    expect(task.rule).toBe('brand_new_rule')
    expect(task.known).toBe(false)
    expect(task.title).toBe('처음 보는 일이 생겼어요')
    expect(task.what).toBe('설명입니다')
    expect(task.urgency).toBe(URGENCY.UNKNOWN)
    expect(task.kind).toBe(KIND.GUIDE)
    expect(task.steps.length).toBeGreaterThan(0)
  })

  it('사전에 없는 규칙이 여러 건이면 "외 n건"으로 적는다', () => {
    const [task] = buildTasks([
      alert({ id: 1, rule: 'brand_new_rule', title_ko: '처음 보는 일' }),
      alert({ id: 2, rule: 'brand_new_rule', title_ko: '처음 보는 일' }),
      alert({ id: 3, rule: 'brand_new_rule', title_ko: '처음 보는 일' }),
    ])
    expect(task.title).toBe('처음 보는 일 외 2건')
  })

  it('사전에 있는 규칙은 사전의 제목·설명을 쓰고 known 이 true 다', () => {
    const [task] = buildTasks([alert({ rule: 'file_permission' }), alert({ id: 2, rule: 'file_permission' })])
    expect(task.known).toBe(true)
    expect(task.kind).toBe(KIND.FIX)
    expect(task.title).toBe('다른 사람이 고칠 수 있는 파일이 2개 있어요')
    expect(task.fix).not.toBeNull()
  })

  it('마지막으로 본 시각은 묶음 안에서 가장 나중 것이다', () => {
    const [task] = buildTasks([
      alert({ id: 1, rule: 'file_permission', last_seen_at: '2026-09-14T10:00:00Z' }),
      alert({ id: 2, rule: 'file_permission', last_seen_at: '2026-09-16T10:00:00Z' }),
      alert({ id: 3, rule: 'file_permission', last_seen_at: '2026-09-15T10:00:00Z' }),
    ])
    expect(task.seenAt).toBe('2026-09-16T10:00:00Z')
  })

  it('사용자가 이미 답한 일이면 그 답을 들고 온다', () => {
    const [task] = buildTasks([
      alert({ id: 1, rule: 'new_login_ip' }),
      alert({ id: 2, rule: 'new_login_ip', details: { user_response: 'not_me' } }),
    ])
    expect(task.response).toBe('not_me')
  })

  it('알림이 없거나 못 받았으면 빈 목록이다', () => {
    expect(buildTasks([])).toEqual([])
    expect(buildTasks(null)).toEqual([])
    expect(buildTasks(undefined)).toEqual([])
  })
})

describe('statusOf', () => {
  it('연결이 끊겼으면 안전하다고 말하지 않는다', () => {
    const s = statusOf(null, [], 'down')
    expect(s.key).toBe('unknown')
    expect(s.label).toBe('상태를 알 수 없어요')
    expect(s.lead).toContain('지금은 말씀드릴 수 없어요')
  })

  it('지킴이가 살아 있어도 stats 를 못 읽었으면 안전하다고 말하지 않는다', () => {
    const s = statusOf(null, [], 'ok')
    expect(s.key).toBe('unknown')
    expect(s.label).toBe('확인하고 있어요')
  })

  it('할 일이 없으면 이상 없음이다', () => {
    const s = statusOf({ status: 'OK', open_critical: 0, open_warning: 0 }, [], 'ok')
    expect(s.key).toBe('ok')
    expect(s.label).toBe('이상 없음')
    expect(s.lead).toBe('지금 손볼 일이 없어요. 이 창을 닫으셔도 돼요.')
  })

  it('DEFCON 1 이면 지금 확인하세요다', () => {
    const s = statusOf({ status: 'DEFCON 1', open_critical: 1, open_warning: 0 }, [], 'ok')
    expect(s.key).toBe('crit')
    expect(s.label).toBe('지금 확인하세요')
  })

  it('위생 작업만 있으면 급하지 않다고 말한다', () => {
    const tasks = buildTasks([alert({ rule: 'pending_security_updates' })])
    const s = statusOf({ status: 'DEFCON 3', open_critical: 0, open_warning: 1 }, tasks, 'ok')
    expect(s.key).toBe('warn')
    expect(s.label).toBe('살펴보세요')
    expect(s.urgency).toBe(URGENCY.CARE)
    expect(s.lead).toBe('손볼 일이 한 가지 있어요. 급하지는 않지만 오늘 중에 해두는 게 좋아요.')
  })

  // 침입 신호에 "급하지는 않지만"이라고 말하면 거짓 안심이 된다.
  it('침입 신호가 있으면 무슨 신호인지 말하고 오늘 바로 보라고 한다', () => {
    const tasks = buildTasks([alert({ rule: 'new_login_ip' })])
    const s = statusOf({ status: 'DEFCON 3', open_critical: 0, open_warning: 1 }, tasks, 'ok')
    expect(s.key).toBe('warn')
    expect(s.urgency).toBe(URGENCY.SIGNAL)
    expect(s.lead).toBe('처음 보는 곳에서 로그인에 성공했어요. 직접 하신 일이 아니라면 오늘 바로 확인하세요.')
    expect(s.lead).not.toContain('급하지는 않지만')
  })

  it('침입 신호가 여러 가지면 몇 가지인지 함께 말한다', () => {
    const tasks = buildTasks([
      alert({ id: 1, rule: 'new_login_ip' }),
      alert({ id: 2, rule: 'root_ssh_login' }),
    ])
    const s = statusOf({ status: 'DEFCON 3', open_critical: 0, open_warning: 2 }, tasks, 'ok')
    expect(s.urgency).toBe(URGENCY.SIGNAL)
    expect(s.lead).toContain('이런 신호가 2가지 있어요.')
  })

  it('침입 신호는 위생 작업보다 먼저 첫 문장을 차지한다', () => {
    const tasks = buildTasks([
      alert({ id: 1, rule: 'pending_security_updates' }),
      alert({ id: 2, rule: 'new_login_ip' }),
    ])
    const s = statusOf({ status: 'DEFCON 3', open_critical: 0, open_warning: 2 }, tasks, 'ok')
    expect(s.urgency).toBe(URGENCY.SIGNAL)
  })

  it('판단하지 못한 것은 괜찮다고도 위험하다고도 말하지 않는다', () => {
    const tasks = buildTasks([alert({ rule: 'monitor_blind_spot' })])
    const s = statusOf({ status: 'DEFCON 3', open_critical: 0, open_warning: 1 }, tasks, 'ok')
    expect(s.urgency).toBe(URGENCY.UNKNOWN)
    expect(s.lead).toBe('지킴이가 못 보는 곳이 생겼어요. 지킴이가 판단하지 못한 일이에요. 오늘 바로 확인하세요.')
  })

  // 목록이 잘린 경우. 예전에는 카드 하나 없이 "손볼 일이 0 가지"라고 말했다.
  it('서버가 센 미확인 건수보다 적게 받았고 할 일이 0이면, 0 가지라고 말하지 않는다', () => {
    const s = statusOf({ status: 'DEFCON 3', open_critical: 1, open_warning: 2 }, [], 'ok')
    expect(s.key).toBe('warn')
    expect(s.urgency).toBe(URGENCY.UNKNOWN)
    expect(s.lead).toContain('손볼 일이 3가지 있는데 아직 불러오지 못했어요.')
    expect(s.lead).not.toContain('0 가지')
  })

  it('일부만 받았으면 아래가 전부가 아니라고 말한다', () => {
    const tasks = buildTasks([
      alert({ id: 1, rule: 'file_permission' }),
      alert({ id: 2, rule: 'file_permission' }),
    ])
    const s = statusOf({ status: 'DEFCON 3', open_critical: 0, open_warning: 5 }, tasks, 'ok')
    expect(s.urgency).toBe(URGENCY.UNKNOWN)
    expect(s.lead).toBe('아래가 전부는 아니에요. 손볼 일 3가지를 아직 불러오지 못했어요.')
  })

  it('받아온 것이 서버가 센 것과 맞으면 잘렸다고 말하지 않는다', () => {
    const tasks = buildTasks([
      alert({ id: 1, rule: 'file_permission' }),
      alert({ id: 2, rule: 'file_permission' }),
    ])
    const s = statusOf({ status: 'DEFCON 3', open_critical: 0, open_warning: 2 }, tasks, 'ok')
    expect(s.urgency).toBe(URGENCY.CARE)
    expect(s.lead).not.toContain('불러오지 못했어요')
  })

  it('DEFCON 3 이 아니어도 할 일이 있으면 살펴보세요로 올린다', () => {
    const tasks = buildTasks([alert({ rule: 'pending_security_updates' })])
    const s = statusOf({ status: 'OK', open_critical: 0, open_warning: 1 }, tasks, 'ok')
    expect(s.label).toBe('살펴보세요')
  })

  // 개수만 넘기는 예전 호출 방식. 종류를 알 수 없으니 위생 작업 문장을 쓴다.
  it('할 일 목록 대신 개수만 넘기면 위생 작업 문장을 쓴다', () => {
    const s = statusOf({ status: 'DEFCON 3', open_critical: 0, open_warning: 0 }, 3, 'ok')
    expect(s.urgency).toBe(URGENCY.CARE)
    expect(s.lead).toBe('손볼 일이 3가지 있어요. 급하지는 않지만 오늘 중에 해두는 게 좋아요.')
  })

  // 예전에는 침입 신호나 판단 못 한 것이 하나라도 있으면 먼저 반환해 버려서,
  // 나머지를 못 받았다는 말이 사라졌다. 가장 급한 신호를 말하면서도 못 받은 것은 함께 알린다.
  it('침입 신호가 있어도 못 받은 알림이 있으면 함께 말한다', () => {
    const tasks = buildTasks([alert({ rule: 'new_login_ip', title_ko: '처음 보는 곳에서 로그인' })])
    const s = statusOf({ status: 'DEFCON 3', open_critical: 0, open_warning: 50 }, tasks, 'ok')
    expect(s.urgency).toBe(URGENCY.SIGNAL)
    expect(s.lead).toContain('직접 하신 일이 아니라면 오늘 바로 확인하세요.')
    expect(s.lead).toContain('아직 불러오지 못한 일이 49가지 더 있어요.')
  })

  it('판단 못 한 것이 있어도 못 받은 알림이 있으면 함께 말한다', () => {
    const tasks = buildTasks([alert({ rule: 'monitor_blind_spot' })])
    const s = statusOf({ status: 'DEFCON 3', open_critical: 0, open_warning: 4 }, tasks, 'ok')
    expect(s.urgency).toBe(URGENCY.UNKNOWN)
    expect(s.lead).toContain('지킴이가 판단하지 못한 일이에요.')
    expect(s.lead).toContain('아직 불러오지 못한 일이 3가지 더 있어요.')
  })

  it('침입 신호를 다 받았으면 못 받았다는 말을 붙이지 않는다', () => {
    const tasks = buildTasks([alert({ rule: 'new_login_ip', title_ko: '처음 보는 곳에서 로그인' })])
    const s = statusOf({ status: 'DEFCON 3', open_critical: 0, open_warning: 1 }, tasks, 'ok')
    expect(s.urgency).toBe(URGENCY.SIGNAL)
    expect(s.lead).not.toContain('불러오지 못한')
  })
})
