import datetime

from integrations.accounts import list_accounts


def test_account_states(tmp_path):
    passwd = tmp_path / "passwd"
    passwd.write_text("root:x:0:0:root:/root:/bin/bash\nubuntu:x:1000:1000:Ubuntu:/home/ubuntu:/bin/bash\nkunmyon:x:1001:1001:K:/home/kunmyon:/bin/bash\nslackbot:x:1003:1003::/home/slackbot:/bin/bash\nsftpshare:x:1004:1004::/home/sftpshare:/usr/sbin/nologin\nsecdash:x:997:984::/opt/secdash:/usr/sbin/nologin\n")
    today = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)).days
    shadow = tmp_path / "shadow"
    shadow.write_text(f"root:*:19000:0:99999:7:::\nubuntu:!$6$abc:19000:0:365:14::1:\nkunmyon:$6$abc:19000:0:365:14:::\nslackbot:$6$abc:19000:0:99999:7::{today + 30}:\nsftpshare:!:19000:0:99999:7:::\n")
    ll = {"ubuntu": {"when": "2025-07-09T09:06:25+09:00", "host": "203.236.8.219"}, "kunmyon": {"when": "2026-06-19T23:32:45+09:00", "host": "192.168.50.3"}, "slackbot": {"when": None, "host": None}}
    res = list_accounts(str(passwd), str(shadow), ll)
    assert res["shadow_readable"]
    by = {a["name"]: a for a in res["accounts"]}
    assert "secdash" not in by                       # 시스템 계정 제외
    assert by["ubuntu"]["state"] == "locked" and by["ubuntu"]["expired"] and by["ubuntu"]["state_ko"] == "잠김 (만료)"
    assert by["ubuntu"]["last_login_host"] == "203.236.8.219"
    assert by["kunmyon"]["state"] == "active" and by["kunmyon"]["password_max_days"] == 365
    assert by["slackbot"]["state"] == "active" and by["slackbot"]["last_login"] is None   # 미래 만료는 아직 활성
    assert by["sftpshare"]["state"] == "disabled"
    assert by["root"]["state"] == "locked" and by["ubuntu"]["commands"]["unlock"] == "sudo usermod -U -e '' ubuntu"
    assert [a["name"] for a in res["accounts"]][0] == "root"


def test_unreadable_shadow_is_reported(tmp_path):
    passwd = tmp_path / "passwd"; passwd.write_text("kunmyon:x:1001:1001::/home/k:/bin/bash\n")
    res = list_accounts(str(passwd), str(tmp_path / "missing"), {})
    assert res["shadow_readable"] is False and res["accounts"][0]["state"] == "unknown"
