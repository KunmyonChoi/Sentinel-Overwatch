"""홈의 USB 저장장치 줄을 언제 숨기는가 — 물리 접근 판정.

원칙 하나만 지키면 된다: **모르면 보여준다.** 이 파일의 절반은 그 원칙이 깨지지 않았는지 본다.
숨기려면 '이 기계 앞에 앉는 자리가 없다'는 적극적인 근거가 있어야 한다.
"""
from fastapi.testclient import TestClient

from integrations.presence import MODES, physical_access

H = {"X-API-Token": "test-token"}


def _paths(tmp_path, *, seats="missing", chassis=None, vendor="", product="", container=None, tag=""):
    """신호 파일 모양을 만들어 physical_access 인자로 돌려준다.

    seats: "missing"(디렉터리 자체가 없음) | "empty" | 자리 이름 목록
    chassis: SMBIOS 번호, 문자열(쓰레기 값), 또는 None(파일 없음)
    tag: 한 테스트에서 여러 모양을 만들 때 서로 섞이지 않게 하는 이름
    """
    root = tmp_path / f"case{tag}"
    root.mkdir()
    tmp_path = root
    seats_dir = tmp_path / "seats"
    if seats == "empty":
        seats_dir.mkdir()
    elif seats != "missing":
        seats_dir.mkdir()
        for name in seats:
            (seats_dir / name).write_text("IS_SEAT0=1\n")

    chassis_path = tmp_path / "chassis_type"
    if chassis is not None:
        chassis_path.write_text(f"{chassis}\n")

    vendor_path = tmp_path / "sys_vendor"
    vendor_path.write_text(vendor)
    product_path = tmp_path / "product_name"
    product_path.write_text(product)

    markers = ()
    if container is not None:
        marker = tmp_path / "container"
        marker.write_text(container)
        markers = (str(marker),)

    return dict(seats_dir=str(seats_dir), chassis_path=str(chassis_path),
                container_markers=markers, dmi_paths=(str(vendor_path), str(product_path)))


# --- 자리(seat)가 1차 신호다 ---

def test_seat_means_someone_can_walk_up_even_on_a_server_chassis(tmp_path):
    """자리가 있으면 섀시가 뭐라고 하든 보여준다. 콘솔이 붙은 랙 서버도 USB 를 꽂을 수 있다."""
    r = physical_access(mode="auto", **_paths(tmp_path, seats=["seat0"], chassis=23))
    assert r["usb_relevant"] is True
    assert r["signals"]["seat"] == "present" and "자리" in r["reason"]


def test_headless_server_chassis_hides_the_row(tmp_path):
    """자리 0개 + 서버 섀시. 숨기는 유일한 자동 경로가 이것과 가상화다."""
    r = physical_access(mode="auto", **_paths(tmp_path, seats="empty", chassis=17))
    assert r["usb_relevant"] is False
    assert r["signals"]["seat"] == "absent" and r["signals"]["chassis_kind"] == "machine_room"


def test_headless_desk_chassis_still_shows_because_signals_disagree(tmp_path):
    """책상에 두는 기계는 모니터를 안 꽂아 뒀을 뿐일 수 있다. 엇갈리면 보여준다."""
    r = physical_access(mode="auto", **_paths(tmp_path, seats="empty", chassis=3))
    assert r["usb_relevant"] is True and "엇갈" in r["reason"]


def test_unreadable_seats_shows_the_row_even_with_server_chassis(tmp_path):
    """이 테스트가 이 기능의 안전장치다.

    디렉터리를 못 읽은 것은 '자리가 없다'가 아니다 (logind 가 없거나 못 읽는 것이다).
    서버 섀시라는 신호가 있어도 1차 신호를 모르면 보안 조작을 감추지 않는다.
    """
    r = physical_access(mode="auto", **_paths(tmp_path, seats="missing", chassis=23))
    assert r["usb_relevant"] is True
    assert r["signals"]["seat"] == "unknown" and "몰라서 감추지는 않아요" in r["reason"]


# --- 섀시 파일이 성하지 않을 때 ---

def test_missing_chassis_file_with_no_seat_shows(tmp_path):
    r = physical_access(mode="auto", **_paths(tmp_path, seats="empty", chassis=None))
    assert r["usb_relevant"] is True
    assert r["signals"]["chassis_kind"] == "unknown" and r["signals"]["chassis_type"] is None


def test_garbage_chassis_value_is_treated_as_unknown(tmp_path):
    r = physical_access(mode="auto", **_paths(tmp_path, seats="empty", chassis="not-a-number"))
    assert r["usb_relevant"] is True and r["signals"]["chassis_type"] is None


def test_unclassified_chassis_number_does_not_hide(tmp_path):
    """1(기타)·2(알 수 없음)처럼 분류하지 않은 번호는 숨기는 근거가 되지 못한다."""
    for code in (1, 2, 33):
        r = physical_access(mode="auto", **_paths(tmp_path, seats="empty", chassis=code, tag=code))
        assert r["usb_relevant"] is True, code


# --- 가상 머신·컨테이너 ---

def test_virtual_machine_without_a_seat_hides_the_row(tmp_path):
    r = physical_access(mode="auto", **_paths(tmp_path, seats="empty", chassis=1, vendor="QEMU"))
    assert r["usb_relevant"] is False and "QEMU" in r["reason"]


def test_container_marker_hides_the_row(tmp_path):
    r = physical_access(mode="auto", **_paths(tmp_path, seats="empty", container="docker"))
    assert r["usb_relevant"] is False and "컨테이너" in r["reason"]


def test_virtual_machine_with_a_seat_still_shows(tmp_path):
    """가상 콘솔이 seat0 으로 잡히는 VM 도 있다. 자리가 있으면 보여준다 (덜 숨기는 쪽)."""
    r = physical_access(mode="auto", **_paths(tmp_path, seats=["seat0"], vendor="VMware, Inc."))
    assert r["usb_relevant"] is True


def test_dmi_strings_are_not_echoed_back(tmp_path):
    """제조사·제품 이름은 호스트 정보다. 화면에 필요한 것은 '가상 머신이다'뿐이다."""
    raw = "QEMU Standard PC i440FX-9999 rack-7"
    r = physical_access(mode="auto", **_paths(tmp_path, seats="empty", vendor=raw))
    assert r["usb_relevant"] is False
    assert raw not in r["reason"] and raw not in str(r["signals"])
    assert r["signals"]["virtualized"] == "QEMU"


# --- 설정이 자동 판정보다 이긴다 ---

def test_always_wins_over_hiding_signals(tmp_path):
    r = physical_access(mode="always", **_paths(tmp_path, seats="empty", chassis=23, vendor="QEMU"))
    assert r["usb_relevant"] is True and r["mode"] == "always" and "설정" in r["reason"]


def test_never_wins_over_a_present_seat(tmp_path):
    r = physical_access(mode="never", **_paths(tmp_path, seats=["seat0"], chassis=3))
    assert r["usb_relevant"] is False and r["mode"] == "never" and "설정" in r["reason"]


def test_override_does_not_pretend_to_have_read_the_signals(tmp_path):
    r = physical_access(mode="never", **_paths(tmp_path, seats=["seat0"]))
    assert r["signals"]["seat"] == "not_checked"


def test_unknown_setting_value_falls_back_to_auto_and_says_so(tmp_path):
    r = physical_access(mode="maybe", **_paths(tmp_path, seats="empty", chassis=23))
    assert r["mode"] == "auto"
    assert "SECDASH_PHYSICAL_ACCESS" in r["reason"]
    # 자동 판정 자체는 그대로 돌아간다
    assert r["usb_relevant"] is False


def test_empty_setting_value_is_auto(tmp_path):
    r = physical_access(mode="", **_paths(tmp_path, seats="empty", chassis=17))
    assert r["mode"] == "auto" and r["usb_relevant"] is False


# --- API ---

def test_api_host_reports_the_decision_and_the_reason():
    """화면은 정책을 다시 계산하지 않는다. 백엔드가 판정과 이유를 함께 말해준다."""
    import app as app_module
    pa = TestClient(app_module.app).get("/api/host", headers=H).json()["physical_access"]
    assert isinstance(pa["usb_relevant"], bool)
    assert pa["mode"] in MODES
    assert isinstance(pa["reason"], str) and pa["reason"].strip()
    assert "seat" in pa["signals"]


def test_default_mode_reads_config():
    """인자를 안 주면 설정에서 읽는다 (기본 auto)."""
    import config
    assert config.PHYSICAL_ACCESS in MODES
    r = physical_access()
    assert isinstance(r["usb_relevant"], bool) and r["mode"] in MODES
