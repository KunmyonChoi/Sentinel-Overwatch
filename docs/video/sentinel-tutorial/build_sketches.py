#!/usr/bin/env python3
"""스케치 패스 — 장면 12개의 와이어프레임을 뽑는다.

스케치는 '실제 문구가 들어간 배치도'다. 색은 frame.md 의 바탕·글·강조 셋만
쓰고, 카드는 빈 상자로 둔다. 모션은 없다(빈 타임라인만 등록한다).

한 벌로 뽑는 이유: 열두 장이 자막 띠·안전 여백·장 제목 자리를 똑같이 지켜야
하는데, 손으로 열두 번 쓰면 반드시 어긋난다. 빌드 패스에서 각 장면을 직접
꾸밀 때는 이 파일이 아니라 뽑힌 HTML 을 고친다.
"""
import html
import pathlib

W, H = 1920, 1080
BAND = 220                 # 자막 띠 높이
CONTENT_H = H - BAND       # 860
PAD = 150                  # 좌우 안전 여백

BG, CARD, PANEL2 = "#eef3f0", "#ffffff", "#f5f8f6"
INK, MUTED, ACCENT = "#17221d", "#5c6b64", "#0e7c6b"
LINE, LINE2, ACC_SOFT = "#dfe7e3", "#c7d4ce", "#d9ece7"
WARN, CRIT = "#b8860b", "#b3261e"
DARK, NEON, NEON_DIM = "#0a0f0d", "#00ff41", "rgba(0,255,65,0.45)"

KR = "'IBM Plex Sans KR','Apple SD Gothic Neo','Malgun Gothic',system-ui,sans-serif"
MONO = "'JetBrains Mono','Fira Code',monospace"

_parts: list[str] = []


def el(x, y, w, h, content="", *, size=26, weight=400, color=INK, bg=None,
       border=None, radius=0, align="left", lh=1.5, mono=False, extra="", eid=None):
    s = [f"position:absolute", f"left:{x}px", f"top:{y}px", f"width:{w}px"]
    if h is not None:
        s.append(f"height:{h}px")
    s += [f"font-family:{MONO if mono else KR}", f"font-size:{size}px",
          f"font-weight:{weight}", f"color:{color}", f"line-height:{lh}",
          f"text-align:{align}", "word-break:keep-all"]
    if bg: s.append(f"background:{bg}")
    if border: s.append(f"border:{border}")
    if radius: s.append(f"border-radius:{radius}px")
    if extra: s.append(extra)
    i = f' id="{eid}"' if eid else ""
    _parts.append(f'<div{i} style="{";".join(s)};">{content}</div>')


def box(x, y, w, h, *, bg=None, border=None, radius=12, extra=""):
    """빈 상자 — 스케치에서 '여기 무언가 들어간다'를 뜻한다."""
    el(x, y, w, h, "", bg=bg, border=border or f"1px dashed {LINE2}",
       radius=radius, extra=extra)


def head(eyebrow, title, *, dark=False):
    el(PAD, 70, 1400, 40, eyebrow, size=30, weight=700,
       color=NEON if dark else ACCENT)
    el(PAD, 112, 1500, 82, title, size=62, weight=700,
       color=NEON if dark else INK)


def band(text):
    """자막 띠 — 절대 움직이지 않는 자리."""
    el(0, CONTENT_H, W, BAND, "", bg=INK)
    el(PAD, CONTENT_H + 56, W - PAD * 2, 108, text, size=38, color="#ffffff", lh=1.55)


# ─────────────────────────────────────────────────────────── 장면 정의

def f01():
    el(0, 0, W, CONTENT_H, "", bg=BG)
    el(0, 0, 22, CONTENT_H, "", bg=ACCENT)
    el(PAD, 300, 1400, 50, "개인 컴퓨터를 혼자 관리하는 분을 위한", size=34, color=ACCENT)
    el(PAD, 362, 1560, 240, "내 컴퓨터 지킴이<br>사용 안내", size=104, weight=700, lh=1.14)
    el(PAD, 636, 1400, 50, "보안을 몰라도 됩니다. 화면이 무엇을 해야 할지 알려줍니다.",
       size=32, color=MUTED)
    band("내 컴퓨터 지킴이. 보안을 모르는 사람이 자기 컴퓨터를 스스로 지킬 수 있게 만든 도구입니다.")


def f02():
    el(0, 0, W, CONTENT_H, "", bg=DARK)
    head("1장", "왜 필요한가", dark=True)
    logs = [
        "Feb  3 04:12:07 host sshd[2211]: Failed password for invalid user admin from 203.0.113.9 port 41022 ssh2",
        "Feb  3 04:12:09 host sshd[2213]: Failed password for invalid user test from 203.0.113.9 port 41031 ssh2",
        "Feb  3 04:12:11 host sshd[2215]: Invalid user oracle from 203.0.113.9 port 41044",
    ]
    for i, ln in enumerate(logs):
        el(PAD, 262 + i * 42, 1620, 34, html.escape(ln), size=21, color=NEON_DIM, mono=True)
    el(PAD, 262 + 42, 1620, 34, html.escape(logs[1]), size=21, color=NEON, mono=True)
    el(PAD, 440, 60, 50, "↓", size=44, color=NEON_DIM)
    # 사람 말로 바뀐 카드
    el(PAD, 512, 1160, 200, "", bg=CARD, radius=16, border=f"1px solid {LINE}")
    box(PAD + 34, 546, 64, 64, radius=32)
    el(PAD + 126, 550, 940, 46, "처음 보는 곳에서 계정 이름을 찍어보고 있어요",
       size=34, weight=700)
    el(PAD + 126, 606, 940, 40, "모두 막혔어요. 따로 하실 일은 없어요.", size=26, color=MUTED)
    band("문제는 그 기록을 아무도 읽지 않는다는 것입니다. 읽으려 해도 어렵습니다.")


def f03():
    el(0, 0, W, CONTENT_H, "", bg=BG)
    head("2장", "화면 구성")
    # 초보자 모드 덩이
    el(PAD, 250, 1060, 250, "", bg=PANEL2, radius=16, border=f"1px solid {LINE}")
    el(PAD + 28, 274, 500, 36, "초보자 모드 — 쉬운 화면", size=26, weight=700, color=ACCENT)
    for i, name in enumerate(["홈", "할 일 상세", "기록", "자세히 보기"]):
        bx = PAD + 28 + i * 254
        el(bx, 322, 230, 150, "", bg=CARD, radius=12, border=f"1px dashed {LINE2}")
        el(bx, 386, 230, 34, name, size=26, align="center")
    # 전문가 모드 덩이
    el(PAD, 560, 1060, 210, "", bg=DARK, radius=16)
    el(PAD + 28, 584, 600, 36, "전문가 모드 — 대시보드", size=26, weight=700, color=NEON)
    el(PAD + 28, 632, 1004, 112, "", border=f"1px dashed {NEON_DIM}", radius=12)
    el(PAD + 28, 674, 1004, 34, "예전 대시보드 그대로 · 패널 11개를 한 화면에",
       size=26, color=NEON_DIM, align="center")
    # 모드 전환기 확대
    el(1300, 250, 470, 40, "오른쪽 위에서 바꿉니다", size=28, weight=700)
    el(1300, 312, 440, 76, "", bg=PANEL2, radius=14, border=f"1px solid {LINE}")
    el(1310, 322, 210, 56, "쉬운 화면", size=26, align="center", bg=CARD,
       radius=10, border=f"1px solid {LINE}", extra="line-height:56px")
    el(1526, 322, 204, 56, "전문가 화면", size=26, align="center", color=MUTED,
       extra="line-height:56px")
    el(1300, 424, 470, 200,
       "고른 화면은 기억됩니다.<br><br>자세히 보기는 여기 없습니다 —<br>그것도 초보자 화면이라<br>홈 본문 링크로 들어갑니다.",
       size=25, color=MUTED, lh=1.7)
    band("화면은 두 가지입니다. 쉬운 화면과 전문가 화면. 오른쪽 위에서 언제든 바꿀 수 있고, 고른 화면은 기억됩니다.")


def screen(x, y, w, h, top_left, *, right=None):
    """화면 목업 창틀."""
    el(x, y, w, h, "", bg=CARD, radius=18, border=f"1px solid {LINE}",
       extra="box-shadow:0 24px 60px rgba(23,34,29,0.16)")
    el(x, y, w, 62, "", bg=PANEL2, radius=18)
    el(x, y + 44, w, 18, "", bg=PANEL2)
    el(x, y + 61, w, 1, "", bg=LINE)
    el(x + 26, y + 16, 600, 32, top_left, size=22, weight=700)
    if right:
        el(x + w - 330, y + 16, 300, 32, right, size=20, color=MUTED, align="right")


def f04():
    el(0, 0, W, CONTENT_H, "", bg=BG)
    head("3장 · 시나리오 하나", "아무 일 없는 날")
    sx, sy, sw = 320, 250, 1280
    screen(sx, sy, sw, 570, "🛡 내 컴퓨터 지킴이", right="쉬운 화면 | 전문가 화면")
    box(sx + 56, sy + 122, 96, 96, radius=48)
    el(sx + 186, sy + 128, 700, 70, "이상 없음", size=56, weight=700)
    el(sx + 186, sy + 204, 800, 40, "지금 손볼 일이 없어요. 이 창을 닫으셔도 돼요.",
       size=26, color=MUTED)
    for i, (lab, val) in enumerate([("밖에서 들어올 수 있는 문", "1개"),
                                    ("밀린 보안 업데이트", "없음"),
                                    ("막은 접속 시도", "23번")]):
        bx = sx + 40 + i * 400
        el(bx, sy + 292, 380, 170, "", bg=CARD, radius=14, border=f"1px solid {LINE}")
        el(bx + 24, sy + 316, 332, 32, lab, size=21, color=MUTED)
        el(bx + 24, sy + 360, 332, 56, val, size=44, weight=700)
    el(sx + 40, sy + 486, 1200, 56, "할 일 카드가 들어갈 자리 — 오늘은 비어 있습니다",
       size=24, color=MUTED, align="center", border=f"1px dashed {LINE2}",
       radius=12, extra="line-height:56px")
    band("화면에서 가장 큰 글씨가 '이상 없음'이면, 정말로 아무것도 하지 않으셔도 됩니다.")


def steps(active, labels):
    """① → ② → ③ 진행 막대. 지금 보는 자리를 표시한다."""
    for i, lab in enumerate(labels):
        bx = PAD + i * 300
        on = i == active
        el(bx, 236, 270, 52, lab, size=24, align="center",
           color="#ffffff" if on else MUTED, bg=ACCENT if on else None,
           radius=26, border=None if on else f"1px solid {LINE2}",
           extra="line-height:52px")


def f05():
    el(0, 0, W, CONTENT_H, "", bg=BG)
    head("3장 · 시나리오 둘", "손볼 일이 생겼다")
    steps(1, ["① 할 일 카드", "② 미리보기", "③ 결과"])
    sx, sy, sw = 320, 316, 1280
    screen(sx, sy, sw, 500, "←  돌아가기", right="쉬운 화면 | 전문가 화면")
    el(sx + 40, sy + 96, 900, 48, "다른 사람이 고칠 수 있는 파일 3개", size=36, weight=700)
    el(sx + 40, sy + 158, 1200, 46, "무엇이 바뀌는지 먼저 보여드릴게요",
       size=24, weight=700, color=MUTED, bg=PANEL2, radius=10,
       extra="line-height:46px;padding-left:20px")
    for i, (a, b, c) in enumerate([
            ("로그인할 때 실행되는 설정", "누구나 고칠 수 있음", "나만 고칠 수 있음"),
            ("터미널을 열 때 실행되는 설정", "누구나 고칠 수 있음", "나만 고칠 수 있음"),
            ("내가 설치한 프로그램 폴더", "누구나 넣을 수 있음", "나만 넣을 수 있음")]):
        ry = sy + 224 + i * 52
        el(sx + 40, ry, 480, 36, a, size=23)
        el(sx + 540, ry, 300, 36, b, size=21, color=MUTED)
        el(sx + 850, ry, 40, 36, "→", size=22, color=LINE2)
        el(sx + 900, ry, 300, 36, c, size=21, weight=700, color=ACCENT)
    el(sx + 40, sy + 396, 200, 60, "잠그기", size=26, color="#ffffff", bg=ACCENT,
       radius=30, align="center", extra="line-height:60px")
    el(sx + 260, sy + 396, 200, 60, "나중에", size=26, align="center",
       border=f"1px solid {LINE2}", radius=30, extra="line-height:60px")
    band("누르면 바로 고치지 않습니다. 먼저 무엇이 어떻게 바뀌는지 표로 보여드립니다.")


def f06():
    el(0, 0, W, CONTENT_H, "", bg=BG)
    head("3장 · 시나리오 셋", "지킴이가 대신 못 하는 일")
    sx, sy, sw = PAD, 250, 1060
    screen(sx, sy, sw, 570, "←  돌아가기")
    el(sx + 40, sy + 96, 700, 36, "지금 확인하세요", size=24, weight=700, color=CRIT)
    el(sx + 40, sy + 142, 900, 50, "처음 보는 곳에서 로그인에 성공했어요",
       size=36, weight=700)
    for i, (k, v) in enumerate([("언제", "오늘 새벽 3시 12분"),
                                ("어디서", "해외 · 지금까지 접속한 적 없는 곳"),
                                ("어떻게", "미리 등록해 둔 열쇠로 들어왔어요")]):
        ry = sy + 214 + i * 46
        el(sx + 40, ry, 120, 34, k, size=22, color=MUTED)
        el(sx + 180, ry, 800, 34, v, size=23)
    el(sx + 40, sy + 372, 900, 44, "이때 직접 접속하셨나요?", size=28, weight=700)
    for i, (lab, col) in enumerate([("네, 제가 했어요", LINE2), ("아니요, 제가 안 했어요", CRIT),
                                    ("잘 모르겠어요", LINE2)]):
        el(sx + 40 + i * 330, sy + 432, 300, 62, lab, size=24, align="center",
           color=CRIT if col == CRIT else INK, border=f"1px solid {col}",
           radius=31, extra="line-height:62px")
    el(sx + 40, sy + 516, 980, 50, "👁  지킴이가 본 것  1건  —  열어보기", size=23,
       color=ACCENT, bg=ACC_SOFT, radius=10, extra="line-height:50px;padding-left:20px")
    # 세 갈래
    el(1300, 250, 470, 44, "답에 따라 갈립니다", size=30, weight=700)
    for i, (q, r) in enumerate([("네, 제가 했어요", "확인 처리하고 닫습니다"),
                                ("아니요", "긴급으로 올리고 순서대로 안내"),
                                ("잘 모르겠어요", "열어둔 채 재촉하지 않습니다")]):
        ry = 322 + i * 150
        el(1300, ry, 470, 38, q, size=25, weight=700)
        el(1300, ry + 46, 470, 76, r, size=24, color=MUTED, lh=1.55)
    el(1300, 762, 470, 46, "복사하면 이름·주소는 가려집니다", size=23, color=ACCENT)
    band("그래서 고치지 않고 사실만 보여드리고 물어봅니다. 언제, 어디서, 어떻게 들어왔는지.")


def f07():
    el(0, 0, W, CONTENT_H, "", bg=BG)
    head("4장", "할 수 있는 일")
    items = [
        ("SSH 로그인 실패·성공", "auth.log"), ("sudo 사용과 계정 변경", "auth.log"),
        ("브루트포스 차단 상태", "fail2ban"), ("새로 열린 포트", "ss"),
        ("밖에서 실제로 닿는지", "ufw · iptables"), ("너무 열린 파일 권한", "자체 점검"),
        ("설정 파일 변조", "SHA-256 기준선"), ("자동 실행 지점 변경", "SHA-256 기준선"),
        ("리버스 셸·임시 실행", "/proc"), ("패키지 변경·밀린 업데이트", "dpkg · apt"),
        ("이 서버에 영향 있는 취약점", "Ubuntu USN"), ("누가 무엇을 실행했나", "auditd"),
    ]
    for i, (name, src) in enumerate(items):
        col, row = i % 2, i // 2
        bx = PAD + col * 820
        by = 250 + row * 96
        el(bx, by, 780, 80, "", bg=CARD, radius=12, border=f"1px solid {LINE}")
        el(bx + 24, by + 14, 560, 36, name, size=26)
        el(bx + 24, by + 50, 700, 26, src, size=19, color=ACCENT)
    band("SSH 로그인 실패와 성공, sudo 사용, 계정 변경. 브루트포스 차단 상태.")


def f08():
    el(0, 0, W, CONTENT_H, "", bg=BG)
    head("4장", "할 수 없는 일")
    items = [
        ("백신이 아닙니다", "파일을 뒤져 악성코드를 찾지 않습니다"),
        ("침입 차단 장비가 아닙니다", "네트워크 패킷을 뜯어보지 않습니다"),
        ("본인이 한 일인지 모릅니다", "그래서 묻습니다"),
        ("커널까지 장악당한 뒤라면", "같은 커널 위에서 도는 이 도구도 속습니다"),
        ("직접 막지 않습니다", "막는 것은 fail2ban 과 방화벽입니다"),
        ("공유기 바깥은 모릅니다", "포트를 넘겨주는지 안에서는 알 수 없습니다"),
    ]
    for i, (name, sub) in enumerate(items):
        col, row = i % 2, i // 2
        bx = PAD + col * 820
        by = 250 + row * 130
        el(bx, by, 780, 112, "", bg=CARD, radius=12, border=f"1px solid {LINE}")
        el(bx + 24, by + 18, 700, 40, name, size=28, weight=700)
        el(bx + 24, by + 62, 720, 34, sub, size=22, color=MUTED)
    el(PAD, 664, 1620, 60, "할 수 없는 일을 할 수 있다고 말하지 않는 것이, 이 도구의 첫 번째 원칙입니다.",
       size=30, weight=700, color=ACCENT, align="center", extra="line-height:60px")
    band("할 수 없는 것. 백신이 아닙니다. 파일을 뒤져 악성코드를 찾아내지 않습니다.")


def f09():
    el(0, 0, W, CONTENT_H, "", bg=DARK)
    head("5장", "설치", dark=True)
    el(PAD, 250, 1620, 150, "", border=f"1px solid {NEON_DIM}", radius=12)
    el(PAD + 30, 276, 1560, 40, "$ deploy/build-release.sh --wheels",
       size=26, color=NEON, mono=True)
    el(PAD + 30, 326, 1560, 40, "$ sudo secdash-&lt;ver&gt;/deploy/install.sh",
       size=26, color=NEON, mono=True)
    el(PAD, 428, 700, 40, "스크립트가 하는 일", size=28, weight=700, color=NEON)
    for i, s in enumerate(["호스트 도구 설치·활성화 (fail2ban · rsyslog · auditd · lynis)",
                           "전용 계정 secdash 생성",
                           "/opt/secdash 복사와 가상환경",
                           "설정 파일 /etc/secdash/secdash.env",
                           "최소 권한 sudoers 와 systemd 유닛",
                           "서비스 시작"]):
        el(PAD, 486 + i * 46, 1400, 36, f"✓  {s}", size=25, color=NEON_DIM, mono=False)
    el(PAD, 772, 800, 44, "API token: ••••••••", size=26, color=NEON, mono=True)
    band("설치는 두 줄입니다. 빌드 머신에서 압축본을 만들고, 대상 서버에서 설치 스크립트를 실행합니다.")


def f10():
    el(0, 0, W, CONTENT_H, "", bg=DARK)
    head("6장", "설정", dark=True)
    el(PAD, 240, 1120, 560, "", border=f"1px solid {NEON_DIM}", radius=12)
    el(PAD + 30, 262, 1000, 34, "/etc/secdash/secdash.env", size=22, color=NEON, mono=True)
    lines = [
        ("SECDASH_HOST=127.0.0.1", 0), ("SECDASH_PORT=8000", 0),
        ("SECDASH_AUTH_LOG=/var/log/auth.log", 0),
        ("SECDASH_FAIL2BAN_JAIL=sshd", 0), ("", 0),
        ("SLACK_WEBHOOK_URL=https://hooks.slack.com/...", 1),
        ("SECDASH_HOST_ROLE=개발 서버, 외부 파일 유입 없음", 1),
        ("# fail2ban ignoreip → deploy/fail2ban-secdash.conf", 1),
        ("", 0), ("SECDASH_USN_MATCH=1", 0),
        ("SECDASH_EVENT_RETENTION_DAYS=30", 0),
    ]
    for i, (ln, hot) in enumerate(lines):
        el(PAD + 30, 312 + i * 42, 1060, 34, html.escape(ln), size=22, mono=True,
           color=NEON if hot else NEON_DIM)
    el(1340, 240, 430, 44, "서버마다 채우는 셋", size=30, weight=700, color=NEON)
    for i, (n, d) in enumerate([("Slack 웹훅", "알림 제목에 호스트 이름이 붙습니다"),
                                ("서버 역할 메모", "AI 에게 물을 때 맥락으로 나갑니다"),
                                ("ignoreip", "자기 자신을 차단하지 않게")]):
        ry = 312 + i * 150
        el(1340, ry, 430, 38, f"{i+1}. {n}", size=26, weight=700, color=NEON)
        el(1340, ry + 46, 430, 80, d, size=23, color=NEON_DIM, lh=1.55)
    el(PAD, 828, 1620, 0, "🔒  호스트 로그는 어떤 경우에도 밖으로 나가지 않습니다",
       size=26, color=NEON)
    band("설정은 한 파일입니다. /etc/secdash/secdash.env. 기본값만으로도 돕니다.")


def f11():
    el(0, 0, W, CONTENT_H, "", bg=BG)
    head("7장", "아키텍처")
    el(PAD, 246, 620, 40, "진실의 원천 — 검증된 호스트 도구", size=26, weight=700, color=MUTED)
    for i, (n, d) in enumerate([("fail2ban", "IP 차단"), ("rsyslog · auth.log", "로그인·sudo"),
                                ("dpkg · apt", "패키지 변경"), ("auditd", "명령 실행 주체"),
                                ("Lynis", "설정 강화 감사"), ("Ubuntu USN", "취약점 공지")]):
        by = 300 + i * 84
        el(PAD, by, 620, 68, "", bg=CARD, radius=12, border=f"1px solid {LINE}")
        el(PAD + 22, by + 12, 380, 34, n, size=25, weight=700)
        el(PAD + 22, by + 12, 576, 34, d, size=21, color=MUTED, align="right")
    for i in range(6):
        el(800, 314 + i * 84, 80, 40, "→", size=32, color=LINE2, align="center")
    el(920, 246, 620, 40, "지킴이가 하는 일", size=26, weight=700, color=ACCENT)
    for i, (n, d) in enumerate([("구조화", "줄글을 필드로"), ("상관 분석", "흩어진 것을 하나로"),
                                ("한국어로", "사람의 말로"), ("알림 하나로", "지금 할 일만")]):
        by = 300 + i * 108
        el(920, by, 620, 92, "", bg=CARD, radius=12, border=f"1px solid {LINE}")
        el(920 + 22, by + 14, 576, 36, n, size=26, weight=700, color=ACCENT)
        el(920 + 22, by + 52, 576, 30, d, size=21, color=MUTED)
    el(1600, 300, 170, 300, "지킴이를<br>꺼도<br>보안은<br>그대로<br>남습니다",
       size=26, weight=700, lh=1.7)
    el(PAD, 796, 1620, 44, "사실은 이벤트로  →  판단은 알림으로  →  위험 단계는 열린 알림에서만",
       size=25, color=MUTED, align="center")
    band("구조는 단순합니다. 지킴이는 새로운 보안 장치를 만들지 않습니다.")


def f12():
    el(0, 0, W, CONTENT_H, "", bg=ACCENT)
    el(PAD, 180, 1400, 100, "기억할 것은 셋", size=78, weight=700, color="#ffffff")
    for i, (n, d) in enumerate([
            ("할 일이 없으면 아무 말도 하지 않습니다", "대부분의 날이 그렇습니다."),
            ("고치기 전에 무엇이 바뀌는지 먼저 보여줍니다", "보고 나서 정하시면 됩니다."),
            ("모르는 것은 모른다고 말합니다", "사용자만 아는 것은 사용자에게 묻습니다.")]):
        by = 350 + i * 150
        el(PAD, by, 64, 64, str(i + 1), size=30, weight=700, color=ACCENT, bg="#ffffff",
           radius=32, align="center", extra="line-height:64px")
        el(PAD + 96, by + 2, 1400, 46, n, size=36, weight=700, color="#ffffff")
        el(PAD + 96, by + 56, 1400, 40, d, size=26, color="rgba(255,255,255,0.8)")
    band("정리하겠습니다. 이 도구는 세 가지를 지킵니다.")


FRAMES = [
    ("01-title", "f01-title", 17, f01),
    ("02-why", "f02-why", 49, f02),
    ("03-map", "f03-map", 47, f03),
    ("04-scenario-calm", "f04-calm", 34, f04),
    ("05-scenario-fix", "f05-fix", 59, f05),
    ("06-scenario-judge", "f06-judge", 61, f06),
    ("07-can", "f07-can", 50, f07),
    ("08-cannot", "f08-cannot", 52, f08),
    ("09-install", "f09-install", 47, f09),
    ("10-config", "f10-config", 65, f10),
    ("11-architecture", "f11-arch", 63, f11),
    ("12-closing", "f12-closing", 29, f12),
]

TPL = """<!doctype html>
<html lang="ko">
  <head>
    <meta charset="UTF-8" />
    <title>{title}</title>
  </head>
  <body>
    <template>
      <style>
        #{cid} {{ position: relative; width: {w}px; height: {h}px; overflow: hidden;
                  background: {bg}; }}
        #{cid} * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        #{cid} .clip {{ position: absolute; inset: 0; }}
      </style>
      <div id="{cid}" data-composition-id="{cid}" data-start="0"
           data-width="{w}" data-height="{h}" data-duration="{dur}">
        <div class="clip" data-start="0" data-duration="{dur}">
{body}
        </div>
      </div>
      <script>
        // 스케치 패스 — 배치만 확인한다. 모션은 빌드 패스에서 붙인다.
        window.__timelines["{cid}"] = gsap.timeline({{ paused: true }});
      </script>
    </template>
  </body>
</html>
"""


def main():
    out = pathlib.Path(__file__).parent / "compositions" / "frames"
    out.mkdir(parents=True, exist_ok=True)
    for name, cid, dur, fn in FRAMES:
        _parts.clear()
        fn()
        body = "\n".join("          " + p for p in _parts)
        (out / f"{name}.html").write_text(
            TPL.format(title=name, cid=cid, w=W, h=H, dur=dur, bg=BG, body=body),
            encoding="utf-8")
        print(f"  {name}.html  ({len(_parts)} 요소, {dur}s)")


if __name__ == "__main__":
    main()
