"""
탐지 파이프라인 점검용 시뮬레이터.

- SSH 브루트포스: SECDASH_AUTH_LOG (기본 backend/test_auth.log) 에 [SIMULATION] 태그가 붙은 줄을 기록
- 도구 실행: sleep 바이너리를 nmap_sim 이름으로 복사해 실행 (ProcessAudit 가 시뮬레이션으로 태그)
시뮬레이션 이벤트/알림은 TEST DATA 로 표시되고 DEFCON/Slack/fail2ban 에 영향을 주지 않는다.

백엔드를 테스트 로그로 실행해야 한다:
  cd backend && SECDASH_AUTH_LOG=./test_auth.log venv/bin/python app.py
"""
import os
import shutil
import subprocess
import time
from datetime import datetime

LOG = os.environ.get("SECDASH_AUTH_LOG", os.path.join("backend", "test_auth.log"))


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
