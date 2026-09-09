#!/usr/bin/env python3
"""
튜토리얼 덱 생성기 (Genitor 슬라이드 HTML).

좌표를 손으로 누적하면 반드시 어긋난다. 화면 목업이 많은 덱이라 요소마다 위치를 계산해 뽑는다.
색·글꼴은 제품(비전문가용 화면)이 쓰는 것을 그대로 가져와, 덱을 보는 사람이 화면과 같은 세계로 느끼게 한다.

    python3 build_tutorial_deck.py > tutorial-deck.html
"""
import html
import math

W, H = 1920, 1080

# 제품 팔레트 (frontend/src/index.css 의 calm-* 토큰)
BG      = "#eef3f0"
INK     = "#17221d"
MUTED   = "#5d6c65"
LINE    = "#d7e0db"
LINE2   = "#b9c6bf"
PANEL   = "#ffffff"
PANEL2  = "#e6ede9"
ACCENT  = "#0e7c6b"
ACC_SOFT= "#d5ece6"
WARN    = "#b98a12"
WARN_SOFT="#f7ecd0"
CRIT    = "#b5322a"
CRIT_SOFT="#f4ddda"
DARK    = "#12211c"

F = "'IBM Plex Sans KR',sans-serif"

_parts: list[str] = []


def _anim(kw) -> str:
    m = {"anim": "data-anim", "dir": "data-anim-dir", "dur": "data-anim-duration",
         "delay": "data-anim-delay", "trig": "data-anim-trigger",
         "name": "data-anim-name", "ref": "data-anim-ref"}
    return "".join(f' {m[k]}="{v}"' for k, v in kw.items() if k in m and v is not None)


def box(x, y, w, h, *, bg=None, border=None, radius=0, shadow=None, z=None, **kw):
    """텍스트 없는 도형."""
    s = [f"position:absolute", f"left:{x}px", f"top:{y}px", f"width:{w}px", f"height:{h}px"]
    if bg: s.append(f"background:{bg}")
    if border: s.append(f"border:{border}")
    if radius: s.append(f"border-radius:{radius}px")
    if shadow: s.append(f"box-shadow:{shadow}")
    if z is not None: s.append(f"z-index:{z}")
    _parts.append(f'<div{_anim(kw)} style="{";".join(s)};"></div>')


def _units(seg: str) -> float:
    """한글은 한 칸, 라틴·숫자·공백은 반 칸으로 폭을 어림한다."""
    return sum(1.0 if ord(c) > 0x1100 else 0.52 for c in seg)


def _wrap(content: str, w: int, size: int) -> list[str]:
    """폭에 맞춰 직접 줄을 나눈다. 모든 줄바꿈을 <br> 로 선언해야 검증기가 '의도치 않은 줄바꿈'으로 보지 않는다."""
    per = max(1.0, (w - 16) / (size * 1.14))
    out: list[str] = []
    for para in content.split("\n"):
        words, line = para.split(" "), ""
        for word in words:
            cand = (line + " " + word).strip()
            if _units(cand) <= per or not line:
                line = cand
            else:
                out.append(line)
                line = word
        out.append(line)
    return out or [""]


def text(x, y, w, h, content, *, size=32, weight=400, color=INK, lh=1.5,
         align="left", ls=None, z=None, raw=False, **kw):
    """텍스트 블록. 카드 위에 얹을 때는 카드와 별개 요소로 둔다 (flex 안에 자식을 넣지 않는다).

    줄바꿈과 높이는 손으로 계산하지 않는다 — 폭에 맞춰 나누고, 줄 수 × 글자크기 × 행간으로 높이를 잡는다."""
    if not raw:
        lines = _wrap(content, w, size)
        content = "<br>".join(html.escape(l) for l in lines)
        n = len(lines)
    else:
        n = content.count("<br>") + 1
    # 여유를 크게 두면 빈 공간이 줄로 세어지고, 없으면 큰 글자가 잘린다. 글자 크기에 비례한 최소 여백만.
    h = math.ceil(n * size * lh) + math.ceil(size * 0.06) + 4
    s = [f"position:absolute", f"left:{x}px", f"top:{y}px", f"width:{w}px", f"height:{h}px",
         f"font-family:{F}", f"font-size:{size}px", f"font-weight:{weight}",
         f"color:{color}", f"line-height:{lh}", f"text-align:{align}"]
    if ls: s.append(f"letter-spacing:{ls}")
    if z is not None: s.append(f"z-index:{z}")
    _parts.append(f'<div{_anim(kw)} style="{";".join(s)};">{content}</div>')
    return h


def pill(x, y, w, h, label, *, fg, bg, border=None, size=20, **kw):
    """한 줄짜리 배지. 라벨이 접히지 않도록 폭을 자동으로 넓힌다."""
    w = max(w, int(_units(label) * size * 1.08) + 56)
    s = [f"position:absolute", f"left:{x}px", f"top:{y}px", f"width:{w}px", f"height:{h}px",
         f"background:{bg}", f"border-radius:{h // 2}px",
         f"font-family:{F}", f"font-size:{size}px", f"font-weight:500", f"color:{fg}",
         f"line-height:{h}px", "text-align:center", "white-space:nowrap", "overflow:hidden"]
    if border: s.append(f"border:{border}")
    _parts.append(f'<div{_anim(kw)} style="{";".join(s)};">{html.escape(label)}</div>')


class Screen:
    """화면 목업 하나. 창틀을 그리고, 안쪽 좌표를 창 기준으로 계산해준다."""

    def __init__(self, x, y, w, h, *, name=None, trig=None, anim="fadeIn", dir=None):
        self.x, self.y, self.w, self.h = x, y, w, h
        box(x, y, w, h, bg=PANEL, radius=18, shadow="0 24px 60px rgba(23,34,29,0.16)",
            border=f"1px solid {LINE}", anim=anim, name=name, trig=trig, dir=dir)
        # 상단 바 (모든 화면 공통)
        box(x, y, w, 62, bg=PANEL2, radius=18)
        box(x, y + 44, w, 18, bg=PANEL2)
        box(x, y + 61, w, 1, bg=LINE)

    def at(self, dx, dy):
        return self.x + dx, self.y + dy

    def topbar(self, left_label, *, right_label="자세히 보기", accent_right=False):
        x, y = self.x, self.y
        text(x + 26, y + 16, 520, 32, left_label, size=21, weight=600, color=INK)
        rw = 150
        text(x + self.w - rw - 26, y + 16, rw, 32, right_label, size=19,
             color=ACCENT if accent_right else MUTED, align="right")


def notes_col(x, y, w, blocks, *, size=27, gap=18, block_gap=52):
    """제목·본문을 계산된 높이로 쌓는다. y 를 손으로 정하면 글이 길어질 때 반드시 겹친다."""
    for i, (head, body, kw) in enumerate(blocks):
        y += text(x, y, w, 0, head, size=38, weight=700, **kw) + gap
        y += text(x, y, w, 0, body, size=size, color=MUTED, lh=1.7,
                  trig="with", ref=kw.get("name")) + block_gap
    return y


def slide(bg, transition=None, first=False):
    _parts.append("")  # 자리표시 — flush 에서 교체
    return len(_parts) - 1, bg, transition, first


# ---------------------------------------------------------------- 슬라이드 조립
slides: list[tuple[str, str, list[str]]] = []   # (배경, 노트, 요소들)


def begin():
    _parts.clear()


def end(bg, notes, transition="fade"):
    slides.append((bg, notes, list(_parts), transition))


# ============================================================ 1. 표지
begin()
box(0, 0, W, H, bg=BG)
box(0, 0, 22, H, bg=ACCENT)
text(150, 300, 1400, 60, "개인 컴퓨터를 혼자 관리하는 분을 위한", size=38, color=ACCENT,
     weight=500, anim="fadeIn", trig="auto", name="eyebrow")
text(150, 372, 1560, 260, "내 컴퓨터 지킴이<br>사용 안내", size=112, weight=900, lh=1.12,
     raw=True, anim="fadeIn", trig="after", ref="eyebrow", delay="150", name="title")
text(150, 668, 1400, 120, "보안을 몰라도 됩니다. 화면이 무엇을 해야 할지 알려줍니다.",
     size=42, color=MUTED, lh=1.5, anim="slideIn", dir="up", trig="after", ref="title", delay="150")
box(150, 830, 120, 8, bg=ACCENT, radius=4)
end(BG, """
안녕하세요. 새로 만든 보안 화면 사용법을 안내드리겠습니다.

이 화면은 보안을 잘 모르는 분이, 물어볼 사람 없이 혼자 판단할 수 있게 만든 것입니다.

오늘은 실제로 쓰게 될 순서 그대로 따라가 보겠습니다.
""")

# ============================================================ 2. 무엇이 달라졌나
begin()
box(0, 0, W, H, bg=PANEL)
text(150, 110, 1620, 90, "무엇이 달라졌나", size=76, weight=900, anim="fadeIn", trig="auto")

# 이전
box(150, 260, 760, 620, bg="#0d0d0d", radius=20, anim="fadeIn", name="before")
text(190, 300, 680, 44, "이전", size=28, weight=700, color="#00ff41", trig="with", ref="before")
for i in range(6):
    bx = 190 + (i % 2) * 350
    by = 364 + (i // 2) * 150
    box(bx, by, 320, 128, bg="#161616", border="1px solid rgba(0,255,65,0.35)", radius=6)
    text(bx + 16, by + 14, 288, 30, "패널", size=19, color="#00ff41")
    text(bx + 16, by + 52, 288, 60, "리스닝 포트 · 루프백\nDEFCON 3 · 미확인", size=17,
         color="#6b7280", lh=1.6)
text(190, 812, 680, 40, "패널 11개가 같은 무게로 한 화면에", size=24, color="#9ca3af",
     trig="with", ref="before")

# 이후
box(1010, 260, 760, 620, bg=BG, radius=20, border=f"1px solid {LINE}",
    anim="fadeIn", name="after")
text(1050, 300, 680, 44, "지금", size=28, weight=700, color=ACCENT, trig="with", ref="after")
box(1050, 364, 100, 100, bg=ACC_SOFT, radius=50, trig="with", ref="after")
text(1050, 392, 100, 44, "✓", size=44, color=ACCENT, align="center", trig="with", ref="after")
text(1178, 372, 560, 70, "이상 없음", size=58, weight=700, trig="with", ref="after")
text(1178, 444, 560, 44, "지금 손볼 일이 없어요.", size=28, color=MUTED, trig="with", ref="after")
for i, (lab, val) in enumerate([("밖에서 들어올 수 있는 문", "1개"),
                                ("밀린 보안 업데이트", "없음"),
                                ("막은 접속 시도", "23번")]):
    by = 552 + i * 88
    box(1050, by, 680, 76, bg=PANEL, radius=12, border=f"1px solid {LINE}")
    text(1074, by + 12, 460, 28, lab, size=21, color=MUTED)
    text(1074, by + 40, 460, 30, val, size=24, weight=700)
text(1050, 812, 680, 40, "상태 한 줄 + 오늘 할 일 + 안심 정보 셋", size=24, color=MUTED,
     trig="with", ref="after")
end(PANEL, """
왼쪽이 이전 화면입니다. 패널 열한 개가 똑같은 크기로 나열돼 있어서, 무엇이 중요한지 알 수 없었습니다.

오른쪽이 지금입니다. 화면이 답하는 질문은 하나입니다. 지금 내가 뭘 해야 하나.

전문가 화면을 없앤 게 아닙니다. 순서를 정해줬을 뿐이고, 원래 화면은 그대로 안에 있습니다.
""")

# ============================================================ 3. 평소 — 이상 없음
begin()
box(0, 0, W, H, bg=BG)
text(150, 96, 1000, 60, "장면 1", size=32, weight=700, color=ACCENT, anim="fadeIn", trig="auto")
text(150, 152, 1100, 90, "대부분의 날", size=72, weight=900, anim="fadeIn", trig="auto")

s = Screen(150, 292, 1080, 660, name="home", anim="fadeIn")
s.topbar("🛡  내 컴퓨터 지킴이")
box(*s.at(56, 130), 108, 108, bg=ACC_SOFT, radius=54)
text(*s.at(56, 158), 108, 52, "✓", size=52, color=ACCENT, align="center")
text(*s.at(196, 138), 700, 76, "이상 없음", size=62, weight=700)
text(*s.at(196, 218), 780, 40, "지금 손볼 일이 없어요. 이 창을 닫으셔도 돼요.", size=26, color=MUTED)
for i, (lab, val, note) in enumerate([
        ("밖에서 들어올 수 있는 문", "1개", "직접 열어두신 것이에요."),
        ("밀린 보안 업데이트", "없음", "오늘 아침에 12개 설치됨."),
        ("막은 접속 시도", "23번", "모두 들어오지 못했어요.")]):
    bx = 40 + i * 336
    box(*s.at(bx, 320), 316, 216, bg=PANEL, radius=14, border=f"1px solid {LINE}")
    text(*s.at(bx + 24, 344), 268, 32, lab, size=20, color=MUTED)
    text(*s.at(bx + 24, 392), 268, 56, val, size=44, weight=700)
    text(*s.at(bx + 24, 458), 268, 60, note, size=19, color=MUTED, lh=1.5)
text(*s.at(40, 578), 700, 40, "📊  무슨 일이 있었는지 보기", size=22, color=ACCENT)

notes_col(1310, 340, 470, [
    ("여기만 보면 됩니다",
     "상태 한 줄이 화면에서 가장 큽니다.\n‘이상 없음’이면 정말로 아무것도\n하지 않아도 됩니다.", dict(anim="slideIn", dir="up", name="n1")),
    ("숫자 셋의 뜻",
     "문 = 밖에서 들어올 수 있는 통로.\n업데이트 = 밀린 보안 수정.\n막은 시도 = 지킴이가 한 일.", dict(anim="slideIn", dir="up", name="n2")),
])
end(BG, """
먼저 평소의 화면입니다. 대부분의 날은 이 모습입니다.

가장 큰 글씨가 상태 한 줄입니다. ‘이상 없음’이면 정말로 아무것도 하지 않으셔도 됩니다. 창을 닫으셔도 됩니다.

아래 숫자 세 개는 안심하시라고 두는 것입니다. 밖에서 들어올 수 있는 문이 몇 개인지, 밀린 보안 업데이트가 있는지, 지킴이가 얼마나 막아냈는지.
""")

# ============================================================ 4. 할 일이 생기면
begin()
box(0, 0, W, H, bg=BG)
text(150, 96, 1000, 60, "장면 2", size=32, weight=700, color=WARN, anim="fadeIn", trig="auto")
text(150, 152, 1300, 90, "손볼 일이 생기면", size=72, weight=900, anim="fadeIn", trig="auto")

s = Screen(150, 292, 1080, 660, name="todo", anim="fadeIn")
s.topbar("🛡  내 컴퓨터 지킴이")
box(*s.at(40, 96), 88, 88, bg=WARN_SOFT, radius=44)
text(*s.at(40, 118), 88, 46, "!", size=46, weight=900, color=WARN, align="center")
text(*s.at(152, 100), 700, 62, "살펴보세요", size=50, weight=700)
text(*s.at(152, 164), 820, 36, "손볼 일이 한 가지 있어요. 오늘 중에 해두는 게 좋아요.",
     size=24, color=MUTED)

box(*s.at(40, 236), 1000, 250, bg=PANEL, radius=16, border=f"2px solid {WARN}",
    name="card", anim="slideIn", dir="up")
box(*s.at(72, 268), 62, 62, bg=WARN_SOFT, radius=12, trig="with", ref="card")
text(*s.at(72, 284), 62, 34, "🔒", size=30, align="center", trig="with", ref="card")
text(*s.at(156, 266), 820, 44, "다른 사람이 고칠 수 있는 파일이 3개 있어요",
     size=32, weight=700, trig="with", ref="card")
text(*s.at(156, 318), 830, 96,
     "이 파일들은 로그인할 때마다 자동으로 실행돼요. 다른 사람이 내용을 바꿔 놓으면 "
     "내가 로그인할 때 그 프로그램이 내 이름으로 함께 실행돼요.",
     size=22, color=MUTED, lh=1.65, trig="with", ref="card")
pill(*s.at(156, 424), 132, 52, "잠그기", fg="#ffffff", bg=ACCENT, size=23,
     trig="with", ref="card")
pill(*s.at(304, 424), 300, 52, "무엇이 바뀌는지 먼저 보기", fg=INK, bg=PANEL,
     border=f"1px solid {LINE2}", size=21, trig="with", ref="card")

notes_col(1310, 340, 480, [
    ("할 일이 있을 때만",
     "평소에는 이 카드가 아예 없습니다.\n빈 목록도 띄우지 않습니다.\n\n"
     "그래야 카드가 보일 때\n‘진짜 볼 것이 생겼구나’ 하고\n눈이 갑니다.", dict(anim="slideIn", dir="up", name="p1")),
    ("급한 정도는 색으로", "노랑 = 오늘 중에\n빨강 = 지금 바로", dict(anim="slideIn", dir="up", name="p2")),
])
end(BG, """
손볼 일이 생기면 이렇게 바뀝니다. 상태 줄이 ‘살펴보세요’가 되고, 그 아래 할 일 카드가 하나 뜹니다.

중요한 건, 할 일이 없을 때는 이 카드가 아예 없다는 점입니다. 빈 목록도 띄우지 않습니다. 그래야 카드가 보이는 날에 눈이 갑니다.

색으로 급한 정도를 구분합니다. 노란색이면 오늘 중에, 빨간색이면 지금 바로 봐주세요.
""")

# ============================================================ 5. 미리보기
begin()
box(0, 0, W, H, bg=PANEL)
text(150, 96, 1000, 60, "장면 3", size=32, weight=700, color=ACCENT, anim="fadeIn", trig="auto")
text(150, 152, 1500, 90, "누르기 전에 무엇이 바뀌는지 봅니다", size=68, weight=900,
     anim="fadeIn", trig="auto")

s = Screen(150, 300, 1180, 640, name="prev", anim="fadeIn")
s.topbar("←  돌아가기")
text(*s.at(48, 96), 900, 50, "다른 사람이 고칠 수 있는 파일 3개", size=38, weight=700)

box(*s.at(48, 168), 1084, 300, bg=PANEL, radius=14, border=f"1px solid {LINE}")
box(*s.at(48, 168), 1084, 60, bg=PANEL2, radius=14)
box(*s.at(48, 210), 1084, 18, bg=PANEL2)
text(*s.at(72, 184), 700, 34, "무엇이 바뀌는지 먼저 보여드릴게요", size=23, weight=600)
cols = [(72, 460, "파일"), (552, 250, "지금"), (850, 250, "잠근 뒤")]
for cx, cw, lab in cols:
    text(*s.at(cx, 240), cw, 26, lab, size=18, color=MUTED)
rows = [("로그인할 때 실행되는 설정", "누구나 고칠 수 있음", "나만 고칠 수 있음"),
        ("터미널을 열 때 실행되는 설정", "누구나 고칠 수 있음", "나만 고칠 수 있음"),
        ("내가 설치한 프로그램 폴더", "누구나 넣을 수 있음", "나만 열 수 있음")]
for i, (a, b, c) in enumerate(rows):
    ry = 272 + i * 52
    box(*s.at(72, ry - 8), 1036, 1, bg="#eef2f0")
    text(*s.at(72, ry), 460, 0, a, size=21)
    text(*s.at(552, ry), 250, 0, b, size=19, color=MUTED)
    text(*s.at(812, ry), 28, 0, "→", size=20, color=LINE2)
    text(*s.at(850, ry), 250, 0, c, size=19, weight=600, color=ACCENT)
box(*s.at(48, 432), 1084, 36, bg="#f7fbf9")
text(*s.at(76, 438), 900, 30, "✓  잠그기만 해요. 지금 쓰시던 기능이 안 되는 일은 없어요.",
     size=21, color=MUTED)

pill(*s.at(48, 500), 150, 56, "잠그기", fg="#ffffff", bg=ACCENT, size=24,
     anim="pop", name="btn")
pill(*s.at(214, 500), 130, 56, "나중에", fg=INK, bg=PANEL, border=f"1px solid {LINE2}",
     size=22, trig="with", ref="btn")

notes_col(1400, 360, 390, [
    ("먼저 보여주고",
     "전 → 후를 표로 보여준 다음에\n누르게 합니다.\n\n"
     "뜻을 모르는 채 눌러서\n필요한 걸 꺼버리는 일을\n막기 위해서입니다.", dict(anim="slideIn", dir="up", name="q1")),
    ("좁히기만 합니다", "지킴이는 자물쇠를 잠그기만 하고\n열지는 않습니다.", dict(anim="slideIn", dir="up", name="q2")),
], size=26)
end(PANEL, """
카드를 누르면 상세 화면이 열립니다. 여기서 바로 처리하지 않습니다.

먼저 무엇이 어떻게 바뀌는지 표로 보여드립니다. 왼쪽이 지금, 오른쪽이 잠근 뒤입니다. 이걸 보고 나서 누르시면 됩니다.

그리고 지킴이는 자물쇠를 잠그기만 합니다. 열지는 않습니다. 그래서 이 버튼을 눌러서 쓰던 기능이 안 되는 일은 생기지 않습니다.
""")

# ============================================================ 6. 결과
begin()
box(0, 0, W, H, bg=BG)
text(150, 96, 1000, 60, "장면 4", size=32, weight=700, color=ACCENT, anim="fadeIn", trig="auto")
text(150, 152, 1300, 90, "무엇이 바뀌었는지 다시", size=72, weight=900,
     anim="fadeIn", trig="auto")

s = Screen(150, 300, 1080, 600, name="done", anim="fadeIn")
s.topbar("←  돌아가기")
box(*s.at(48, 110), 92, 92, bg=ACC_SOFT, radius=46)
text(*s.at(48, 134), 92, 46, "🔒", size=42, align="center")
text(*s.at(168, 116), 700, 60, "잠갔어요", size=50, weight=700)
text(*s.at(168, 180), 760, 38, "파일 3개를 나만 고칠 수 있게 바꿨어요.", size=25, color=MUTED)

box(*s.at(48, 250), 984, 190, bg=PANEL, radius=14, border=f"1px solid {LINE}")
box(*s.at(48, 250), 984, 46, bg=PANEL2, radius=14)
box(*s.at(48, 282), 984, 14, bg=PANEL2)
for cx, cw, lab in [(76, 370, "파일"), (456, 240, "잠그기 전"), (744, 250, "지금")]:
    text(*s.at(cx, 262), cw, 26, lab, size=18, color=MUTED)
for i, (a, b, c) in enumerate(rows):
    ry = 312 + i * 42
    text(*s.at(76, ry), 370, 0, a, size=19)
    text(*s.at(456, ry), 240, 0, b, size=18, color=MUTED)
    text(*s.at(706, ry), 28, 0, "→", size=19, color=LINE2)
    text(*s.at(744, ry), 250, 0, c, size=18, weight=600, color=ACCENT)

box(*s.at(48, 466), 984, 74, bg=PANEL, radius=14, border=f"1px solid {LINE}")
text(*s.at(76, 480), 900, 30, "혹시 뭔가 안 되나요?", size=22, weight=700)
text(*s.at(76, 508), 920, 28, "이 변경은 기록에 남아 있어요. 되돌리는 방법도 거기에 적어뒀어요.",
     size=20, color=MUTED)

notes_col(1310, 360, 480, [
    ("약속한 그대로",
     "미리보기에서 쓴 문구를\n결과 화면에서도 똑같이 씁니다.\n\n"
     "말이 달라지면 무엇이 일어났는지\n대조할 수 없기 때문입니다.", dict(anim="slideIn", dir="up", name="r1")),
    ("되돌리는 법도 함께",
     "기록 화면에서 언제 무엇이 바뀌었는지\n보고 되돌릴 수 있습니다.", dict(anim="slideIn", dir="up", name="r2")),
], size=26)
end(BG, """
누르고 나면 무엇이 바뀌었는지 다시 보여드립니다.

여기서 쓰는 말은 미리보기에서 쓴 말과 똑같습니다. ‘누구나 고칠 수 있음’이 ‘나만 고칠 수 있음’으로. 말이 달라지면 사용자가 무슨 일이 일어났는지 대조할 수 없습니다.

되돌리는 방법도 함께 알려드립니다. 기록 화면에 그대로 남아 있습니다.
""")

# ============================================================ 7. 판단이 필요한 일
begin()
box(0, 0, W, H, bg=PANEL)
text(150, 90, 1000, 60, "장면 5", size=32, weight=700, color=CRIT, anim="fadeIn", trig="auto")
text(150, 146, 1500, 90, "지킴이가 대신 못 하는 일", size=68, weight=900,
     anim="fadeIn", trig="auto")
text(150, 250, 1560, 50, "본인이 한 일인지 아닌지는 사용자만 알 수 있습니다.",
     size=32, color=MUTED, anim="fadeIn", trig="auto")

s = Screen(150, 336, 1080, 600, name="judge", anim="fadeIn")
s.topbar("←  돌아가기")
text(*s.at(48, 96), 300, 34, "지금 확인하세요", size=22, weight=600, color=CRIT)
text(*s.at(48, 132), 900, 52, "처음 보는 곳에서 로그인에 성공했어요", size=38, weight=700)

box(*s.at(48, 206), 984, 150, bg=PANEL, radius=14, border=f"1px solid {LINE}")
for i, (k, v) in enumerate([("언제", "오늘 새벽 3시 12분"),
                            ("어디서", "해외 · 지금까지 접속한 적 없는 곳"),
                            ("어떻게", "미리 등록해 둔 열쇠 파일로 들어왔어요")]):
    ry = 228 + i * 42
    text(*s.at(76, ry), 130, 32, k, size=21, color=MUTED)
    text(*s.at(220, ry), 780, 32, v, size=21)

text(*s.at(48, 384), 700, 40, "이때 직접 접속하셨나요?", size=26, weight=700)
pill(*s.at(48, 434), 210, 54, "네, 제가 했어요", fg=INK, bg=PANEL,
     border=f"1px solid {LINE2}", size=21, anim="pop", name="ans")
pill(*s.at(276, 434), 250, 54, "아니요, 제가 안 했어요", fg=CRIT, bg=PANEL,
     border=f"1px solid {CRIT}", size=21, trig="with", ref="ans")
pill(*s.at(544, 434), 180, 54, "잘 모르겠어요", fg=MUTED, bg=PANEL2, size=21,
     trig="with", ref="ans")

box(*s.at(48, 508), 984, 62, bg=ACC_SOFT, radius=12)
text(*s.at(76, 522), 920, 34, "👁  지킴이가 본 것  1건   —   열어보기",
     size=22, weight=600, color=ACCENT)

notes_col(1310, 326, 480, [
    ("세 갈래로 나눈 이유",
     "‘아니요’와 ‘모르겠어요’는\n다음에 할 일이 다릅니다.\n\n"
     "아니요 → 긴급으로 올리고\n              순서대로 안내\n"
     "모르겠어요 → ‘확인 중’으로 두고\n                      재촉하지 않음", dict(anim="slideIn", dir="up", name="j1")),
    ("근거를 먼저 보세요",
     "기억이 안 나면 ‘지킴이가 본 것’을\n펼쳐서 확인하고 정하세요.", dict(anim="slideIn", dir="up", name="j2")),
], size=26)
end(PANEL, """
어떤 일은 지킴이가 대신 고칠 수 없습니다. 본인이 한 일인지 아닌지는 사용자만 알기 때문입니다.

그래서 사실만 보여드리고 물어봅니다. 언제, 어디서, 어떻게 들어왔는지.

답은 셋입니다. ‘아니요’와 ‘모르겠어요’를 나눈 이유는 다음에 할 일이 다르기 때문입니다. 아니라고 하시면 긴급으로 올리고 순서대로 안내하고, 모르겠다고 하시면 ‘확인 중’으로 두고 재촉하지 않습니다.

기억이 잘 안 나시면 아래 ‘지킴이가 본 것’을 펼쳐서 언제 무슨 일이 있었는지 확인하고 정하시면 됩니다.
""")

# ============================================================ 8. 복사해서 물어보기
begin()
box(0, 0, W, H, bg=DARK)
text(150, 110, 1000, 60, "장면 6", size=32, weight=700, color="#7fd3c1",
     anim="fadeIn", trig="auto")
text(150, 166, 1500, 90, "그래도 모르겠으면", size=72, weight=900, color="#f2f5f3",
     anim="fadeIn", trig="auto")
text(150, 274, 1560, 50, "설명을 통째로 복사해 다른 곳에 물어볼 수 있습니다.",
     size=32, color="#9fb3ab", anim="fadeIn", trig="auto")

box(150, 366, 900, 520, bg="#1b2f28", radius=16, border="1px solid #2f4a41",
    anim="fadeIn", name="copy")
text(186, 400, 830, 40, "설명이 어렵거나 더 묻고 싶으면", size=27, weight=700,
     color="#f2f5f3", trig="with", ref="copy")
text(186, 448, 840, 100,
     "위 내용을 그대로 복사해서 Claude 같은 AI나 잘 아는 분에게 붙여넣어 물어보세요. "
     "무엇을 물어보면 좋을지까지 함께 적어드려요.",
     size=22, color="#9fb3ab", lh=1.65, trig="with", ref="copy")
box(186, 570, 40, 40, bg=ACCENT, radius=8, trig="with", ref="copy")
text(194, 576, 26, 30, "✓", size=22, color="#ffffff", align="center", trig="with", ref="copy")
text(244, 570, 780, 40, "중요한 정보 가리기", size=25, weight=700, color="#f2f5f3",
     trig="with", ref="copy")
text(244, 614, 790, 130,
     "컴퓨터 이름, 계정 이름, 인터넷 주소를 <이렇게> 바꿔서 복사해요. "
     "운영체제·프로그램 이름은 남겨요 — 그게 있어야 제대로 된 답을 받을 수 있고, "
     "그것만으로는 이 컴퓨터를 찾아낼 수 없거든요.",
     size=21, color="#9fb3ab", lh=1.7, trig="with", ref="copy")
pill(186, 776, 170, 56, "복사하기", fg="#ffffff", bg=ACCENT, size=23,
     trig="with", ref="copy")
pill(372, 776, 280, 56, "무엇이 복사되는지 보기", fg="#9fb3ab", bg="#243c34", size=21,
     trig="with", ref="copy")

box(1110, 366, 660, 520, bg="#0f1c18", radius=16, border="1px solid #2f4a41",
    anim="slideIn", dir="up", name="out")
text(1146, 398, 600, 36, "복사되는 글", size=22, weight=700, color="#7fd3c1",
     trig="with", ref="out")
text(1146, 444, 590, 400,
     "# 제 컴퓨터에 이런 알림이 떴는데…<br><br>"
     "저는 보안을 잘 모르는 사람이고,<br>제 개인 컴퓨터를 혼자 관리하고 있어요.<br><br>"
     "## 보안 프로그램이 실제로 본 것<br>"
     "1. 계정 목록 변경됨<br>"
     "&nbsp;&nbsp;&nbsp;- <span style=\"color:#7fd3c1\">&lt;사용자 A&gt;</span> 삭제<br>"
     "&nbsp;&nbsp;&nbsp;- <span style=\"color:#7fd3c1\">&lt;외부주소 1&gt;</span> 에서 접속<br><br>"
     "## 물어보고 싶은 것<br>"
     "1. 이게 실제로 위험한 상황인가요?<br>"
     "2. 제가 직접 할 수 있는 일은?",
     size=20, color="#c6d6d0", lh=1.75, raw=True, trig="with", ref="out")
end(DARK, """
설명을 읽어도 모르겠을 때가 있습니다. 그럴 때는 내용을 통째로 복사해서 다른 곳에 물어보실 수 있습니다.

무엇을 물어보면 좋을지까지 같이 적어드립니다. 질문을 만드는 것 자체가 어려우니까요.

그리고 기본으로 중요한 정보를 가립니다. 컴퓨터 이름, 계정 이름, 인터넷 주소는 이렇게 꺾쇠로 바꿔서 나갑니다. 운영체제나 프로그램 이름은 남깁니다. 그게 있어야 제대로 된 답이 오고, 그것만으로는 이 컴퓨터를 찾아낼 수 없기 때문입니다.
""")

# ============================================================ 9. 기록과 자세히 보기
begin()
box(0, 0, W, H, bg=BG)
text(150, 96, 1000, 60, "장면 7", size=32, weight=700, color=ACCENT, anim="fadeIn", trig="auto")
text(150, 152, 1500, 90, "무슨 일이 있었나 · 근거는 어디에", size=68, weight=900,
     anim="fadeIn", trig="auto")

# 기록
s = Screen(150, 300, 800, 620, name="hist", anim="fadeIn")
s.topbar("←  돌아가기")
text(*s.at(40, 96), 600, 46, "무슨 일이 있었는지", size=34, weight=700)
box(*s.at(40, 158), 720, 400, bg=PANEL, radius=14, border=f"1px solid {LINE}")
box(*s.at(40, 158), 720, 40, bg=PANEL2, radius=14)
text(*s.at(64, 166), 300, 28, "오늘", size=19, weight=600, color=MUTED)
hist = [("15:44", "파일 3개를 나만 고칠 수 있게 잠갔어요", "내가 함"),
        ("15:30", "다른 사람이 고칠 수 있는 파일 3개를 찾았어요", "자동 점검"),
        ("09:12", "보안 업데이트 12개가 설치됐어요", "자동"),
        ("어제", "비밀번호를 계속 찍어보던 상대를 막았어요", "자동 차단")]
for i, (t_, d_, w_) in enumerate(hist):
    ry = 210 + i * 82
    box(*s.at(64, ry - 10), 672, 1, bg="#eef2f0")
    text(*s.at(64, ry), 90, 30, t_, size=19, color=MUTED)
    text(*s.at(168, ry), 420, 34, d_, size=21)
    text(*s.at(600, ry), 130, 30, w_, size=17, color=MUTED, align="right")

# 자세히 보기
s2 = Screen(1010, 300, 760, 620, name="exp", anim="slideIn", dir="up")
s2.topbar("←  돌아가기", right_label="쉬운 화면으로", accent_right=True)
text(*s2.at(40, 96), 400, 46, "자세히 보기", size=34, weight=700)
pill(*s2.at(520, 100), 180, 46, "모두 펼치기", fg=INK, bg=PANEL,
     border=f"1px solid {LINE2}", size=20)
box(*s2.at(40, 168), 680, 390, bg=PANEL, radius=14, border=f"1px solid {LINE}")
folds = ["밖에서 들어올 수 있는 문", "파일과 프로그램 설정", "이 컴퓨터를 쓰는 사람",
         "막은 상대", "지킴이가 보고 있는 것", "알림 전체"]
for i, f_ in enumerate(folds):
    ry = 190 + i * 62
    if i: box(*s2.at(64, ry - 12), 632, 1, bg="#eef2f0")
    text(*s2.at(64, ry), 500, 34, f_, size=21)
    text(*s2.at(640, ry), 40, 34, "⌄", size=22, color=MUTED, align="right")

text(150, 952, 1620, 60,
     "전문가 화면은 없애지 않았습니다. 어느 화면에서든 오른쪽 위 ‘자세히 보기’로 열립니다.",
     size=30, color=MUTED, anim="fadeIn", name="foot")
end(BG, """
왼쪽은 기록입니다. 지킴이가 한 일과 컴퓨터에 생긴 일을 시간 순서로 적어둡니다. 줄을 누르면 자세히 볼 수 있고, 되돌리는 방법도 여기 있습니다.

오른쪽은 자세히 보기입니다. 지킴이가 무엇을 보고 그렇게 판단했는지 전부 여기 있습니다. 예전에 쓰시던 전문가 화면이 하나도 빠짐없이 이 안에 들어 있습니다.

‘모두 펼치기’를 누르면 예전처럼 한 화면에서 전부 볼 수 있습니다. 그리고 이 전환 버튼은 어느 화면에서든 오른쪽 위 같은 자리에 있습니다.
""")

# ============================================================ 10. 정리
begin()
box(0, 0, W, H, bg=ACCENT)
text(150, 200, 1620, 100, "기억할 것은 셋", size=84, weight=900, color="#ffffff",
     anim="fadeIn", trig="auto")
items = [("1", "‘이상 없음’이면 아무것도 안 해도 됩니다",
          "대부분의 날이 그렇습니다. 창을 닫으셔도 됩니다."),
         ("2", "할 일이 뜨면 눌러서 미리보기부터 보세요",
          "무엇이 바뀌는지 보고 나서 정하시면 됩니다."),
         ("3", "모르겠으면 복사해서 물어보세요",
          "중요한 정보는 가려서 나갑니다. 억지로 판단하지 않으셔도 됩니다.")]
for i, (n, t_, d_) in enumerate(items):
    ty = 380 + i * 190
    nm = f"it{i}"
    box(150, ty, 92, 92, bg="#0a5f52", radius=46, anim="slideIn", dir="up", name=nm)
    text(150, ty + 22, 92, 50, n, size=44, weight=900, color="#ffffff", align="center",
         trig="with", ref=nm)
    text(288, ty + 4, 1480, 56, t_, size=42, weight=700, color="#ffffff",
         trig="with", ref=nm)
    text(288, ty + 68, 1480, 46, d_, size=28, color="#bfe3da", trig="with", ref=nm)
end(ACCENT, """
정리하겠습니다. 기억하실 것은 세 가지입니다.

첫째, ‘이상 없음’이면 아무것도 하지 않으셔도 됩니다. 대부분의 날이 그렇습니다.

둘째, 할 일이 뜨면 눌러서 미리보기를 먼저 보세요. 무엇이 바뀌는지 보고 나서 정하시면 됩니다.

셋째, 모르겠으면 복사해서 물어보세요. 중요한 정보는 가려서 나가니 안심하셔도 됩니다. 억지로 혼자 판단하지 않으셔도 됩니다.
""")

# ---------------------------------------------------------------- 출력
out = ["""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>내 컴퓨터 지킴이 사용 안내</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;700&display=swap">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { width: 1920px; height: 1080px; overflow: hidden; position: relative; background: #12211c; }
.slide { position: absolute; inset: 0; display: none; overflow: hidden; background: #fff; }
.slide.active { display: block; }
</style>
</head>
<body>
"""]
for i, (bg, notes, parts, transition) in enumerate(slides):
    cls = "slide active" if i == 0 else "slide"
    out.append(f'  <div class="{cls}" data-transition="{transition}" '
               f'style="width:{W}px;height:{H}px;background:{bg};font-family:{F};">')
    out.extend("    " + p for p in parts if p)
    out.append('    <script type="text/plain" class="fe-notes">')
    out.append(notes.strip())
    out.append('    </script>')
    out.append('  </div>')
out.append("</body>\n</html>")
print("\n".join(out))
