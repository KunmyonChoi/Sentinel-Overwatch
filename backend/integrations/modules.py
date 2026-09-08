"""커널 모듈 정책 (usb-storage 차단 등) 상태 판정. modprobe.d 설정과 실제 로드 상태를 함께 본다."""
import glob
import os
import re

MODPROBE_DIR = "/etc/modprobe.d"
SYS_MODULE_DIR = "/sys/module"

TEMP_UNBLOCK_CMD = "sudo modprobe --ignore-install usb-storage"
REBLOCK_CMD = "sudo rmmod usb-storage"
PERMANENT_UNBLOCK_CMD = "sudo sed -i '/usb-storage/d' /etc/modprobe.d/90-secdash-hardening.conf"
PERMANENT_BLOCK_CMD = "sudo deploy/harden.sh --apply --disable-usb-storage"


def _blocked_in_config(module: str, modprobe_dir: str) -> tuple[bool, str]:
    """(차단 설정 존재 여부, 근거 파일)"""
    pattern = re.compile(rf"^\s*(install\s+{re.escape(module)}\s+/bin/(false|true)|blacklist\s+{re.escape(module)})\b")
    for path in sorted(glob.glob(os.path.join(modprobe_dir, "*.conf"))):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if pattern.match(line):
                        return True, path
        except OSError:
            continue
    return False, ""


def _loaded(module: str, sys_module_dir: str) -> bool:
    return os.path.isdir(os.path.join(sys_module_dir, module.replace("-", "_")))


def usb_storage_status(modprobe_dir: str = MODPROBE_DIR, sys_module_dir: str = SYS_MODULE_DIR) -> dict:
    blocked, source = _blocked_in_config("usb-storage", modprobe_dir)
    loaded = _loaded("usb-storage", sys_module_dir)
    if blocked and not loaded:
        state, state_ko = "blocked", "차단 중"
    elif blocked and loaded:
        state, state_ko = "temporarily_unblocked", "일시 해제됨 (재부팅 시 다시 차단)"
    elif loaded:
        state, state_ko = "allowed_loaded", "허용 (모듈 로드됨)"
    else:
        state, state_ko = "allowed", "허용 (차단 설정 없음)"
    return {
        "state": state,
        "state_ko": state_ko,
        "blocked_by_config": blocked,
        "config_file": source,
        "module_loaded": loaded,
        "commands": {
            "temp_unblock": TEMP_UNBLOCK_CMD,
            "reblock": REBLOCK_CMD,
            "permanent_unblock": PERMANENT_UNBLOCK_CMD,
            "permanent_block": PERMANENT_BLOCK_CMD,
        },
    }


def blocked_modules(modprobe_dir: str = MODPROBE_DIR) -> list[str]:
    """secdash 정책 파일이 차단하는 모듈 목록"""
    out: set[str] = set()
    for path in glob.glob(os.path.join(modprobe_dir, "*secdash*.conf")):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    m = re.match(r"^\s*(?:install|blacklist)\s+(\S+)", line)
                    if m:
                        out.add(m.group(1))
        except OSError:
            continue
    return sorted(out)
