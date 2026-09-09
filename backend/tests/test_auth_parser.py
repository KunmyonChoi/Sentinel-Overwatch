from monitor.intrusion import parse_line, is_private_ip, is_cloud_ip


def test_failed_password_invalid_user():
    p = parse_line("Sep  8 14:20:01 host sshd[1234]: Failed password for invalid user hacker from 192.168.1.200 port 4444 ssh2")
    assert p["kind"] == "invalid_user" and p["user"] == "hacker" and p["ip"] == "192.168.1.200"


def test_failed_password_existing_user_ipv6():
    p = parse_line("Sep  8 14:20:01 host sshd[1234]: Failed password for root from 2001:db8::1 port 4444 ssh2")
    assert p["kind"] == "auth_failure" and p["user"] == "root" and p["ip"] == "2001:db8::1"


def test_accepted_publickey_with_fingerprint():
    p = parse_line("Sep  8 14:20:01 host sshd[1234]: Accepted publickey for kunmyon from 10.0.0.5 port 52222 ssh2: ED25519 SHA256:abc123")
    assert p["kind"] == "auth_success" and p["method"] == "publickey" and p["key"] == "ED25519 SHA256:abc123"


def test_iso_timestamp_and_sshd_session():
    p = parse_line("2026-09-08T14:20:01.123456+09:00 host sshd-session[77]: Accepted password for bob from 1.2.3.4 port 1 ssh2")
    assert p and p["kind"] == "auth_success" and p["user"] == "bob"


def test_sudo_command_and_failure():
    p = parse_line("Sep  8 14:20:01 host sudo:  kunmyon : TTY=pts/0 ; PWD=/home/kunmyon ; USER=root ; COMMAND=/usr/bin/apt update")
    assert p["kind"] == "sudo_command" and p["user"] == "kunmyon" and p["command"] == "/usr/bin/apt update"
    f = parse_line("Sep  8 14:20:01 host sudo:  bob : 3 incorrect password attempts ; TTY=pts/0 ; PWD=/ ; USER=root ; COMMAND=/bin/ls")
    assert f["kind"] == "sudo_failure" and f["user"] == "bob" and "incorrect password" in f["reason"]
    n = parse_line("Sep  8 14:20:01 host sudo:  eve : user NOT in sudoers ; TTY=pts/0 ; PWD=/ ; USER=root ; COMMAND=/bin/bash")
    assert n["kind"] == "sudo_failure"


def test_account_changes():
    p = parse_line("Sep  8 14:20:01 host useradd[123]: new user: name=test, UID=1002, GID=1002, home=/home/test, shell=/bin/bash, from=/dev/pts/0")
    assert p["kind"] == "account_change" and p["user"] == "test"
    g = parse_line("Sep  8 14:20:01 host usermod[123]: add 'test' to group 'sudo'")
    assert g["kind"] == "account_change" and g["group"] == "sudo" and g["direction"] == "add"


def test_group_removal_is_parsed():
    """제거도 봐야 한다. 되돌림인지 정리인지는 사람이 판단하고, 사실은 남긴다."""
    r = parse_line("Sep  8 14:20:01 host usermod[123]: remove 'test' from group 'docker'")
    assert r["kind"] == "account_change" and r["group"] == "docker" and r["direction"] == "remove"


def test_gpasswd_is_watched():
    """gpasswd 는 usermod 와 다른 문장을 남긴다. 빠뜨리면 권한 그룹 변경 주체를 놓친다."""
    a = parse_line("Sep  8 14:20:01 host gpasswd[123]: user mallory added by root to group docker")
    assert a["kind"] == "account_change" and a["user"] == "mallory" and a["group"] == "docker"
    assert a["direction"] == "add"
    d = parse_line("Sep  8 14:20:01 host gpasswd[123]: user bob removed by root from group docker")
    assert d["kind"] == "account_change" and d["user"] == "bob" and d["group"] == "docker"
    assert d["direction"] == "remove"


def test_groupdel_is_parsed():
    g = parse_line("Sep  8 14:20:01 host groupdel[123]: group 'legacy' removed from /etc/group")
    assert g["kind"] == "account_change" and g["group"] == "legacy"


def test_root_session_via_su_and_cron_ignored():
    s = parse_line("Sep  8 14:20:01 host su: (to root) kunmyon on pts/0")
    assert s["kind"] == "root_session" and s["by"] == "kunmyon"
    c = parse_line("Sep  8 14:20:01 host CRON[123]: pam_unix(cron:session): session opened for user root(uid=0) by root(uid=0)")
    assert c is None


def test_simulation_flag_and_unknown_lines():
    p = parse_line("Jan 15 10:25:10 server sshd[999]: Failed password for invalid user hacker from 192.168.1.200 port 4444 ssh2 [SIMULATION]")
    assert p["simulation"] is True
    assert parse_line("garbage line") is None
    assert parse_line("Sep  8 14:20:01 host sshd[1]: Connection closed by 1.2.3.4 port 5 [preauth]") is None


def test_private_ip_check_is_exact():
    assert is_private_ip("172.20.1.1")
    assert not is_private_ip("172.2.1.1")     # 이전 접두사 검사 버그
    assert is_private_ip("::1") and is_private_ip("::ffff:10.0.0.1")
    assert not is_private_ip("8.8.8.8")


def test_cloud_ip_no_longer_hides_whole_slash8():
    assert is_cloud_ip("140.82.112.4")        # GitHub
    assert not is_cloud_ip("52.10.10.10")     # 이전엔 52.0.0.0/8 전체가 숨겨졌다


def test_sudo_without_tty_and_uid_only_session():
    p = parse_line("Sep  8 14:20:01 host sudo:  secdash : PWD=/opt/secdash/backend ; USER=root ; COMMAND=/usr/bin/fail2ban-client status sshd")
    assert p["kind"] == "sudo_command" and p["user"] == "secdash" and p["command"].startswith("/usr/bin/fail2ban-client")
    s = parse_line("Sep  8 14:20:01 host sudo: pam_unix(sudo:session): session opened for user root(uid=0) by (uid=0)")
    assert s["kind"] == "root_session" and s["by"] == "root"
    s2 = parse_line("Sep  8 14:20:01 host sudo: pam_unix(sudo:session): session opened for user root(uid=0) by kunmyon(uid=1001)")
    assert s2["by"] == "kunmyon"


def test_interactive_shell_detection():
    from monitor.intrusion import is_interactive_shell
    assert is_interactive_shell("/bin/bash")
    assert is_interactive_shell("/usr/bin/bash -i")
    assert is_interactive_shell("/bin/su -")
    assert not is_interactive_shell("/usr/bin/sh -c 'T=$(cat x); curl -s http://127.0.0.1:8000'")
    assert not is_interactive_shell("/usr/bin/apt update")
