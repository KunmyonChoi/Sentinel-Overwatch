"""이 컴퓨터에 사람이 직접 앉을 수 있는가 — 물리 접근 가능성 판정.

왜 필요한가: 홈의 '지금 할 수 있는 것' 첫 줄은 USB 저장장치 차단 상태다. 그 줄의 조작은
'누가 이 기계 앞에 와서 USB 메모리를 꽂는' 상황을 위한 것이다. 아무도 손댈 수 없는 기계실의
원격 서버에서는 그 줄이 잡음이다 — 꽂을 사람이 없는데 "잠깐 쓰기" 버튼이 홈의 자리를 차지한다.

대시보드는 서버에서 돌고 화면은 SSH 터널을 타고 다른 곳에서 열릴 수 있다. 그래서 서버는
'보는 사람이 어디 있는지'를 알 수 없다. 알 수 있는 것은 '이 기계 앞에 앉는 자리가 있는지'뿐이고,
이 모듈은 그것만 본다.

무엇을 읽는가 (모두 읽기 전용. sudo 없이 서비스 계정으로 읽힌다):

1. ``/run/systemd/seats`` — systemd-logind 가 만드는 seat. 그래픽 카드·화면·키보드가 udev 로
   한 묶음이 되면 ``seat0`` 파일이 생긴다. 헤드리스 서버에는 보통 자리가 하나도 없다.
   이것을 1차 신호로 쓴다. '남이 앞에 앉을 수 있는가'를 가장 직접적으로 말해주기 때문이다.
2. ``/sys/class/dmi/id/chassis_type`` — SMBIOS 섀시 종류. 자리가 없을 때만 본다.
3. 가상 머신·컨테이너 표시 — ``/run/systemd/container`` 와 DMI 제조사·제품 이름 속 알려진 낱말.
   역시 자리가 없을 때만 본다.

판정 규칙:

- 앉는 자리가 있으면 → **보여준다.** 사람이 앞에 앉아 USB 를 꽂을 수 있는 컴퓨터다.
- 자리가 없고 가상 머신·컨테이너이거나 섀시가 서버·랙·블레이드면 → **숨긴다.**
- 자리가 없지만 섀시가 데스크톱·노트북이면 → **보여준다.** 신호가 서로 엇갈린다.
- 자리 정보를 못 읽었거나 섀시도 모르면 → **보여준다.**

마지막 두 줄이 이 모듈의 원칙이다: **모르면 보여준다.** 추측으로 보안 조작을 감추는 것이
필요 없는 줄 하나를 그리는 것보다 나쁘다. 숨기려면 '앉는 자리가 없다'는 적극적인 근거가
있어야 한다. 그리고 운영자가 ``SECDASH_PHYSICAL_ACCESS`` 로 정해 두면 자동 판정보다 그 값이 이긴다.
"""
import os
import re

SEATS_DIR = "/run/systemd/seats"
CHASSIS_PATH = "/sys/class/dmi/id/chassis_type"
# 컨테이너 표시. /run/systemd/container 에는 컨테이너 관리자 이름이 한 줄 들어 있고,
# /.dockerenv 는 내용이 없는 표식이다.
CONTAINER_MARKERS = ("/run/systemd/container", "/.dockerenv")
DMI_ID_PATHS = ("/sys/class/dmi/id/sys_vendor", "/sys/class/dmi/id/product_name")

MODES = ("auto", "always", "never")

# SMBIOS 섀시 종류(SMBIOS 7.4.1 Table). 사람이 앞에 앉는 형태와 기계실에 놓는 형태만
# 분류하고, 나머지(1 기타, 2 알 수 없음, 33 IoT 게이트웨이 …)는 '모름'으로 둔다.
# 모름은 숨기는 근거가 되지 못한다.
DESK_CHASSIS = {3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16, 24, 30, 31, 32, 35, 36}
MACHINE_ROOM_CHASSIS = {17, 18, 19, 20, 21, 22, 23, 25, 26, 27, 28, 29}

# DMI 문자열에서 찾을 가상화 낱말 → 화면에 쓸 이름. 원문은 내보내지 않는다.
# 제조사·제품 이름은 이 호스트의 정보이고, 화면에 필요한 것은 '가상 머신이다'라는 사실뿐이다.
VIRT_KEYWORDS = (
    ("qemu", "QEMU"),
    ("bochs", "QEMU"),
    ("kvm", "KVM"),
    ("vmware", "VMware"),
    ("virtualbox", "VirtualBox"),
    ("innotek", "VirtualBox"),
    ("xen", "Xen"),
    ("bhyve", "bhyve"),
    ("parallels", "Parallels"),
    ("hyper-v", "Hyper-V"),
    ("virtual machine", "가상 머신"),
    ("openstack", "OpenStack"),
    ("amazon ec2", "Amazon EC2"),
    ("google compute engine", "Google Compute Engine"),
    ("alibaba cloud", "Alibaba Cloud"),
)

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")


def _seat_signal(seats_dir: str) -> tuple[str, str]:
    """('present' | 'absent' | 'unknown', 한국어 근거)

    'unknown' 과 'absent' 를 구별하는 것이 이 함수의 핵심이다. 디렉터리를 못 읽은 것은
    '자리가 없다'는 뜻이 아니다 (logind 가 없거나 이 계정이 못 읽는 경우다).
    """
    try:
        names = sorted(n for n in os.listdir(seats_dir) if not n.startswith("."))
    except OSError:
        return "unknown", f"{seats_dir} 를 읽지 못했어요"
    if names:
        shown = ", ".join(n for n in names[:3] if _SAFE_NAME.match(n))
        detail = f"앉는 자리가 {len(names)}개 있어요"
        return "present", f"{detail}({shown})" if shown else detail
    return "absent", f"{seats_dir} 가 비어 있어요 (앉는 자리 0개)"


def _chassis(chassis_path: str) -> tuple[int | None, str]:
    """(SMBIOS 섀시 번호, 'desk' | 'machine_room' | 'unknown')"""
    try:
        with open(chassis_path, encoding="utf-8", errors="replace") as f:
            code = int(f.read().strip())
    except (OSError, ValueError):
        return None, "unknown"
    if code in MACHINE_ROOM_CHASSIS:
        return code, "machine_room"
    if code in DESK_CHASSIS:
        return code, "desk"
    return code, "unknown"


def _virtualized(container_markers, dmi_paths) -> str:
    """가상 머신·컨테이너면 화면에 쓸 이름, 아니면 빈 문자열."""
    for path in container_markers:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                name = f.read().strip()
        except OSError:
            continue
        return f"컨테이너({name})" if _SAFE_NAME.match(name) else "컨테이너"
    for path in dmi_paths:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read().strip().lower()
        except OSError:
            continue
        for needle, label in VIRT_KEYWORDS:
            if needle in text:
                return label
    return ""


def physical_access(
    mode: str | None = None,
    seats_dir: str = SEATS_DIR,
    chassis_path: str = CHASSIS_PATH,
    container_markers=CONTAINER_MARKERS,
    dmi_paths=DMI_ID_PATHS,
) -> dict:
    """USB 줄을 그려도 되는지와 그렇게 정한 이유.

    ``usb_relevant`` 만 화면이 쓴다. ``reason`` 은 궁금한 운영자가 '자세히 보기'에서 읽는다.
    """
    if mode is None:
        import config
        mode = config.PHYSICAL_ACCESS
    mode = (mode or "auto").strip().lower()
    prefix = ""
    if mode not in MODES:
        prefix = "SECDASH_PHYSICAL_ACCESS 값을 알아듣지 못해 자동 판정으로 돌아갔어요. "
        mode = "auto"

    not_checked = {"seat": "not_checked", "chassis_type": None, "chassis_kind": "not_checked", "virtualized": None}
    if mode == "always":
        return {
            "usb_relevant": True, "mode": mode, "signals": not_checked,
            "reason": prefix + "설정에서 '사람이 이 컴퓨터 앞에 앉을 수 있다'(always)로 정해 두었어요.",
        }
    if mode == "never":
        return {
            "usb_relevant": False, "mode": mode, "signals": not_checked,
            "reason": prefix + "설정에서 '아무도 이 컴퓨터에 직접 손댈 수 없다'(never)로 정해 두었어요.",
        }

    seat, seat_why = _seat_signal(seats_dir)
    code, kind = _chassis(chassis_path)
    virt = _virtualized(container_markers, dmi_paths)
    signals = {"seat": seat, "chassis_type": code, "chassis_kind": kind, "virtualized": virt or None}

    def out(relevant: bool, reason: str) -> dict:
        return {"usb_relevant": relevant, "mode": mode, "reason": prefix + reason, "signals": signals}

    if seat == "present":
        return out(True, f"{seat_why}. 화면과 키보드를 꽂는 자리가 있으니, 누가 앞에 앉아 "
                         "USB 를 꽂을 수 있는 컴퓨터로 봅니다.")
    if seat == "unknown":
        return out(True, f"{seat_why}. 앞에 앉는 자리가 있는지 확인할 수 없어서 그대로 보여줍니다 — "
                         "몰라서 감추지는 않아요.")
    if virt:
        return out(False, f"{seat_why}. 게다가 {virt} 위에서 돌고 있어서, 이 기계에 직접 USB 를 "
                          "꽂을 수 있는 사람이 없다고 봅니다.")
    if kind == "machine_room":
        return out(False, f"{seat_why}. 섀시도 서버·랙 종류(SMBIOS {code})예요. 앞에 앉을 사람이 "
                          "없는 컴퓨터로 봅니다.")
    if kind == "desk":
        return out(True, f"{seat_why}. 그런데 섀시는 책상에 두는 종류(SMBIOS {code})예요. 신호가 "
                         "엇갈리니 그대로 보여줍니다.")
    return out(True, f"{seat_why}. 섀시 종류는 알 수 없었어요. 확실하지 않으니 그대로 보여줍니다.")
