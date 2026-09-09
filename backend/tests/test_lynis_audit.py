import os
import time

from database import Alert, Event
from monitor.audit import AuditMonitor, parse_record
from monitor.lynis import LynisMonitor, parse_report

REPORT_V1 = """# Lynis Report
report_datetime_start=2026-09-09 04:15:01
lynis_version=3.0.9
hardening_index=64
warning[]=KRNL-5830|Reboot of system is most likely needed|-|-|
suggestion[]=SSH-7408|Consider hardening SSH configuration|AllowTcpForwarding (set YES to NO)|-|
suggestion[]=BOOT-5264|Consider hardening system services|Run systemd-analyze security|-|
"""
REPORT_V2 = """# Lynis Report
report_datetime_start=2026-09-10 04:15:01
lynis_version=3.0.9
hardening_index=58
warning[]=AUTH-9328|Default umask in /etc/login.defs could be more strict like 027|-|-|
suggestion[]=SSH-7408|Consider hardening SSH configuration|AllowTcpForwarding (set YES to NO)|-|
"""


def test_parse_lynis_report():
    d = parse_report(REPORT_V1)
    assert d["hardening_index"] == 64 and len(d["warnings"]) == 1 and len(d["suggestions"]) == 2
    assert d["warnings"][0]["id"] == "KRNL-5830" and d["suggestions"][0]["details"].startswith("AllowTcpForwarding")


def test_lynis_diff_alerts(db, tmp_path):
    rep = tmp_path / "lynis-report.dat"
    cron = tmp_path / "cron"
    cron.write_text("x")
    rep.write_text(REPORT_V1)
    m = LynisMonitor(report_path=str(rep), cron_path=str(cron))
    m.setup()
    # 첫 실행: 경고 1건 알림, 지수 하락 알림은 없음
    assert db.query(Alert).filter(Alert.rule == "lynis_warning").count() == 1
    assert db.query(Alert).filter(Alert.rule == "lynis_index_drop").count() == 0
    assert db.query(Event).filter(Event.event_type == "LYNIS_AUDIT").count() == 1
    # 두 번째 실행: 옛 경고 자동 해결, 새 경고 알림, 지수 64→58 하락 알림
    time.sleep(0.01)
    rep.write_text(REPORT_V2)
    os.utime(rep, (time.time() + 5, time.time() + 5))
    m.tick()
    db.expire_all()
    rules = {(a.rule, a.details_dict().get("test_id")): a.status for a in db.query(Alert).all()}
    assert rules[("lynis_warning", "KRNL-5830")] == "RESOLVED"
    assert rules[("lynis_warning", "AUTH-9328")] == "OPEN"
    assert rules[("lynis_index_drop", None)] == "OPEN"
    # 재시작 후 같은 보고서는 다시 알리지 않는다
    m2 = LynisMonitor(report_path=str(rep), cron_path=str(cron))
    m2.setup()
    assert db.query(Alert).filter(Alert.rule == "lynis_warning").count() == 2
    assert m2.latest["hardening_index"] == 58


def test_audit_record_parsing_hex():
    r = parse_record('type=EXECVE msg=audit(1725800000.123:4567): argc=3 a0="nmap" a1="-sS" a2=31302E302E302E31')
    assert r["type"] == "EXECVE" and r["serial"] == 4567 and r["a2"] == "10.0.0.1"
    p = parse_record('type=PROCTITLE msg=audit(1725800000.123:4567): proctitle=6E6D6170002D7353')
    assert p["proctitle"] == "nmap -sS"
    assert parse_record("garbage") is None


def _feed(m, lines):
    for l in lines:
        m._ingest(l)
    for ev in list(m._pending.values()):
        m._handle(ev)
    m._pending.clear()


def test_audit_exec_tool_and_write_and_module(db):
    m = AuditMonitor(log_path="/nonexistent", rules_path="/nonexistent")
    _feed(m, [
        'type=SYSCALL msg=audit(1725800000.100:10): arch=c000003e syscall=59 success=yes exit=0 ppid=100 pid=200 auid=1001 uid=1001 comm="nmap" exe="/usr/bin/nmap" key="secdash_exec"',
        'type=EXECVE msg=audit(1725800000.100:10): argc=2 a0="nmap" a1="10.0.0.1"',
        'type=CWD msg=audit(1725800000.100:10): cwd="/home/bob"',
        'type=SYSCALL msg=audit(1725800000.200:11): arch=c000003e syscall=257 success=yes exit=3 ppid=1 pid=300 auid=1001 uid=0 comm="vi" exe="/usr/bin/vim.basic" key="secdash_sudo"',
        'type=PATH msg=audit(1725800000.200:11): item=0 name="/etc/sudoers.d/" nametype=PARENT',
        'type=PATH msg=audit(1725800000.200:11): item=1 name="/etc/sudoers.d/evil" nametype=CREATE',
        'type=SYSCALL msg=audit(1725800000.300:12): arch=c000003e syscall=313 success=yes exit=0 ppid=1 pid=400 auid=1001 uid=0 comm="insmod" exe="/usr/sbin/insmod" key="secdash_modules"',
        'type=PROCTITLE msg=audit(1725800000.300:12): proctitle=696E736D6F64002F746D702F782E6B6F',
        'type=SYSCALL msg=audit(1725800000.400:13): arch=c000003e syscall=257 success=yes exit=3 ppid=1 pid=500 auid=4294967295 uid=0 comm="tee" exe="/usr/bin/tee" key="secdash_persist"',
        'type=PATH msg=audit(1725800000.400:13): item=0 name="/etc/ld.so.preload" nametype=CREATE',
    ])
    ev = {e.event_type: e for e in db.query(Event).all()}
    assert ev["PROCESS_TOOL"].details_dict()["tool"] == "nmap" and ev["PROCESS_TOOL"].details_dict()["command"] == "nmap 10.0.0.1"
    assert ev["PROCESS_TOOL"].details_dict()["user"] not in ("", None) and "\x10" not in ev["PROCESS_TOOL"].description_ko
    w = db.query(Event).filter(Event.event_type == "AUDIT_WRITE").all()
    assert any("/etc/sudoers.d/evil" in x.details_dict()["paths"] for x in w)
    assert ev["KERNEL_MODULE"].details_dict()["command"] == "insmod /tmp/x.ko"
    rules = {a.rule: a for a in db.query(Alert).all()}
    assert rules["security_tool"].fingerprint == "security_tool:nmap:" + rules["security_tool"].details_dict()["user"]
    assert rules["kernel_module"].severity == "WARNING"
    assert rules["ld_preload_write"].severity == "CRITICAL" and rules["ld_preload_write"].details_dict()["user"].startswith("시스템(자동")


def test_audit_unavailable_is_degraded_not_silent():
    m = AuditMonitor(log_path="/nonexistent/audit.log", rules_path="/nonexistent/rules")
    m.setup()
    assert m.health == "degraded" and "30초 샘플링" in m.health_reason


def test_audit_numeric_fields_are_not_hex_decoded():
    r = parse_record('type=SYSCALL msg=audit(1725800000.100:10): arch=c000003e syscall=59 a0=7ffd1234 auid=1001 uid=1001 comm="bash" exe="/usr/bin/bash" key="secdash_exec"')
    assert r["auid"] == "1001" and r["a0"] == "7ffd1234" and r["arch"] == "c000003e"
    e = parse_record('type=EXECVE msg=audit(1725800000.100:10): argc=1 a0=6E6D6170')
    assert e["a0"] == "nmap"


def test_empty_report_from_aborted_audit_does_not_alert(db, tmp_path):
    rep = tmp_path / "lynis-report.dat"; cron = tmp_path / "cron"; cron.write_text("x")
    rep.write_text(REPORT_V1)
    m = LynisMonitor(report_path=str(rep), cron_path=str(cron)); m.setup()
    time.sleep(0.01)
    rep.write_text("# Lynis Report\nreport_datetime_start=2026-09-11 04:15:01\n")   # 중단된 감사
    os.utime(rep, (time.time() + 5, time.time() + 5))
    m.tick()
    assert m.health == "degraded" and "비어" in m.health_reason
    assert db.query(Alert).filter(Alert.rule == "lynis_index_drop").count() == 0
    assert m.latest["hardening_index"] == 64   # 마지막 정상 결과 유지


def test_brief_markdown_and_skipped_profile(tmp_path):
    from monitor.lynis import brief_markdown, read_skipped
    prf = tmp_path / "custom.prf"
    prf.write_text("# secdash profile\n\n# FINT-4350 file integrity -> IntegrityMonitor\nskip-test=FINT-4350\n# HRDN-7222 compilers -> dev server\nskip-test=HRDN-7222\n")
    skipped = read_skipped(str(prf))
    assert skipped == [{"id": "FINT-4350", "reason": "FINT-4350 file integrity -> IntegrityMonitor"}, {"id": "HRDN-7222", "reason": "HRDN-7222 compilers -> dev server"}]
    latest = parse_report(REPORT_V1)
    from monitor.lynis import summarize
    md = brief_markdown(summarize(latest), skipped, {"hostname": "srv1", "os": "Linux", "kernel": "7.0", "role": "GPU 개발 서버"})
    assert "서버 역할: GPU 개발 서버" in md and "**KRNL-5830**" in md and "**SSH-7408**" in md and "AllowTcpForwarding" in md
    assert "FINT-4350" in md and "## 요청" in md
    one = brief_markdown(summarize(latest), skipped, {"hostname": "srv1"}, item_id="SSH-7408")
    assert "SSH-7408" in one and "KRNL-5830" not in one and "건너뛰는" not in one
