import time
import os
import subprocess

def simulate_intrusion():
    print(">>> Simulating SSH Brute Force...")
    with open("backend/test_auth.log", "a") as f:
        print("   -> Hammering 192.168.1.200 (5 attempts)...")
        for i in range(6):
            line = f"Jan 15 10:25:{10+i} server sshd[999]: Failed password for invalid user hacker from 192.168.1.200 port 4444 ssh2 [SIMULATION]\n"
            f.write(line)
            f.flush()
            time.sleep(0.5)

def simulate_malware():
    print(">>> Simulating Malware Process (nmap)...")
    # Use subprocess with explicit process name so psutil captures name='nmap_sim', not 'bash'
    # Also write a wrapper that tags itself for simulation identification
    procs = []
    for tool in ("nmap", "wireshark"):
        os.system(f"cp /bin/sleep ./{tool}_sim")
        p = subprocess.Popen([f"./{tool}_sim", "15"], start_new_session=True)
        procs.append((tool, p))
        print(f"   -> Spawned {tool}_sim (PID: {p.pid})")
    return procs

if __name__ == "__main__":
    print("Starting Simulation...")
    simulate_intrusion()
    procs = simulate_malware()
    print("Simulation Complete. Check Dashboard.")
    time.sleep(12)
    # Cleanup
    for tool, p in procs:
        p.terminate()
        os.system(f"rm -f ./{tool}_sim")
    print("Cleanup done.")
