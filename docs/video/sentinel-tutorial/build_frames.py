#!/usr/bin/env python3
"""장면 21개와 index.html 을 만든다.

**자막이 이 파일의 시계다.** 내레이션 원고는 STORYBOARD.md 한 곳에만 있고
여기서 읽어온다. 원고를 고치면 자막도 타이밍도 따라 바뀐다 — 두 곳에 적어두면
반드시 어긋나기 때문이다.

문단마다 머무는 시간은 글자 수로 정한다(초당 5.3자 + 호흡 0.8초). 그 합을
장면 길이에 맞춰 비례 조정한다. 요소는 문단이 바뀔 때마다 한 무리씩 도착한다.

모션 규칙은 frame.md 를 따른다 — 도착하고 머문다. 나갔다 들어오지 않고,
카메라도 없다. 설명서에 과시적인 동작은 필요 없다.
"""
import html
import math
import pathlib
import re
import textwrap

W, H = 1920, 1080
BAND = 220                 # 자막 띠 높이
CONTENT_H = H - BAND       # 860
PAD = 150                  # 좌우 안전 여백

BG, CARD, PANEL2 = "#eef3f0", "#ffffff", "#f5f8f6"
INK, MUTED, ACCENT = "#17221d", "#5c6b64", "#0e7c6b"
LINE, LINE2, ACC_SOFT = "#dfe7e3", "#c7d4ce", "#d9ece7"
WARN, CRIT = "#b8860b", "#b3261e"
DARK, NEON, NEON_DIM = "#0a0f0d", "#00ff41", "rgba(120,255,160,0.86)"

KR = "'IBM Plex Sans KR','Apple SD Gothic Neo','Malgun Gothic',system-ui,sans-serif"
MONO = "'JetBrains Mono','Fira Code',monospace"

_parts: list[str] = []
_anims: list[tuple[str, int]] = []   # (요소 id, 도착할 문단 번호)
_frame_id = ""
_cur_beat = 0

STATIC = -1     # 애니메이션 없이 처음부터 있는 것 (바탕, 장 제목)


def beat(n: int):
    """이 뒤에 선언하는 요소는 n 번째 자막 문단에서 도착한다."""
    global _cur_beat
    _cur_beat = n


def el(x, y, w, h, content="", *, size=26, weight=400, color=INK, bg=None,
       border=None, radius=0, align="left", lh=1.5, mono=False, extra="", at=None):
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
    eid = f"{_frame_id}-e{len(_parts)}"
    b = _cur_beat if at is None else at
    if b != STATIC:
        _anims.append((eid, b))
        s.append("will-change:transform,opacity")
    _parts.append(f'<div id="{eid}" style="{";".join(s)};">{content}</div>')


def box(x, y, w, h, *, bg=None, border=None, radius=12, extra=""):
    el(x, y, w, h, "", bg=bg, border=border or f"1px dashed {LINE2}",
       radius=radius, extra=extra)


def bg(color):
    """장면 바탕. 장이 바뀌는 자리는 컷이므로 바탕은 페이드하지 않는다."""
    el(0, 0, W, CONTENT_H, "", bg=color, at=STATIC)


def head(eyebrow, title, *, dark=False):
    el(PAD, 70, 1400, 40, eyebrow, size=30, weight=700,
       color=NEON if dark else ACCENT, at=STATIC)
    el(PAD, 112, 1500, 82, title, size=62, weight=700,
       color=NEON if dark else INK, at=STATIC)


def band(*_ignored):
    """스케치 패스의 잔재. 자막은 이제 STORYBOARD.md 에서 온다."""


# ─────────────────────────────────────────────────────────── 장면 정의

def f01():
    bg(BG)
    el(0, 0, 22, CONTENT_H, "", bg=ACCENT)
    el(PAD, 300, 1400, 50, "개인 컴퓨터를 혼자 관리하는 분을 위한", size=34, color=ACCENT)
    el(PAD, 362, 1560, 240, "내 컴퓨터 지킴이<br>사용 안내", size=104, weight=700, lh=1.14)
    beat(1)
    el(PAD, 636, 1400, 50, "보안을 몰라도 됩니다. 화면이 무엇을 해야 할지 알려줍니다.",
       size=32, color=MUTED)


def f02():
    bg(DARK)
    head("1장", "왜 필요한가", dark=True)
    logs = [
        "Feb  3 04:12:07 host sshd[2211]: Failed password for invalid user admin from 203.0.113.9 port 41022 ssh2",
        "Feb  3 04:12:09 host sshd[2213]: Failed password for invalid user test from 203.0.113.9 port 41031 ssh2",
        "Feb  3 04:12:11 host sshd[2215]: Invalid user oracle from 203.0.113.9 port 41044",
    ]
    for i, ln in enumerate(logs):
        el(PAD, 262 + i * 42, 1620, 34, html.escape(ln), size=21, mono=True,
           color=NEON if i == 1 else NEON_DIM)
    beat(1)
    el(PAD - 16, 296, 1652, 42, "", bg="rgba(0,255,65,0.14)", radius=6)
    beat(3)
    el(PAD, 440, 60, 50, "↓", size=44, color=NEON_DIM)
    beat(4)
    # 사람 말로 바뀐 카드
    el(PAD, 512, 1160, 200, "", bg=CARD, radius=16, border=f"1px solid {LINE}")
    box(PAD + 34, 546, 64, 64, radius=32)
    el(PAD + 126, 550, 940, 46, "처음 보는 곳에서 계정 이름을 찍어보고 있어요",
       size=34, weight=700)
    el(PAD + 126, 606, 940, 40, "모두 막혔어요. 따로 하실 일은 없어요.", size=26, color=MUTED)


def f03():
    bg(BG)
    head("2장", "화면 구성")
    beat(1)
    # 초보자 모드 덩이
    el(PAD, 250, 1060, 250, "", bg=PANEL2, radius=16, border=f"1px solid {LINE}")
    el(PAD + 28, 274, 500, 36, "초보자 모드 — 쉬운 화면", size=26, weight=700, color=ACCENT)
    beat(2)
    for i, name in enumerate(["홈", "할 일 상세", "기록", "자세히 보기"]):
        bx = PAD + 28 + i * 254
        el(bx, 322, 230, 150, "", bg=CARD, radius=12, border=f"1px dashed {LINE2}")
        el(bx, 386, 230, 34, name, size=26, align="center")
    beat(3)
    # 전문가 모드 덩이
    el(PAD, 560, 1060, 210, "", bg=DARK, radius=16)
    el(PAD + 28, 584, 600, 36, "전문가 모드 — 대시보드", size=26, weight=700, color=NEON)
    el(PAD + 28, 632, 1004, 112, "", border=f"1px dashed {NEON_DIM}", radius=12)
    el(PAD + 28, 674, 1004, 34, "예전 대시보드 그대로 · 패널 11개를 한 화면에",
       size=26, color=NEON_DIM, align="center")
    # 모드 전환기 확대 — 첫 문단이 이 이야기라 먼저 온다
    beat(0)
    el(1300, 250, 470, 40, "오른쪽 위에서 바꿉니다", size=28, weight=700)
    el(1300, 312, 440, 76, "", bg=PANEL2, radius=14, border=f"1px solid {LINE}")
    el(1310, 322, 210, 56, "쉬운 화면", size=26, align="center", bg=CARD,
       radius=10, border=f"1px solid {LINE}", extra="line-height:56px")
    el(1526, 322, 204, 56, "전문가 화면", size=26, align="center", color=MUTED,
       extra="line-height:56px")
    beat(1)
    el(1300, 424, 470, 200,
       "고른 화면은 기억됩니다.<br><br>자세히 보기는 여기 없습니다 —<br>그것도 초보자 화면이라<br>홈 본문 링크로 들어갑니다.",
       size=25, color=MUTED, lh=1.7)


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
    bg(BG)
    head("3장 · 시나리오 하나", "아무 일 없는 날")
    sx, sy, sw = 320, 250, 1280
    screen(sx, sy, sw, 570, "🛡 내 컴퓨터 지킴이", right="쉬운 화면 | 전문가 화면")
    beat(1)
    box(sx + 56, sy + 122, 96, 96, radius=48)
    el(sx + 186, sy + 128, 700, 70, "이상 없음", size=56, weight=700)
    el(sx + 186, sy + 204, 800, 40, "지금 손볼 일이 없어요. 이 창을 닫으셔도 돼요.",
       size=26, color=MUTED)
    beat(2)
    for i, (lab, val) in enumerate([("밖에서 들어올 수 있는 문", "1개"),
                                    ("밀린 보안 업데이트", "없음"),
                                    ("막은 접속 시도", "23번")]):
        bx = sx + 40 + i * 400
        el(bx, sy + 292, 380, 170, "", bg=CARD, radius=14, border=f"1px solid {LINE}")
        el(bx + 24, sy + 316, 332, 32, lab, size=21, color=MUTED)
        el(bx + 24, sy + 360, 332, 56, val, size=44, weight=700)
    beat(3)
    el(sx + 40, sy + 486, 1200, 56, "할 일 카드가 들어갈 자리 — 오늘은 비어 있습니다",
       size=24, color=MUTED, align="center", border=f"1px dashed {LINE2}",
       radius=12, extra="line-height:56px")


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
    bg(BG)
    head("3장 · 시나리오 둘", "손볼 일이 생겼다")
    steps(1, ["① 할 일 카드", "② 미리보기", "③ 결과"])
    sx, sy, sw = 320, 316, 1280
    screen(sx, sy, sw, 500, "←  돌아가기", right="쉬운 화면 | 전문가 화면")
    beat(1)
    el(sx + 40, sy + 96, 900, 48, "다른 사람이 고칠 수 있는 파일 3개", size=36, weight=700)
    beat(2)
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
    beat(3)
    el(sx + 40, sy + 396, 200, 60, "잠그기", size=26, color="#ffffff", bg=ACCENT,
       radius=30, align="center", extra="line-height:60px")
    el(sx + 260, sy + 396, 200, 60, "나중에", size=26, align="center",
       border=f"1px solid {LINE2}", radius=30, extra="line-height:60px")


def f06():
    bg(BG)
    head("3장 · 시나리오 셋", "지킴이가 대신 못 하는 일")
    sx, sy, sw = PAD, 250, 1060
    screen(sx, sy, sw, 570, "←  돌아가기")
    el(sx + 40, sy + 96, 700, 36, "지금 확인하세요", size=24, weight=700, color=CRIT)
    el(sx + 40, sy + 142, 900, 50, "처음 보는 곳에서 로그인에 성공했어요",
       size=36, weight=700)
    beat(1)
    for i, (k, v) in enumerate([("언제", "오늘 새벽 3시 12분"),
                                ("어디서", "해외 · 지금까지 접속한 적 없는 곳"),
                                ("어떻게", "미리 등록해 둔 열쇠로 들어왔어요")]):
        ry = sy + 214 + i * 46
        el(sx + 40, ry, 120, 34, k, size=22, color=MUTED)
        el(sx + 180, ry, 800, 34, v, size=23)
    beat(2)
    el(sx + 40, sy + 372, 900, 44, "이때 직접 접속하셨나요?", size=28, weight=700)
    for i, (lab, col) in enumerate([("네, 제가 했어요", LINE2), ("아니요, 제가 안 했어요", CRIT),
                                    ("잘 모르겠어요", LINE2)]):
        el(sx + 40 + i * 330, sy + 432, 300, 62, lab, size=24, align="center",
           color=CRIT if col == CRIT else INK, border=f"1px solid {col}",
           radius=31, extra="line-height:62px")
    beat(4)
    el(sx + 40, sy + 516, 980, 50, "👁  지킴이가 본 것  1건  —  열어보기", size=23,
       color=ACCENT, bg=ACC_SOFT, radius=10, extra="line-height:50px;padding-left:20px")
    # 세 갈래
    beat(3)
    el(1300, 250, 470, 44, "답에 따라 갈립니다", size=30, weight=700)
    for i, (q, r) in enumerate([("네, 제가 했어요", "확인 처리하고 닫습니다"),
                                ("아니요", "긴급으로 올리고 순서대로 안내"),
                                ("잘 모르겠어요", "열어둔 채 재촉하지 않습니다")]):
        ry = 322 + i * 150
        el(1300, ry, 470, 38, q, size=25, weight=700)
        el(1300, ry + 46, 470, 76, r, size=24, color=MUTED, lh=1.55)
    el(1300, 762, 470, 46, "복사하면 이름·주소는 가려집니다", size=23, color=ACCENT)


def f07():
    bg(BG)
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
        beat(1 + min(2, i // 4))
        col, row = i % 2, i // 2
        bx = PAD + col * 820
        by = 250 + row * 96
        el(bx, by, 780, 80, "", bg=CARD, radius=12, border=f"1px solid {LINE}")
        el(bx + 24, by + 14, 560, 36, name, size=26)
        el(bx + 24, by + 50, 700, 26, src, size=19, color=ACCENT)


def f08():
    bg(BG)
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
        beat(1 + min(2, i // 2))
        col, row = i % 2, i // 2
        bx = PAD + col * 820
        by = 250 + row * 130
        el(bx, by, 780, 112, "", bg=CARD, radius=12, border=f"1px solid {LINE}")
        el(bx + 24, by + 18, 700, 40, name, size=28, weight=700)
        el(bx + 24, by + 62, 720, 34, sub, size=22, color=MUTED)
    beat(4)
    el(PAD, 664, 1620, 60, "할 수 없는 일을 할 수 있다고 말하지 않는 것이, 이 도구의 첫 번째 원칙입니다.",
       size=30, weight=700, color=ACCENT, align="center", extra="line-height:60px")


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
    bg(BG)
    head("6장", "설치")
    xs = [150, 563, 976, 1389]
    station(xs[0], 290, 380, 210, "1", "빌드 머신",
            ["$ deploy/build-release.sh", "tar.gz + sha256", "dist 포함 · 비밀 제외"], dark=True)
    beat(1)
    station(xs[1], 290, 380, 210, "2", "install.sh",
            ["전용 계정 · capability", "systemd · sudoers",
             "fail2ban · auditd · Lynis"], accent=True)
    beat(2)
    station(xs[2], 290, 380, 210, "3", "harden.sh",
            ["dry-run 으로 목록 확인", "→ --apply 로 적용",
             "역할별 플래그"], accent=True)
    beat(3)
    station(xs[3], 290, 380, 210, "4", "Lynis 크론",
            ["하루 한 번", "새 경고·지수 하락만 알림", "제안은 백로그"])
    for i in range(3):
        el(xs[i] + 380, 372, 33, 46, "→", size=30, color=LINE2, align="center")
    el(150, 268, 380, 26, "scp", size=20, color=MUTED, align="center")
    beat(4)
    # 되돌아오는 고리 — 이 장의 요점
    el(xs[2] + 40, 540, xs[3] - xs[2] + 300, 3, "", bg=ACCENT)
    el(xs[2] + 40, 512, 40, 30, "↖", size=26, color=ACCENT)
    el(xs[2], 560, 780, 40,
       "결정(적용 · 수용 · 이미 해결)이 다시 프로파일과 플래그로 돌아간다",
       size=23, color=ACCENT)
    el(150, 650, 1620, 44, "설치는 한 번이지만, 강화는 한 바퀴를 도는 일이다",
       size=28, weight=700, align="center")


def f10():
    bg(DARK)
    head("7장", "설정", dark=True)
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
        beat(1 if not hot else 2 + [5, 6, 7].index(i) if i in (5, 6, 7) else 1)
        el(PAD + 30, 312 + i * 42, 1060, 34, html.escape(ln), size=22, mono=True,
           color=NEON if hot else NEON_DIM)
    beat(2)
    el(1340, 240, 430, 44, "서버마다 채우는 셋", size=30, weight=700, color=NEON)
    for i, (n, d) in enumerate([("Slack 웹훅", "알림 제목에 호스트 이름이 붙습니다"),
                                ("서버 역할 메모", "AI 에게 물을 때 맥락으로 나갑니다"),
                                ("ignoreip", "자기 자신을 차단하지 않게")]):
        beat(2 + i)
        ry = 312 + i * 150
        el(1340, ry, 430, 38, f"{i+1}. {n}", size=26, weight=700, color=NEON)
        el(1340, ry + 46, 430, 80, d, size=23, color=NEON_DIM, lh=1.55)
    beat(5)
    el(PAD, 828, 1620, 0, "🔒  호스트 로그는 어떤 경우에도 밖으로 나가지 않습니다",
       size=26, color=NEON)


def f11():
    bg(BG)
    head("8장 · 아키텍처 ①", "어디서 들어오나")
    el(150, 236, 900, 30, "호스트 진실 원천 — root 소유 데몬·로그·/proc",
       size=21, color=MUTED)
    beat(1)
    srcs = [("auth.log · audit.log", "rsyslog · auditd"), ("dpkg.log · apt", "패키지 변경"),
            ("/proc", "소켓 · 프로세스 · fd"), ("/etc · cron · systemd", "설정 · 영속화 · SUID"),
            ("fail2ban", "차단의 진실 원천"), ("USN · 뉴스 RSS", "공개 URL 읽기만")]
    for i, (n, d) in enumerate(srcs):
        beat(1 if i < 5 else 2)
        bx, ext = 150 + i * 274, i == 5
        el(bx, 268, 250, 114, "", bg="#f6e7cf" if ext else CARD, radius=10,
           border=f"1px dashed #b8731c" if ext else f"1px solid {LINE}")
        el(bx + 14, 282, 222, 58, n, size=21, weight=700, lh=1.32,
           color="#b8731c" if ext else INK)
        el(bx + 14, 342, 222, 30, d, size=18, color=MUTED)
        el(bx + 105, 388, 40, 34, "↓", size=24, color="#b8731c" if ext else MUTED)
    beat(3)
    # 백엔드 경계
    el(120, 428, 1680, 232, "", border=f"1px dashed {ACCENT}", radius=14)
    el(140, 438, 1000, 28, "secdash.service · User=secdash · 127.0.0.1:8000", size=19, color=ACCENT)
    mons = [("AuthLog · Audit", "실패 창 · 실패 후 성공"), ("UpdateMonitor", "설치/제거 · 미적용"),
            ("Network · Process", "새 리스너 · 리버스 셸"), ("Integrity · Persistence", "기준선 diff"),
            ("Fail2banSync", "30초 동기화"), ("IntelMonitor", "USN ↔ 설치 버전")]
    for i, (n, d) in enumerate(mons):
        bx = 150 + i * 274
        el(bx, 474, 250, 100, "", bg=CARD, radius=10, border=f"1.5px solid {ACCENT}")
        el(bx + 14, 486, 222, 54, n, size=20, weight=700, lh=1.32)
        el(bx + 14, 542, 222, 28, d, size=18, color=MUTED)
        el(bx + 105, 578, 40, 30, "↓", size=22, color=MUTED)
    beat(4)
    el(190, 616, 1540, 5, "", bg=ACCENT)
    el(150, 676, 760, 40, "사실은 이벤트로", size=26, weight=700, color=ACCENT)
    el(150, 716, 760, 34, "일어난 일. 심각도 없음. 근거로 남는다.", size=21, color=MUTED)
    el(1010, 676, 760, 40, "판단은 알림으로", size=26, weight=700, color=ACCENT)
    el(1010, 716, 760, 34, "묶어서 내린 결론. 사람의 시간을 요구한다.", size=21, color=MUTED)


def f12():
    bg(BG)
    head("8장 · 아키텍처 ②", "어디에 쌓이고 어디로 나가나")
    el(190, 232, 1540, 5, "", bg=ACCENT)
    el(150, 244, 900, 28, "앞 장의 이벤트 버스", size=19, color=ACCENT)
    beat(0)
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
    beat(1)
    # 판단
    el(870, 288, 330, 136, "", bg=ACC_SOFT, radius=12, border=f"1.5px solid {ACCENT}")
    el(890, 308, 290, 36, "알림 엔진", size=25, weight=700, color=ACCENT)
    el(890, 350, 290, 60, "같은 지문 → 횟수 +1<br>심각도 상승 → 재오픈", size=20, color=MUTED, lh=1.5)
    beat(2)
    el(870, 444, 330, 136, "", bg=ACC_SOFT, radius=12, border=f"1.5px solid {ACCENT}")
    el(890, 464, 290, 36, "DefconWatcher", size=25, weight=700, color=ACCENT)
    el(890, 506, 290, 60, "10초마다<br>열린 알림만 센다", size=20, color=MUTED, lh=1.5)
    beat(3)
    el(1240, 288, 300, 292, "", bg=ACC_SOFT, radius=12, border=f"1.5px solid {ACCENT}")
    el(1260, 308, 260, 36, "알림 큐", size=25, weight=700, color=ACCENT)
    el(1260, 350, 260, 120, "워커 스레드 1개<br>분당 10건<br>초과분은 묶어서<br>모니터를 막지 않음",
       size=20, color=MUTED, lh=1.6)
    el(1580, 288, 190, 136, "", bg=PANEL2, radius=12, border=f"1px solid {LINE}")
    el(1600, 308, 150, 36, "파일 로그", size=23, weight=700)
    el(1600, 350, 150, 56, "security.log<br>critical.log", size=19, color=MUTED, mono=True, lh=1.5)
    beat(4)
    # API · 외부 · 브라우저
    el(150, 612, 1050, 92, "", bg=ACC_SOFT, radius=12, border=f"1.5px solid {ACCENT}")
    el(172, 630, 1000, 34, "FastAPI · 127.0.0.1:8000", size=25, weight=700, color=ACCENT)
    el(172, 666, 1000, 30, "모든 /api 요청에 X-API-Token · 원격은 SSH 터널", size=20, color=MUTED)
    for bx, n, d in [(1240, "번역 API", "뉴스 제목만"), (1520, "Slack", "웹훅 POST")]:
        el(bx, 612, 250, 92, "", bg="#f6e7cf", radius=12, border="1px dashed #b8731c")
        el(bx + 20, 630, 210, 34, n, size=23, weight=700, color="#b8731c")
        el(bx + 20, 666, 210, 30, d, size=19, color=MUTED)
    beat(5)
    el(150, 726, 1050, 80, "", bg=CARD, radius=12, border=f"1px solid {LINE}")
    el(172, 744, 1000, 34, "브라우저 · React 대시보드", size=24, weight=700)
    el(172, 778, 1000, 28, "5초 폴링 · 토큰 헤더", size=19, color=MUTED)
    el(1240, 730, 530, 76, "나가는 것은 셋뿐 —<br>공개 피드 · 뉴스 제목 · Slack 웹훅",
       size=22, color="#b8731c", weight=700, lh=1.5)


def f13():
    bg(BG)
    head("8장 · 아키텍처 ③", "사건 하나가 지나가는 길")
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
            beat((1 if i < 2 else 2 if i == 2 else 3) if r == 0 else (4 if i < 2 else 5))
            bx = 150 + i * 330
            el(bx, by, 300, 150, "", bg=CARD, radius=12,
               border=f"1.5px solid {tone}" if tone else f"1px solid {LINE}")
            el(bx + 18, by + 22, 264, 66, n, size=24, weight=700, color=tone or INK, lh=1.3)
            el(bx + 18, by + 94, 264, 56, d, size=20, color=MUTED, lh=1.4)
            if i < 4:
                el(bx + 300, by + 56, 30, 40, "→", size=26,
                   color=CRIT if r else LINE2, align="center")
    beat(4)
    el(1140, 412, 400, 92, "같은 IP 의 실패 창을 유지한다", size=21, color=MUTED)
    el(1145, 412, 3, 90, "", bg=LINE2)
    beat(6)
    el(150, 728, 1620, 44,
       "시뮬레이션 사건은 같은 길을 가되 표시가 붙어 위험 단계·Slack·fail2ban 에 닿지 않는다",
       size=23, color=MUTED, align="center")


def f14():
    bg(BG)
    head("8장 · 아키텍처 ④", "알림의 생애주기와 위험 단계")
    pills = [("열림", "아직 아무도 안 봄<br>위험 단계에 반영", CRIT, CARD),
             ("확인함", "사람이 '봤다' 표시<br>단계에서 빠짐", ACCENT, ACC_SOFT),
             ("해결됨", "끝난 것<br>90일 뒤 삭제", LINE2, PANEL2)]
    for i, (n, d, col, fill) in enumerate(pills):
        beat(1 + i)
        bx = 260 + i * 510
        el(bx, 380, 380, 130, "", bg=fill, radius=65, border=f"2px solid {col}")
        el(bx, 404, 380, 44, n, size=32, weight=700, color=col if col != LINE2 else INK, align="center")
        el(bx, 450, 380, 52, d, size=20, color=MUTED, align="center", lh=1.4)
    beat(4)
    for i, lab in enumerate(["확인(ack)", "해결(resolve)"]):
        el(640 + i * 510, 396, 130, 34, "→", size=30, color=LINE2, align="center")
        el(618 + i * 510, 434, 174, 30, lab, size=20, color=MUTED, align="center")
    el(618, 470, 174, 30, "← 심각도 상승", size=20, color=CRIT, align="center")
    el(450, 596, 1020, 3, "", bg=LINE2)
    el(450, 610, 1020, 40, "원인이 사라지면 시스템이 스스로 해결로 넘긴다 (자동 해결)",
       size=22, color=MUTED, align="center")
    beat(5)
    el(260, 300, 380, 60, "같은 지문 재발 → 횟수 +1", size=21, color=MUTED, align="center")
    el(770, 300, 380, 60, "점검 모드 중 계획된 변경은<br>처음부터 '확인함'", size=21,
       color=ACCENT, align="center", lh=1.4)
    beat(6)
    el(150, 700, 1620, 44,
       "DEFCON 1 = 열린 긴급 있음   ·   DEFCON 3 = 열린 경고 있음   ·   SAFE = 열린 것 없음",
       size=25, weight=700, align="center")
    el(150, 754, 1620, 40, "침입 신호는 점검 모드와 무관하게 언제나 '열림'",
       size=22, color=CRIT, align="center")


def f15():
    bg(BG)
    head("8장 · 아키텍처 ⑤", "권한의 경계, 그리고 왜 이 구조인가")
    el(150, 246, 980, 32, "지킴이는 root 로 돌지 않는다", size=24, weight=700)
    for i, h_ in enumerate(["경계", "넘는 것", "허용 방법"]):
        el(150 + [0, 330, 700][i], 292, [320, 360, 280][i], 30, h_, size=19, color=MUTED)
    beat(1)
    rows = [("root 데몬 → secdash", "auth.log 읽기", "adm 그룹"),
            ("보호 파일 → secdash", "shadow · sudoers · authorized_keys", "CAP_DAC_READ_SEARCH"),
            ("타 사용자 프로세스", "실행 파일 · 소켓 귀속", "CAP_SYS_PTRACE"),
            ("secdash → fail2ban", "차단 · 해제 · 조회", "sudo 일곱 명령만"),
            ("브라우저 → API", "조회 · 확인 · 차단 요청", "X-API-Token · 127.0.0.1"),
            ("호스트 → 인터넷", "공개 피드 · 제목 · 웹훅", "아웃바운드 HTTPS")]
    for i, (a, b, c) in enumerate(rows):
        beat(1 if i < 3 else 2)
        ry = 336 + i * 74
        el(150, ry, 980, 1, "", bg=LINE)
        el(150, ry + 16, 320, 40, a, size=22)
        el(480, ry + 16, 360, 40, b, size=21, color=MUTED)
        el(850, ry + 16, 280, 40, c, size=20, color=ACCENT, mono=True)
    beat(2)
    el(150, 780, 980, 34, "쓰기 권한은 어디에도 없다", size=22, color=CRIT)
    beat(3)
    el(1200, 246, 570, 32, "왜 이 구조인가", size=24, weight=700, color=ACCENT)
    for i, (n, d) in enumerate([
            ("진실 원천은 하나씩", "해석만 한다. 두 번째 사실을 만들지 않는다."),
            ("조용히 실패하지 않는다", "읽지 못하는 파일은 '정상'이 아니라 '제한'."),
            ("사실과 판단을 나눈다", "사람의 시간을 요구하는 것은 알림뿐."),
            ("호스트 로그는 안에 머문다", "한국어는 서버 안에서 템플릿으로 만든다.")]):
        beat(4 + i // 2)
        ry = 300 + i * 128
        el(1200, ry, 570, 40, f"{i+1}.  {n}", size=25, weight=700)
        el(1236, ry + 46, 534, 64, d, size=21, color=MUTED, lh=1.5)


def f16():
    bg(ACCENT)
    el(PAD, 180, 1400, 100, "기억할 것은 셋", size=78, weight=700, color="#ffffff")
    beat(1)
    for i, (n, d) in enumerate([
            ("할 일이 없으면 아무 말도 하지 않습니다", "대부분의 날이 그렇습니다."),
            ("고치기 전에 무엇이 바뀌는지 먼저 보여줍니다", "보고 나서 정하시면 됩니다."),
            ("모르는 것은 모른다고 말합니다", "사용자만 아는 것은 사용자에게 묻습니다.")]):
        by = 350 + i * 150
        el(PAD, by, 64, 64, str(i + 1), size=30, weight=700, color=ACCENT, bg="#ffffff",
           radius=32, align="center", extra="line-height:64px")
        el(PAD + 96, by + 2, 1400, 46, n, size=36, weight=700, color="#ffffff")
        el(PAD + 96, by + 56, 1400, 40, d, size=26, color="rgba(255,255,255,0.8)")


def feat_exposure():
    bg(BG)
    head("5장 · 기능 ①", "문이 실제로 밖에서 닿는가")
    el(150, 236, 1620, 50, "열려 있다  ≠  밖에서 닿는다", size=32, weight=700, color=ACCENT)
    states = [("루프백 전용", "이 컴퓨터 안에서만", LINE, PANEL2),
              ("의도된 공개", "직접 열어두신 것", LINE, PANEL2),
              ("잠시 쓰는 통로", "프로그램이 나가면서", LINE, PANEL2),
              ("외부 도달 가능", "경고 — 밖에서 닿는다", WARN, CARD),
              ("방화벽이 막는 중", "바인딩은 전체지만 막힘", LINE, PANEL2),
              ("판단 불가", "방화벽 상태를 못 읽음", CRIT, CARD)]
    for i, (n, d, col, fill) in enumerate(states):
        beat(3 if i < 5 else 4)
        bx, by = 150 + (i % 3) * 550, 314 + (i // 3) * 180
        el(bx, by, 520, 150, "", bg=fill, radius=14,
           border=f"{'2px' if col != LINE else '1px'} solid {col}")
        el(bx + 26, by + 26, 468, 46, n, size=32, weight=700,
           color=col if col != LINE else INK)
        el(bx + 26, by + 82, 468, 40, d, size=23, color=MUTED)
    beat(5)
    el(150, 700, 1620, 44, "모르는 것을 '안전'이라고 말하지 않는다 — 그게 가장 위험하다",
       size=28, weight=700, color=CRIT, align="center")
    el(150, 756, 1620, 40, "다른 계정의 프로세스를 못 볼 때도 모니터가 스스로 '제한됨'이라고 표시한다",
       size=22, color=MUTED, align="center")


def feat_integrity():
    bg(BG)
    head("5장 · 기능 ②", "건드리면 안 되는 파일이 바뀌었을 때")
    beat(1)
    el(150, 236, 900, 34, "기준선을 저장해두고 비교하는 곳", size=23, color=MUTED)
    for i, pth in enumerate(["/etc/sudoers", "authorized_keys", "/etc/cron.d",
                             "systemd 유닛", "ld.so.preload"]):
        el(150 + i * 190, 280, 178, 48, pth, size=17, mono=True, align="center",
           bg=CARD, radius=10, border=f"1px solid {LINE}", extra="line-height:48px")
    beat(2)
    el(150, 348, 900, 34, "설정 파일 60초 · 자동 실행 지점 5분", size=21, color=MUTED)
    beat(3)
    # 차이 카드
    el(150, 392, 900, 264, "", bg=CARD, radius=14, border=f"1px solid {LINE}")
    el(174, 414, 850, 36, "무엇이 바뀌었나", size=25, weight=700)
    for i, (mark, ln, col) in enumerate([(" ", "%admin ALL=(ALL) ALL", MUTED),
                                         (" ", "%sudo  ALL=(ALL:ALL) ALL", MUTED),
                                         ("+", "deploy ALL=(ALL) NOPASSWD: ALL", CRIT),
                                         (" ", "#includedir /etc/sudoers.d", MUTED)]):
        el(174, 462 + i * 40, 40, 32, mark, size=21, mono=True, weight=700, color=col)
        el(222, 462 + i * 40, 790, 32, html.escape(ln), size=21, mono=True, color=col)
    el(174, 620, 850, 30, "SHA-256 기준선과의 차이를 그대로 붙인다", size=20, color=MUTED)
    beat(4)
    # auditd
    el(1100, 392, 670, 116, "", bg=ACC_SOFT, radius=14, border=f"1.5px solid {ACCENT}")
    el(1126, 412, 620, 36, "auditd 가 한 줄을 더 붙인다", size=25, weight=700, color=ACCENT)
    el(1126, 454, 620, 34, "누가 · 어떤 프로그램으로 그 파일에 썼나", size=22, color=MUTED)
    beat(5)
    # 계획 변경 필터
    el(1100, 528, 670, 114, "", bg=CARD, radius=14, border=f"1px solid {LINE}")
    el(1126, 548, 620, 36, "정상적인 변경은 거른다", size=25, weight=700)
    el(1126, 590, 620, 34, "소유 패키지 + 최근 패키지 작업 대조 → 사실로만", size=21, color=MUTED)
    beat(6)
    el(1100, 664, 670, 40, "예외 — 무슨 일이 있어도 알린다", size=23, weight=700, color=CRIT)
    el(1100, 708, 670, 40, "sudoers · sshd_config · authorized_keys · ld.so.preload",
       size=20, mono=True, color=CRIT)


def feat_fix():
    bg(BG)
    head("5장 · 기능 ③", "지킴이가 직접 잠그는 유일한 곳")
    el(150, 236, 1620, 40, "스스로 시스템을 바꾸는 곳은 여기 하나뿐이다. 그래서 방어가 네 겹이다.",
       size=26, color=MUTED)
    guards = [("경로를 인자로 받지 않는다",
               "무엇을 고칠지는 root 진입점이 스스로 다시 검사해 정한다",
               "secdash-fix-permissions --apply"),
              ("좁히기만 한다",
               "교집합은 언제나 기존의 부분집합 — 넓어지는 경우가 없다",
               "new = old & target"),
              ("심볼릭 링크를 따라가지 않는다",
               "검사와 적용 사이에 링크로 바뀌어도 가리키는 파일은 안 건드린다",
               "os.open(O_NOFOLLOW) → fchmod"),
              ("실행 체인이 전부 root 소유일 때만",
               "디렉터리 · 진입점 · 스캐너 · 인터프리터 중 하나라도 아니면 거부",
               "stat -c %u == 0")]
    for i, (n, d, code) in enumerate(guards):
        beat(1 + i)
        bx, by = 150 + (i % 2) * 830, 300 + (i // 2) * 220
        el(bx, by, 790, 190, "", bg=CARD, radius=14, border=f"1px solid {LINE}")
        el(bx + 26, by + 22, 60, 40, f"{i+1}", size=30, weight=700, color=ACCENT)
        el(bx + 86, by + 22, 680, 44, n, size=29, weight=700)
        el(bx + 86, by + 74, 680, 60, d, size=21, color=MUTED, lh=1.45)
        el(bx + 86, by + 140, 680, 34, code, size=20, mono=True, color=ACCENT)
    beat(5)
    el(150, 756, 1620, 44,
       "조치 기능 자체가 공격면이 되지 않게 — 이건 직접 겪고 고친 것이다",
       size=27, weight=700, color=CRIT, align="center")


def feat_intel():
    bg(BG)
    head("5장 · 기능 ④", "내 서버에 해당하는 취약점만")
    el(150, 240, 1620, 40, "보안 공지는 하루에도 여러 건. 대부분은 내 서버와 상관이 없다.",
       size=26, color=MUTED)
    beat(2)
    el(150, 310, 460, 200, "", bg="#f6e7cf", radius=14, border="1px dashed #b8731c")
    el(176, 336, 408, 40, "우분투 보안 공지", size=28, weight=700, color="#b8731c")
    el(176, 386, 408, 100, "한 시간에 한 번 받아온다<br><br>영향 패키지 · 고쳐진 버전",
       size=22, color=MUTED, lh=1.5)
    beat(3)
    el(630, 386, 60, 46, "→", size=32, color=LINE2, align="center")
    el(710, 310, 460, 200, "", bg=ACC_SOFT, radius=14, border=f"1.5px solid {ACCENT}")
    el(736, 336, 408, 40, "설치된 버전과 대조", size=28, weight=700, color=ACCENT)
    el(736, 386, 408, 100, "dpkg 가 서버 안에서 비교<br><br>version_lt(설치, 고쳐진)",
       size=22, color=MUTED, lh=1.5, mono=False)
    el(1190, 386, 60, 46, "→", size=32, color=LINE2, align="center")
    for i, (n, d, on) in enumerate([("설치 안 됨", "넘어감", False),
                                    ("이미 고쳐진 버전", "넘어감", False),
                                    ("낮은 버전", "이 서버에 해당 — 알린다", True)]):
        by = 310 + i * 70
        el(1270, by, 500, 58, "", bg=CARD if on else PANEL2, radius=10,
           border=f"2px solid {CRIT}" if on else f"1px solid {LINE}")
        el(1294, by + 12, 240, 34, n, size=23, weight=700, color=CRIT if on else MUTED)
        el(1534, by + 12, 220, 34, d, size=20, color=CRIT if on else MUTED, align="right")
    beat(4)
    el(150, 600, 1620, 44,
       "대조는 서버 안에서 dpkg 가 한다. 설치된 패키지 목록은 밖으로 나가지 않는다.",
       size=27, weight=700, align="center")
    beat(5)
    el(150, 660, 1620, 40,
       "뉴스 제목을 한국어로 옮길 때도, 나가는 것은 공개된 제목뿐이다.",
       size=23, color=MUTED, align="center")


def feat_maint():
    bg(BG)
    head("5장 · 기능 ⑤", "작업할 때는 점검 모드")
    el(150, 236, 1620, 40, "감시 기능이 아니라, 감시가 죽지 않게 하는 장치다.",
       size=26, color=MUTED)
    beat(1)
    for i, (n, d) in enumerate([("파일이 바뀌었어요", "설정 파일 3건"),
                                ("새 포트가 열렸어요", "서비스를 띄웠을 때"),
                                ("패키지가 바뀌었어요", "설치·업그레이드"),
                                ("자동 실행 지점이 늘었어요", "유닛·cron")]):
        el(150, 300 + i * 62, 620, 52, "", bg=CARD, radius=10, border=f"1px solid {LINE}")
        el(172, 312 + i * 62, 400, 30, n, size=22)
        el(560, 312 + i * 62, 190, 30, d, size=18, color=MUTED, align="right")
    el(150, 552, 620, 40, "전부 지킴이가 잡아야 할 일이다 — 다만 지금은 내가 하는 일이다",
       size=21, color=MUTED)
    beat(2)
    el(150, 606, 620, 44, "반복되면 사람은 알림을 무시하게 된다", size=26, weight=700, color=CRIT)
    el(150, 652, 620, 40, "그러면 진짜가 왔을 때도 무시한다", size=22, color=CRIT)
    beat(3)
    el(830, 236, 940, 40, "그래서 작업 전에 창을 선언한다", size=26, weight=700, color=ACCENT)
    el(830, 288, 420, 210, "", bg=CARD, radius=16, border=f"2px solid {ACCENT}")
    el(178, 328, 464, 40, "점검 모드 선언", size=30, weight=700, color=ACCENT)
    el(178, 386, 464, 40, "45분", size=44, weight=700)
    el(178, 448, 464, 76, "메모: 커널 업데이트와 재부팅<br>선언: kunmyon", size=22,
       color=MUTED, lh=1.6)
    el(700, 400, 70, 46, "→", size=32, color=LINE2, align="center")
    beat(4)
    el(800, 300, 970, 110, "", bg=ACC_SOFT, radius=14, border=f"1.5px solid {ACCENT}")
    el(826, 318, 918, 38, "계획된 변경 → 처음부터 '확인함'", size=27, weight=700, color=ACCENT)
    el(826, 358, 918, 34, "파일 변경 · 자동 실행 지점 · 새 포트 · 패키지 · Lynis · 리소스",
       size=20, color=MUTED)
    el(800, 430, 970, 40, "Slack 안 감 · 위험 단계 안 올라감 · 근거는 그대로 남음",
       size=23, color=MUTED)
    beat(5)
    el(800, 500, 970, 110, "", bg=CARD, radius=14, border=f"2px solid {CRIT}")
    el(826, 518, 918, 38, "침입 신호 → 언제나 '열림'", size=27, weight=700, color=CRIT)
    el(826, 558, 918, 34, "브루트포스 · 실패 후 로그인 성공 · 리버스 셸 · 계정 변경",
       size=20, color=MUTED)
    el(800, 630, 970, 40, "점검 모드와 무관하다", size=23, color=CRIT)
    beat(5)
    el(150, 700, 1620, 44, "근거는 남는다. 조용해지는 것은 알림뿐이다.",
       size=28, weight=700, align="center")
    el(150, 756, 1620, 40,
       "알림 피로로 사람이 알림을 무시하게 되면, 진짜가 왔을 때도 무시한다",
       size=22, color=MUTED, align="center")


FRAMES = [
    ("01-title", "f01-title", 17, f01),
    ("02-why", "f02-why", 49, f02),
    ("03-map", "f03-map", 47, f03),
    ("04-scenario-calm", "f04-calm", 34, f04),
    ("05-scenario-fix", "f05-fix", 59, f05),
    ("06-scenario-judge", "f06-judge", 61, f06),
    ("07-can", "f07-can", 50, f07),
    ("08-cannot", "f08-cannot", 52, f08),
    ("09-feat-exposure", "f09-exposure", 60, feat_exposure),
    ("10-feat-integrity", "f10-integrity", 64, feat_integrity),
    ("11-feat-fix", "f11-fix", 68, feat_fix),
    ("12-feat-intel", "f12-intel", 56, feat_intel),
    ("13-feat-maintenance", "f13-maint", 58, feat_maint),
    ("14-install", "f14-install", 62, f09),
    ("15-config", "f15-config", 65, f10),
    ("16-arch-sources", "f16-arch-src", 66, f11),
    ("17-arch-core", "f17-arch-core", 72, f12),
    ("18-arch-path", "f18-arch-path", 68, f13),
    ("19-arch-alert", "f19-arch-alert", 58, f14),
    ("20-arch-trust", "f20-arch-trust", 62, f15),
    ("21-closing", "f21-closing", 29, f16),
]

# ─────────────────────────────────────────────────────── 자막 (STORYBOARD.md 가 원본)

CPS = 5.3          # 한국어 자막을 읽는 속도 (초당 글자)
BREATH = 0.8       # 문단 사이 호흡
LEAD, TAIL = 0.3, 0.4


def read_storyboard() -> dict:
    """장면별 (길이, 자막 문단 목록). 원고는 여기에만 있다."""
    src = (pathlib.Path(__file__).parent / "STORYBOARD.md").read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r"## Frame \d+ — .+?\n(.*?)(?=\n## Frame |\Z)", src, re.S):
        b = m.group(1)
        name = re.search(r"- src: .*?/([\w-]+)\.html", b).group(1)
        dur = int(re.search(r"- duration: (\d+)s", b).group(1))
        vo = re.search(r"- voiceover: \|\n((?:    .*\n|\n)*)", b)
        paras = [" ".join(x.split())
                 for x in re.split(r"\n\s*\n", textwrap.dedent(vo.group(1)).strip()) if x.strip()]
        out[name] = (dur, paras)
    return out


def subtitle_schedule(paras: list[str], duration: float) -> list[tuple[float, float]]:
    """문단마다 (시작, 끝). 글자 수로 비례 배분하고 장면 길이에 맞춘다."""
    want = [len(p.replace(" ", "")) / CPS + BREATH for p in paras]
    span = duration - LEAD - TAIL
    k = span / sum(want)
    out, t0 = [], LEAD
    for w in want:
        out.append((round(t0, 3), round(t0 + w * k, 3)))
        t0 += w * k
    return out


def subtitle_markup(fid: str, paras: list[str]) -> str:
    """문단을 겹쳐 놓고 투명도로 갈아 끼운다. 자리는 절대 움직이지 않는다."""
    parts = []
    for i, text in enumerate(paras):
        units = sum(1.0 if ord(c) > 0x2000 else 0.55 for c in text)
        lines = max(1, math.ceil(units / 40))
        h = math.ceil(lines * 34 * 1.5)
        top = CONTENT_H + (BAND - h) // 2
        parts.append(
            f'<div id="{fid}-sub{i}" style="position:absolute;left:{PAD}px;top:{top}px;'
            f'width:{W - PAD * 2}px;height:{h}px;font-family:{KR};font-size:34px;'
            f'color:#ffffff;line-height:1.5;word-break:keep-all;opacity:0;'
            f'will-change:opacity;">{html.escape(text)}</div>')
    return "\n".join("          " + x for x in parts)


# ─────────────────────────────────────────────────────── 출력

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
                  background: {bgc}; }}
        #{cid} * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        #{cid} .clip {{ position: absolute; inset: 0; }}
      </style>
      <div id="{cid}" data-composition-id="{cid}" data-start="0"
           data-width="{w}" data-height="{h}" data-duration="{dur}">
        <div id="{cid}-clip" class="clip" data-start="0" data-duration="{dur}">
{body}
          <div style="position:absolute;left:0px;top:{band_y}px;width:{w}px;height:{band_h}px;background:{ink};"></div>
{subs}
        </div>
      </div>
      <script>
        // 하나의 일시정지 타임라인. 되감아도 같은 그림이 나오도록 절대값만 쓴다.
        (function () {{
          const tl = gsap.timeline({{ paused: true }});
{tweens}
          window.__timelines["{cid}"] = tl;
        }})();
      </script>
    </template>
  </body>
</html>
"""

INDEX = """<!doctype html>
<html lang="ko">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <title>내 컴퓨터 지킴이 · 사용 안내</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: 1920px; height: 1080px; overflow: hidden; background: #17221d; }}
      /* 장면 슬롯은 화면을 가득 채운다. */
      [data-composition-id="root"] > div[data-composition-src] {{ position: absolute; inset: 0; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="root" data-start="0"
         data-width="1920" data-height="1080" data-duration="{total}">
{slots}
    </div>
    <script>
      // 조립만 한다. 장면 안의 움직임은 각 하위 컴포지션이 가진다.
      window.__timelines["root"] = gsap.timeline({{ paused: true }});
    </script>
  </body>
</html>
"""


def emit_frame(name, cid, fn, dur, paras, bgc):
    _parts.clear(); _anims.clear()
    globals()["_frame_id"] = cid
    beat(0)
    fn()
    sched = subtitle_schedule(paras, dur)
    tw = []
    for i, (t0, t1) in enumerate(sched):
        tw.append(f'          tl.fromTo("#{cid}-sub{i}", {{ opacity: 0 }}, '
                  f'{{ opacity: 1, duration: 0.25, ease: "none" }}, {t0});')
        if i < len(sched) - 1:
            tw.append(f'          tl.to("#{cid}-sub{i}", '
                      f'{{ opacity: 0, duration: 0.25, ease: "none" }}, {round(t1 - 0.25, 3)});')
    # 요소는 자기 문단이 시작할 때 무리로 도착한다 (한 무리 전체가 0.5초 안에)
    per = {}
    for eid, b in _anims:
        per.setdefault(min(b, len(sched) - 1), []).append(eid)
    for b, ids in sorted(per.items()):
        t0 = sched[b][0]
        step = min(0.08, 0.5 / max(1, len(ids)))
        for j, eid in enumerate(ids):
            tw.append(f'          tl.fromTo("#{eid}", {{ opacity: 0, y: 16 }}, '
                      f'{{ opacity: 1, y: 0, duration: 0.45, ease: "power2.out" }}, '
                      f'{round(t0 + j * step, 3)});')
    body = "\n".join("          " + x for x in _parts)
    return TPL.format(title=name, cid=cid, w=W, h=H, dur=dur, bgc=bgc, body=body,
                      band_y=CONTENT_H, band_h=BAND, ink=INK,
                      subs=subtitle_markup(cid, paras), tweens="\n".join(tw))


def main():
    root = pathlib.Path(__file__).parent
    out = root / "compositions" / "frames"
    out.mkdir(parents=True, exist_ok=True)
    board = read_storyboard()
    slots, t0 = [], 0.0
    for name, cid, _sketch_dur, fn in FRAMES:
        dur, paras = board[name]
        bgc = DARK if name in DARK_FRAMES else (ACCENT if name == "21-closing" else BG)
        (out / f"{name}.html").write_text(emit_frame(name, cid, fn, dur, paras, bgc),
                                          encoding="utf-8")
        slots.append(
            f'      <div id="el-{cid}" data-composition-id="{cid}"\n'
            f'           data-composition-src="compositions/frames/{name}.html"\n'
            f'           data-start="{round(t0, 3)}" data-duration="{dur}"\n'
            f'           data-track-index="1" data-width="{W}" data-height="{H}"></div>')
        print(f"  {name:<22} {dur:>2}s  요소 {len(_parts):>2}  문단 {len(paras)}")
        t0 += dur
    (root / "index.html").write_text(
        INDEX.format(total=round(t0, 3), slots="\n\n".join(slots)), encoding="utf-8")
    print(f"\n  index.html — 장면 {len(FRAMES)}개 · {int(t0)}s = {int(t0)//60}분 {int(t0)%60}초")


DARK_FRAMES = {"02-why", "14-install", "15-config"}

if __name__ == "__main__":
    main()
