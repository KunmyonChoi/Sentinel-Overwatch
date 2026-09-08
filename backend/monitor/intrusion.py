import time
import re
import ipaddress
import psutil
import logging
from datetime import datetime, timedelta
from database import SessionLocal, Event

# Known cloud provider CIDR ranges — connections to these are file-logged only, not stored in DB
_CLOUD_CIDRS = [
    # Google
    "142.250.0.0/15", "142.251.0.0/16", "172.217.0.0/16",
    "216.239.32.0/19", "74.125.0.0/16", "66.102.0.0/20",
    "209.85.128.0/17",
    # Google Cloud (GCP)
    "34.0.0.0/8",
    # GitHub
    "140.82.112.0/20", "143.55.64.0/20",
    # Microsoft / Azure
    "20.0.0.0/8", "13.64.0.0/11", "13.104.0.0/14",
    "51.0.0.0/8", "52.0.0.0/8", "150.171.0.0/16",
    # AWS (global)
    "3.0.0.0/8", "18.0.0.0/8", "35.0.0.0/8", "54.0.0.0/8",
    "99.77.0.0/16", "99.78.0.0/16",  # CloudFront
    # Cloudflare
    "104.16.0.0/13", "104.24.0.0/14", "198.41.128.0/17", "162.158.0.0/15",
    # Fastly CDN
    "151.101.0.0/16", "146.75.0.0/16",
    # Ubuntu / Canonical
    "185.125.188.0/22",
    # Akamai
    "23.0.0.0/8", "104.64.0.0/10",
]
_CLOUD_NETWORKS = [ipaddress.ip_network(c, strict=False) for c in _CLOUD_CIDRS]

def _is_cloud_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in _CLOUD_NETWORKS)
    except ValueError:
        return False

# Configure Logging
logger = logging.getLogger("intrusion_monitor")

class AuthLogWatcher:
    def __init__(self, log_path="/var/log/auth.log"):
        self.log_path = log_path
        # Fallback for testing
        if not self.check_log_path(log_path):
             self.log_path = "test_auth.log"
        self.running = False

    def check_log_path(self, path):
        try:
            with open(path, 'r') as f:
                pass
            return True
        except:
            return False

    def monitor(self):
        if not self.check_log_path(self.log_path):
            return
        
        self.running = True
        logger.info(f"Starting Auth Log Monitor on {self.log_path}")
        
        with open(self.log_path, 'r') as f:
            # Move to end of file
            f.seek(0, 2)
            
            while self.running:
                line = f.readline()
                if not line:
                    time.sleep(1)
                    continue
                
                self.process_line(line)

    def process_line(self, line):
        # detection keywords
        if "Failed password" in line or "authentication failure" in line:
            self.log_event("INTRUSION_ATTEMPT", "WARNING", "SSH/Auth", line.strip())
            ip_match = re.search(r"from (\d+\.\d+\.\d+\.\d+)", line)
            if ip_match:
                self.handle_failure(ip_match.group(1))

        elif "Invalid user" in line:
            self.log_event("INVALID_USER", "WARNING", "SSH/Auth", line.strip())
            ip_match = re.search(r"from (\d+\.\d+\.\d+\.\d+)", line)
            if ip_match:
                self.handle_failure(ip_match.group(1))

        elif "Accepted password" in line or "Accepted publickey" in line:
            self.log_event("SUCCESSFUL_LOGIN", "INFO", "SSH/Auth", line.strip())

        elif "sudo:" in line and "COMMAND=" in line:
            user_match = re.search(r"sudo:\s+(\S+)", line)
            cmd_match = re.search(r"COMMAND=(.+)$", line)
            user = user_match.group(1) if user_match else "unknown"
            cmd = cmd_match.group(1).strip() if cmd_match else line.strip()
            severity = "WARNING" if "sudo" in cmd.lower() or "/bin/su" in cmd or "/bin/bash" in cmd else "INFO"
            self.log_event("PRIVILEGE_ESCALATION", severity, "SSH/Auth",
                           f"sudo command by {user}: {cmd}")

        elif "session opened for user root" in line or ("su:" in line and "session opened" in line):
            # Skip cron/systemd-initiated root sessions — normal system behavior
            if "CRON[" in line or "systemd[" in line or "pam_unix(cron:" in line:
                return
            by_match = re.search(r"by (\S+)", line)
            by_user = by_match.group(1) if by_match else "unknown"
            if by_user.startswith("root"):
                # Direct root session (not CRON/systemd — already filtered above)
                # Unusual if admin never logs in as root directly
                self.log_event("PRIVILEGE_ESCALATION", "WARNING", "SSH/Auth",
                               f"Direct root session detected (no regular user initiator): {line.strip()}")
            else:
                self.log_event("PRIVILEGE_ESCALATION", "WARNING", "SSH/Auth",
                               f"Root session opened by non-root user {by_user}: {line.strip()}")

    def handle_failure(self, ip):
        db = SessionLocal()
        try:
            window = datetime.utcnow() - timedelta(minutes=30)
            count = db.query(Event).filter(
                Event.source == "SSH/Auth",
                Event.event_type.in_(["INTRUSION_ATTEMPT", "INVALID_USER"]),
                Event.description.contains(ip),
                Event.timestamp >= window,
            ).count()
            if count >= 5:
                self.trigger_ban(ip)
        except Exception as e:
            logger.error(f"Failed to count attempts for {ip}: {e}")
        finally:
            db.close()

    def trigger_ban(self, ip):
        from ban_manager import BanManager
        db = SessionLocal()
        try:
            manager = BanManager(db)
            manager.ban_ip(ip, "Too many failed login attempts (Brute Force)")
        except Exception as e:
            logger.error(f"Failed to ban IP: {e}")
        finally:
            db.close()

    def log_event(self, event_type, severity, source, description):
        db = SessionLocal()
        try:
            event = Event(
                event_type=event_type,
                severity=severity,
                source=source,
                description=description
            )
            db.add(event)
            db.commit()
            logger.info(f"Logged event: {event_type} - {description}")
        except Exception as e:
            logger.error(f"Database error: {e}")
        finally:
            db.close()

class NetworkWatcher:
    KNOWN_PORTS = {22, 80, 443, 53, 123, 631, 8000, 5173}  # includes dev server ports
    # Ports that are never interesting to log as "new listener"
    IGNORE_LISTEN_PORTS = {22, 80, 443, 53, 123, 631, 8000, 5173, 5432, 3306, 6379}
    SCAN_WINDOW = 10       # seconds to accumulate connections per remote IP
    SCAN_THRESHOLD = 5     # distinct local ports hit → port scan suspected

    def __init__(self, interval=15):
        self.interval = interval
        self.running = False
        self.seen_listen_ports: set[int] = set()
        self.seen_remote_ips: set[str] = set()
        # {remote_ip: set of local ports contacted} for scan detection
        self._scan_tracker: dict[str, set[int]] = {}

    def monitor(self):
        self.running = True
        logger.info("Starting Network Monitor")
        # Seed known state silently on startup
        try:
            for conn in psutil.net_connections(kind='inet'):
                if conn.status == 'LISTEN' and conn.laddr:
                    self.seen_listen_ports.add(conn.laddr.port)
                if conn.status == 'ESTABLISHED' and conn.raddr:
                    self.seen_remote_ips.add(conn.raddr.ip)
        except Exception:
            pass
        while self.running:
            self.check_connections()
            time.sleep(self.interval)

    def check_connections(self):
        try:
            connections = psutil.net_connections(kind='inet')
            current_listen: set[int] = set()
            new_scan_tracker: dict[str, set[int]] = {}

            for conn in connections:
                # --- New listening port ---
                if conn.status == 'LISTEN' and conn.laddr:
                    port = conn.laddr.port
                    current_listen.add(port)
                    if port not in self.seen_listen_ports and port not in self.IGNORE_LISTEN_PORTS:
                        self.seen_listen_ports.add(port)
                        self.log_event(
                            "NETWORK_ANOMALY", "WARNING", "NetworkWatcher",
                            f"New listening port detected: {port}. Verify this service is expected."
                        )

                # --- Established external connections ---
                if conn.status == 'ESTABLISHED' and conn.raddr:
                    rip = conn.raddr.ip
                    lport = conn.laddr.port if conn.laddr else 0

                    # Skip loopback, private, IPv6-mapped localhost
                    clean_ip = rip.replace('::ffff:', '') if rip.startswith('::ffff:') else rip
                    if clean_ip in ('127.0.0.1', '::1') or clean_ip.startswith(('192.168.', '10.', '172.16.', '172.17.', '172.18.', '172.19.', '172.2', '172.30.', '172.31.')):
                        continue

                    # New external IP seen
                    if rip not in self.seen_remote_ips:
                        self.seen_remote_ips.add(rip)
                        desc = f"New external connection established: {rip}:{conn.raddr.port}"
                        if _is_cloud_ip(rip):
                            # Known cloud provider — file log only, no DB noise
                            logger.info(f"[cloud] {desc}")
                        else:
                            self.log_event("NETWORK_CONN", "INFO", "NetworkWatcher", desc)

                    # Port-scan: track which of OUR SERVICE ports (non-ephemeral) this remote IP hits
                    # Ephemeral ports (>= 32768) are outbound source ports — not scan targets
                    if lport < 32768:
                        if rip not in new_scan_tracker:
                            new_scan_tracker[rip] = set()
                        new_scan_tracker[rip].add(lport)

            # Port-scan heuristic: remote IP contacted multiple of our service ports
            for rip, ports in new_scan_tracker.items():
                prev_ports = self._scan_tracker.get(rip, set())
                combined = prev_ports | ports
                if len(combined) >= self.SCAN_THRESHOLD and len(prev_ports) < self.SCAN_THRESHOLD:
                    self.log_event(
                        "PORT_SCAN", "WARNING", "NetworkWatcher",
                        f"Possible port scan from {rip}: contacted {len(combined)} local service ports {sorted(combined)}."
                    )
            self._scan_tracker = new_scan_tracker

            # Remove stale listen ports from tracking (port closed)
            self.seen_listen_ports &= current_listen | self.IGNORE_LISTEN_PORTS

        except Exception as e:
            logger.error(f"Network check error: {e}")

    def log_event(self, event_type, severity, source, description):
        logger.info(description)
        db = SessionLocal()
        try:
            db.add(Event(event_type=event_type, severity=severity, source=source, description=description))
            db.commit()
        except Exception as e:
            logger.error(f"DB error: {e}")
        finally:
            db.close()
