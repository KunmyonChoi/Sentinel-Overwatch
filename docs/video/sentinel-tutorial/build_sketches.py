#!/usr/bin/env python3
"""스케치 패스 — 장면 16개의 와이어프레임을 뽑는다.

스케치는 '실제 문구가 들어간 배치도'다. 색은 frame.md 의 바탕·글·강조 셋만
쓰고, 카드는 빈 상자로 둔다. 모션은 없다(빈 타임라인만 등록한다).

한 벌로 뽑는 이유: 열여섯 장이 자막 띠·안전 여백·장 제목 자리를 똑같이 지켜야
하는데, 손으로 열여섯 번 쓰면 반드시 어긋난다. 빌드 패스에서 각 장면을 직접
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


def station(x, y, w, h, n, title, lines, *, dark=False, accent=False):
    """정거장 하나. 번호 · 제목 · 설명 줄."""
    el(x, y, w, h, "", bg=DARK if dark else CARD, radius=14,
       border=f"1px solid {ACCENT if accent else LINE}")
    c = NEON if dark else (ACCENT if accent else MUTED)
    el(x + 22, y + 18, 40, 30, n, size=22, weight=700, color=c)
    el(x + 22, y + 54, w - 44, 40, title, size=28, weight=700,
       color=NEON if dark else INK)
    for i, ln in enumerate(lines):
        el(x + 22, y + 104 + i * 34, w - 44, 30, ln, size=21,
           color=NEON_DIM if dark else MUTED, mono=dark)


def f09():
    el(0, 0, W, CONTENT_H, "", bg=BG)
    head("5장", "설치")
    xs = [150, 563, 976, 1389]
    station(xs[0], 290, 380, 210, "1", "빌드 머신",
            ["$ deploy/build-release.sh", "tar.gz + sha256", "dist 포함 · 비밀 제외"], dark=True)
    station(xs[1], 290, 380, 210, "2", "install.sh",
            ["전용 계정 · capability", "systemd · sudoers",
             "fail2ban · auditd · Lynis"], accent=True)
    station(xs[2], 290, 380, 210, "3", "harden.sh",
            ["dry-run 으로 목록 확인", "→ --apply 로 적용",
             "역할별 플래그"], accent=True)
    station(xs[3], 290, 380, 210, "4", "Lynis 크론",
            ["하루 한 번", "새 경고·지수 하락만 알림", "제안은 백로그"])
    for i in range(3):
        el(xs[i] + 380, 372, 33, 46, "→", size=30, color=LINE2, align="center")
    el(150, 268, 380, 26, "scp", size=20, color=MUTED, align="center")
    # 되돌아오는 고리 — 이 장의 요점
    el(xs[2] + 40, 540, xs[3] - xs[2] + 300, 3, "", bg=ACCENT)
    el(xs[2] + 40, 512, 40, 30, "↖", size=26, color=ACCENT)
    el(xs[2], 560, 780, 40,
       "결정(적용 · 수용 · 이미 해결)이 다시 프로파일과 플래그로 돌아간다",
       size=23, color=ACCENT)
    el(150, 650, 1620, 44, "설치는 한 번이지만, 강화는 한 바퀴를 도는 일이다",
       size=28, weight=700, align="center")
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
    head("7장 · 아키텍처 ①", "어디서 들어오나")
    el(150, 236, 900, 30, "호스트 진실 원천 — root 소유 데몬·로그·/proc",
       size=21, color=MUTED)
    srcs = [("auth.log · audit.log", "rsyslog · auditd"), ("dpkg.log · apt", "패키지 변경"),
            ("/proc", "소켓 · 프로세스 · fd"), ("/etc · cron · systemd", "설정 · 영속화 · SUID"),
            ("fail2ban", "차단의 진실 원천"), ("USN · 뉴스 RSS", "공개 URL 읽기만")]
    for i, (n, d) in enumerate(srcs):
        bx, ext = 150 + i * 274, i == 5
        el(bx, 274, 250, 104, "", bg="#f6e7cf" if ext else CARD, radius=10,
           border=f"1px dashed #b8731c" if ext else f"1px solid {LINE}")
        el(bx + 16, 292, 218, 34, n, size=23, weight=700,
           color="#b8731c" if ext else INK)
        el(bx + 16, 330, 218, 30, d, size=19, color=MUTED)
        el(bx + 105, 386, 40, 34, "↓", size=24, color="#b8731c" if ext else LINE2)
    # 백엔드 경계
    el(120, 424, 1680, 232, "", border=f"1px dashed {ACCENT}", radius=14)
    el(140, 434, 1000, 28, "secdash.service · User=secdash · 127.0.0.1:8000", size=19, color=ACCENT)
    mons = [("AuthLog · Audit", "실패 창 · 실패 후 성공"), ("UpdateMonitor", "설치/제거 · 미적용"),
            ("Network · Process", "새 리스너 · 리버스 셸"), ("Integrity · Persistence", "기준선 diff"),
            ("Fail2banSync", "30초 동기화"), ("IntelMonitor", "USN ↔ 설치 버전")]
    for i, (n, d) in enumerate(mons):
        bx = 150 + i * 274
        el(bx, 472, 250, 96, "", bg=CARD, radius=10, border=f"1.5px solid {ACCENT}")
        el(bx + 16, 488, 218, 34, n, size=22, weight=700)
        el(bx + 16, 524, 218, 30, d, size=19, color=MUTED)
        el(bx + 105, 576, 40, 30, "↓", size=22, color=LINE2)
    el(190, 616, 1540, 5, "", bg=ACCENT)
    el(150, 676, 760, 40, "사실은 이벤트로", size=26, weight=700, color=ACCENT)
    el(150, 716, 760, 34, "일어난 일. 심각도 없음. 근거로 남는다.", size=21, color=MUTED)
    el(1010, 676, 760, 40, "판단은 알림으로", size=26, weight=700, color=ACCENT)
    el(1010, 716, 760, 34, "묶어서 내린 결론. 사람의 시간을 요구한다.", size=21, color=MUTED)
    band("맨 위가 진실의 원천입니다. 전부 root가 소유한 데몬과 로그입니다. 지킴이가 만든 것은 하나도 없습니다.")


def f12():
    el(0, 0, W, CONTENT_H, "", bg=BG)
    head("7장 · 아키텍처 ②", "어디에 쌓이고 어디로 나가나")
    el(190, 232, 1540, 5, "", bg=ACCENT)
    el(150, 244, 900, 28, "앞 장의 이벤트 버스", size=19, color=ACCENT)
    # SQLite
    el(150, 288, 680, 292, "", bg=PANEL2, radius=12, border=f"1px solid {LINE}")
    el(172, 308, 600, 36, "SQLite  (WAL)", size=25, weight=700)
    for i, ln in enumerate(["events                원시 이벤트 · 30일",
                            "alerts                 열림/확인/해결 · 90일",
                            "integrity_baselines    파일·cron·systemd 기준선",
                            "known_login_ips        처음 보는 주소",
                            "blocked_ips            fail2ban 미러",
                            "maintenance_windows    점검 모드 창"]):
        el(172, 356 + i * 36, 640, 30, html.escape(ln), size=19, color=MUTED, mono=True)
    # 판단
    el(870, 288, 330, 136, "", bg=ACC_SOFT, radius=12, border=f"1.5px solid {ACCENT}")
    el(890, 308, 290, 36, "알림 엔진", size=25, weight=700, color=ACCENT)
    el(890, 350, 290, 60, "같은 지문 → 횟수 +1<br>심각도 상승 → 재오픈", size=20, color=MUTED, lh=1.5)
    el(870, 444, 330, 136, "", bg=ACC_SOFT, radius=12, border=f"1.5px solid {ACCENT}")
    el(890, 464, 290, 36, "DefconWatcher", size=25, weight=700, color=ACCENT)
    el(890, 506, 290, 60, "10초마다<br>열린 알림만 센다", size=20, color=MUTED, lh=1.5)
    el(1240, 288, 300, 292, "", bg=ACC_SOFT, radius=12, border=f"1.5px solid {ACCENT}")
    el(1260, 308, 260, 36, "알림 큐", size=25, weight=700, color=ACCENT)
    el(1260, 350, 260, 120, "워커 스레드 1개<br>분당 10건<br>초과분은 묶어서<br>모니터를 막지 않음",
       size=20, color=MUTED, lh=1.6)
    el(1580, 288, 190, 136, "", bg=PANEL2, radius=12, border=f"1px solid {LINE}")
    el(1600, 308, 150, 36, "파일 로그", size=23, weight=700)
    el(1600, 350, 150, 56, "security.log<br>critical.log", size=19, color=MUTED, mono=True, lh=1.5)
    # API · 외부 · 브라우저
    el(150, 612, 1050, 92, "", bg=ACC_SOFT, radius=12, border=f"1.5px solid {ACCENT}")
    el(172, 630, 1000, 34, "FastAPI · 127.0.0.1:8000", size=25, weight=700, color=ACCENT)
    el(172, 666, 1000, 30, "모든 /api 요청에 X-API-Token · 원격은 SSH 터널", size=20, color=MUTED)
    for bx, n, d in [(1240, "번역 API", "뉴스 제목만"), (1520, "Slack", "웹훅 POST")]:
        el(bx, 612, 250, 92, "", bg="#f6e7cf", radius=12, border="1px dashed #b8731c")
        el(bx + 20, 630, 210, 34, n, size=23, weight=700, color="#b8731c")
        el(bx + 20, 666, 210, 30, d, size=19, color=MUTED)
    el(150, 726, 1050, 80, "", bg=CARD, radius=12, border=f"1px solid {LINE}")
    el(172, 744, 1000, 34, "브라우저 · React 대시보드", size=24, weight=700)
    el(172, 778, 1000, 28, "5초 폴링 · 토큰 헤더", size=19, color=MUTED)
    el(1240, 730, 530, 76, "나가는 것은 셋뿐 —<br>공개 피드 · 뉴스 제목 · Slack 웹훅",
       size=22, color="#b8731c", weight=700, lh=1.5)
    band("사실은 SQLite에 쌓입니다. 원시 이벤트는 30일, 알림은 90일 보관합니다.")


def f13():
    el(0, 0, W, CONTENT_H, "", bg=BG)
    head("7장 · 아키텍처 ③", "사건 하나가 지나가는 길")
    row1 = [("auth.log", "Failed password ×5", None),
            ("parse_line", "계정 · 주소 · 방식", None),
            ("Event 로그인 실패", "심각도 '정보' — 사실", None),
            ("Alert 브루트포스", "30분 안에 5회 초과", WARN),
            ("fail2ban 차단 요청", "불가하면 '차단 권고'", ACCENT)]
    row2 = [("auth.log", "Accepted password", None),
            ("상관 규칙", "실패 이력 + 처음 보는 곳 + root", None),
            ("Alert 실패 후 성공", "긴급 — 근거는 로그 줄", CRIT),
            ("DefconWatcher", "SAFE → DEFCON 1", CRIT),
            ("Slack · 대시보드", "확인하면 단계에서 빠짐", None)]
    for r, row in enumerate([row1, row2]):
        by = 258 + r * 244
        for i, (n, d, tone) in enumerate(row):
            bx = 150 + i * 330
            el(bx, by, 300, 150, "", bg=CARD, radius=12,
               border=f"1.5px solid {tone}" if tone else f"1px solid {LINE}")
            el(bx + 18, by + 22, 264, 66, n, size=24, weight=700, color=tone or INK, lh=1.3)
            el(bx + 18, by + 94, 264, 56, d, size=20, color=MUTED, lh=1.4)
            if i < 4:
                el(bx + 300, by + 56, 30, 40, "→", size=26,
                   color=CRIT if r else LINE2, align="center")
    el(1140, 412, 400, 92, "같은 IP 의 실패 창을 유지한다", size=21, color=MUTED)
    el(1145, 412, 3, 90, "", bg=LINE2)
    el(150, 728, 1620, 44,
       "시뮬레이션 사건은 같은 길을 가되 표시가 붙어 위험 단계·Slack·fail2ban 에 닿지 않는다",
       size=23, color=MUTED, align="center")
    band("여기까지는 사실입니다. 이벤트로 남고 심각도는 '정보'입니다. 위험 단계에 영향을 주지 않습니다.")


def f14():
    el(0, 0, W, CONTENT_H, "", bg=BG)
    head("7장 · 아키텍처 ④", "알림의 생애주기와 위험 단계")
    pills = [("열림", "아직 아무도 안 봄<br>위험 단계에 반영", CRIT, CARD),
             ("확인함", "사람이 '봤다' 표시<br>단계에서 빠짐", ACCENT, ACC_SOFT),
             ("해결됨", "끝난 것<br>90일 뒤 삭제", LINE2, PANEL2)]
    for i, (n, d, col, bg) in enumerate(pills):
        bx = 260 + i * 510
        el(bx, 380, 380, 130, "", bg=bg, radius=65, border=f"2px solid {col}")
        el(bx, 404, 380, 44, n, size=32, weight=700, color=col if col != LINE2 else INK, align="center")
        el(bx, 450, 380, 52, d, size=20, color=MUTED, align="center", lh=1.4)
    for i, lab in enumerate(["확인(ack)", "해결(resolve)"]):
        el(640 + i * 510, 396, 130, 34, "→", size=30, color=LINE2, align="center")
        el(618 + i * 510, 434, 174, 30, lab, size=20, color=MUTED, align="center")
    el(618, 470, 174, 30, "← 심각도 상승", size=20, color=CRIT, align="center")
    el(450, 596, 1020, 3, "", bg=LINE2)
    el(450, 610, 1020, 40, "원인이 사라지면 시스템이 스스로 해결로 넘긴다 (자동 해결)",
       size=22, color=MUTED, align="center")
    el(260, 300, 380, 60, "같은 지문 재발 → 횟수 +1", size=21, color=MUTED, align="center")
    el(770, 300, 380, 60, "점검 모드 중 계획된 변경은<br>처음부터 '확인함'", size=21,
       color=ACCENT, align="center", lh=1.4)
    el(150, 700, 1620, 44,
       "DEFCON 1 = 열린 긴급 있음   ·   DEFCON 3 = 열린 경고 있음   ·   SAFE = 열린 것 없음",
       size=25, weight=700, align="center")
    el(150, 754, 1620, 40, "침입 신호는 점검 모드와 무관하게 언제나 '열림'",
       size=22, color=CRIT, align="center")
    band("알림에는 세 가지 상태가 있습니다. 열림, 확인함, 해결됨.")


def f15():
    el(0, 0, W, CONTENT_H, "", bg=BG)
    head("7장 · 아키텍처 ⑤", "권한의 경계, 그리고 왜 이 구조인가")
    el(150, 246, 980, 32, "지킴이는 root 로 돌지 않는다", size=24, weight=700)
    for i, h_ in enumerate(["경계", "넘는 것", "허용 방법"]):
        el(150 + [0, 330, 700][i], 292, [320, 360, 280][i], 30, h_, size=19, color=MUTED)
    rows = [("root 데몬 → secdash", "auth.log 읽기", "adm 그룹"),
            ("보호 파일 → secdash", "shadow · sudoers · authorized_keys", "CAP_DAC_READ_SEARCH"),
            ("타 사용자 프로세스", "실행 파일 · 소켓 귀속", "CAP_SYS_PTRACE"),
            ("secdash → fail2ban", "차단 · 해제 · 조회", "sudo 일곱 명령만"),
            ("브라우저 → API", "조회 · 확인 · 차단 요청", "X-API-Token · 127.0.0.1"),
            ("호스트 → 인터넷", "공개 피드 · 제목 · 웹훅", "아웃바운드 HTTPS")]
    for i, (a, b, c) in enumerate(rows):
        ry = 336 + i * 74
        el(150, ry, 980, 1, "", bg=LINE)
        el(150, ry + 16, 320, 40, a, size=22)
        el(480, ry + 16, 360, 40, b, size=21, color=MUTED)
        el(850, ry + 16, 280, 40, c, size=20, color=ACCENT, mono=True)
    el(150, 780, 980, 34, "쓰기 권한은 어디에도 없다", size=22, color=CRIT)
    el(1200, 246, 570, 32, "왜 이 구조인가", size=24, weight=700, color=ACCENT)
    for i, (n, d) in enumerate([
            ("진실 원천은 하나씩", "해석만 한다. 두 번째 사실을 만들지 않는다."),
            ("조용히 실패하지 않는다", "읽지 못하는 파일은 '정상'이 아니라 '제한'."),
            ("사실과 판단을 나눈다", "사람의 시간을 요구하는 것은 알림뿐."),
            ("호스트 로그는 안에 머문다", "한국어는 서버 안에서 템플릿으로 만든다.")]):
        ry = 300 + i * 128
        el(1200, ry, 570, 40, f"{i+1}.  {n}", size=25, weight=700)
        el(1236, ry + 46, 534, 64, d, size=21, color=MUTED, lh=1.5)
    band("마지막으로 권한입니다. 지킴이는 root로 돌지 않습니다.")


def f16():
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
    ("09-install", "f09-install", 62, f09),
    ("10-config", "f10-config", 65, f10),
    ("11-arch-sources", "f11-arch-src", 66, f11),
    ("12-arch-core", "f12-arch-core", 72, f12),
    ("13-arch-path", "f13-arch-path", 68, f13),
    ("14-arch-alert", "f14-arch-alert", 58, f14),
    ("15-arch-trust", "f15-arch-trust", 62, f15),
    ("16-closing", "f16-closing", 29, f16),
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
