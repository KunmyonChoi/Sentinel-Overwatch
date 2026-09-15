"""
탐지 파이프라인 점검용 시뮬레이터.

- 포트 스캔: SECDASH_UFW_LOG (기본 backend/test_ufw.log) 에 [SIMULATION] 태그가 붙은 [UFW BLOCK] 줄을 기록
  (내부망 주소라 '내부망 스캔' 경고, 곧이어 같은 주소의 SSH 시도로 '스캔 뒤 로그인 시도' 경고가 난다)
- SSH 브루트포스: SECDASH_AUTH_LOG (기본 backend/test_auth.log) 에 [SIMULATION] 태그가 붙은 줄을 기록
- 도구 실행: sleep 바이너리를 nmap_sim 이름으로 복사해 실행 (ProcessAudit 가 시뮬레이션으로 태그)
시뮬레이션 이벤트/알림은 TEST DATA 로 표시되고 DEFCON/Slack/fail2ban 에 영향을 주지 않는다.

백엔드를 테스트 로그로 실행해야 한다:
  cd backend && SECDASH_AUTH_LOG=./test_auth.log SECDASH_UFW_LOG=./test_ufw.log venv/bin/python app.py
"""
import os
import shutil
import subprocess
import time
from datetime import datetime

LOG = os.environ.get("SECDASH_AUTH_LOG", os.path.join("backend", "test_auth.log"))
UFW_LOG = os.environ.get("SECDASH_UFW_LOG", os.path.join("backend", "test_ufw.log"))


def simulate_scan():
    print(f">>> port scan (ufw blocked) → {UFW_LOG}")
    with open(UFW_LOG, "a") as f:
        for port in (21, 23, 25, 110, 135, 139, 445, 1433, 3306, 3389, 5900, 8080):
            ts = datetime.now().astimezone().isoformat()
            f.write(f"{ts} server kernel: [UFW BLOCK] IN=eth0 OUT= MAC=52:54:00:12:34:56 SRC=192.168.1.200 "
                    f"DST=192.168.1.10 LEN=44 TOS=0x00 PREC=0x00 TTL=64 ID=4242 PROTO=TCP SPT=4444 DPT={port} "
                    f"WINDOW=1024 RES=0x00 SYN URGP=0 [SIMULATION]\n")
    # FirewallLogWatcher 가 스캔으로 판정한 뒤에 SSH 시도가 오도록 잠시 기다린다
    time.sleep(3)


def simulate_intrusion():
    print(f">>> SSH brute force → {LOG}")
    ts = datetime.now().strftime("%b %d %H:%M:%S")
    with open(LOG, "a") as f:
        for i in range(6):
            f.write(f"{ts} server sshd[999]: Failed password for invalid user hacker from 192.168.1.200 port 4444 ssh2 [SIMULATION]\n")
            f.flush()
            time.sleep(0.3)
        # 실패 후 성공 (CRITICAL 시나리오)
        f.write(f"{ts} server sshd[999]: Accepted password for hacker from 192.168.1.200 port 4444 ssh2 [SIMULATION]\n")
        f.write(f"{ts} server sudo:  hacker : TTY=pts/9 ; PWD=/ ; USER=root ; COMMAND=/bin/bash [SIMULATION]\n")


def simulate_tools():
    print(">>> tool processes (nmap_sim, tcpdump_sim)")
    procs = []
    for tool in ("nmap", "tcpdump"):
        path = f"./{tool}_sim"
        shutil.copy("/bin/sleep", path)
        os.chmod(path, 0o755)
        p = subprocess.Popen([path, "45"], start_new_session=True)
        procs.append((path, p))
        print(f"   spawned {path} (PID {p.pid})")
    return procs


if __name__ == "__main__":
    simulate_scan()
    simulate_intrusion()
    procs = simulate_tools()
    print("Simulation running. Check the dashboard (TEST DATA badges). Cleaning up in 40s...")
    time.sleep(40)
    for path, p in procs:
        p.terminate()
        try:
            os.remove(path)
        except OSError:
            pass
    print("Cleanup done.")
