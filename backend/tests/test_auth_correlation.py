import database
from database import Alert, BlockedIP, Event
from monitor.intrusion import AuthLogWatcher


class FakeBanManager:
    calls = []

    def __init__(self, db):
        self.db = db

    def ban_ip(self, ip, reason, is_simulation=False):
        FakeBanManager.calls.append((ip, is_simulation))
        return {"status": "ACTIVE", "changed": True}


def make_watcher():
    FakeBanManager.calls = []
    w = AuthLogWatcher(log_path="/nonexistent/auth.log", ban_manager_factory=FakeBanManager)
    w.threshold = 5
    return w


def fail_line(ip, user="hacker", n=10):
    return f"Sep  8 14:20:{n:02d} host sshd[1]: Failed password for invalid user {user} from {ip} port 4444 ssh2"


def test_brute_force_alert_and_ban_at_threshold(db):
    w = make_watcher()
    for i in range(5):
        w.process_line(fail_line("203.0.113.9", n=i))
    alerts = db.query(Alert).filter(Alert.rule == "brute_force").all()
    assert len(alerts) == 1 and alerts[0].severity == "WARNING" and "203.0.113.9" in alerts[0].title
    assert FakeBanManager.calls == [("203.0.113.9", False)]
    assert db.query(Event).filter(Event.event_type == "INVALID_USER").count() == 5
    # 추가 실패는 새 알림이 아니라 count 증가
    w.process_line(fail_line("203.0.113.9", n=6))
    db.expire_all()
    a = db.query(Alert).filter(Alert.rule == "brute_force").one()
    assert a.count == 2 and a.details_dict()["count"] == 6


def test_ip_counting_is_exact_not_substring(db):
    w = make_watcher()
    for i in range(3):
        w.process_line(fail_line("10.0.0.1", n=i))
    for i in range(3):
        w.process_line(fail_line("10.0.0.11", n=i))
    assert db.query(Alert).count() == 0


def test_login_after_failures_is_critical(db):
    w = make_watcher()
    for i in range(2):
        w.process_line(fail_line("198.51.100.7", user="bob", n=i))
    w.process_line("Sep  8 14:21:00 host sshd[1]: Accepted password for bob from 198.51.100.7 port 4444 ssh2")
    crit = db.query(Alert).filter(Alert.rule == "login_after_failures").one()
    assert crit.severity == "CRITICAL" and "bob" in crit.title_ko


def test_new_public_ip_alert_only_once_and_private_silent(db):
    w = make_watcher()
    line = "Sep  8 14:21:00 host sshd[1]: Accepted publickey for alice from 45.33.32.156 port 4444 ssh2: ED25519 SHA256:x"
    w.process_line(line)
    w.process_line(line)
    assert db.query(Alert).filter(Alert.rule == "new_login_ip").count() == 1
    w.process_line("Sep  8 14:21:00 host sshd[1]: Accepted publickey for alice from 192.168.0.5 port 4444 ssh2")
    assert db.query(Alert).filter(Alert.rule == "new_login_ip").count() == 1
    row = db.query(database.KnownLoginIP).filter_by(ip_address="45.33.32.156").one()
    assert row.login_count == 2


def test_root_login_and_privileged_group_change(db):
    w = make_watcher()
    w.process_line("Sep  8 14:21:00 host sshd[1]: Accepted password for root from 198.51.100.9 port 4444 ssh2")
    assert db.query(Alert).filter(Alert.rule == "root_ssh_login").count() == 1
    w.process_line("Sep  8 14:20:01 host usermod[123]: add 'mallory' to group 'sudo'")
    a = db.query(Alert).filter(Alert.rule == "account_change").one()
    assert a.severity == "CRITICAL"


def test_simulation_lines_do_not_touch_real_ban_or_defcon(db):
    import alerts
    w = make_watcher()
    for i in range(5):
        w.process_line(fail_line("192.168.1.200", n=i) + " [SIMULATION]")
    assert FakeBanManager.calls == [("192.168.1.200", True)]
    a = db.query(Alert).one()
    assert a.is_simulation
    assert alerts.compute_defcon(db)["status"] == "SAFE"


def test_unreadable_log_sets_health_down_without_fallback(tmp_path):
    w = AuthLogWatcher(log_path=str(tmp_path / "missing.log"))
    w.setup()
    assert w.health == "down" and "없음" in w.health_reason
    assert w.log_path.endswith("missing.log")   # test_auth.log 로 대체하지 않는다


def test_dashboard_own_sudo_is_suppressed(db, monkeypatch):
    import config
    monkeypatch.setattr(config, "SELF_USER", "secdash")
    w = make_watcher()
    w.process_line("Sep  8 14:20:01 host sudo:  secdash : PWD=/opt/secdash/backend ; USER=root ; COMMAND=/usr/bin/fail2ban-client status sshd")
    w.process_line("Sep  8 14:20:01 host sudo: pam_unix(sudo:session): session opened for user root(uid=0) by secdash(uid=997)")
    assert db.query(Event).count() == 0
    # 다른 계정의 같은 명령은 기록된다
    w.process_line("Sep  8 14:20:01 host sudo:  kunmyon : TTY=pts/0 ; PWD=/ ; USER=root ; COMMAND=/usr/bin/fail2ban-client status sshd")
    assert db.query(Event).filter(Event.event_type == "SUDO_COMMAND").count() == 1
    # 대시보드 계정이라도 fail2ban-client 가 아닌 명령은 기록된다
    w.process_line("Sep  8 14:20:01 host sudo:  secdash : PWD=/ ; USER=root ; COMMAND=/bin/bash")
    assert db.query(Event).filter(Event.event_type == "SUDO_COMMAND").count() == 2
