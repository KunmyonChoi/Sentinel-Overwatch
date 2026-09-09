"""
Lynis 감사 결과 연동.

Lynis 는 데몬이 아니라 크론으로 하루 한 번 실행되는 일회성 감사 도구다 (deploy/cron-secdash-lynis).
이 모니터는 /var/log/lynis-report.dat 가 갱신되면 읽어서 이전 실행과 비교한다.
  - 새로 생긴 경고(warning)      → WARNING 알림 (해결 방법 포함)
  - 사라진 경고                   → 자동 해결
  - 강화 지수(hardening index) 하락 → WARNING 알림
  - 제안(suggestion) 은 알림이 아니라 '강화 작업 목록' 으로만 노출한다 (처음엔 수십 개가 나오는 게 정상)
"""
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timedelta

from alerts import auto_resolve, raise_alert
from database import IntegrityBaseline, SessionLocal, utcnow
from monitor.base import BaseMonitor

REPORT_PATH = "/var/log/lynis-report.dat"
CRON_PATH = "/etc/cron.d/secdash-lynis"
INDEX_DROP_THRESHOLD = 3
STALE_DAYS = 2


def parse_report(text: str) -> dict:
    """lynis-report.dat → dict. key[]= 는 리스트, warning/suggestion 은 구조화."""
    data: dict = {"warnings": [], "suggestions": []}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in ("warning[]", "suggestion[]"):
            parts = value.split("|")
            item = {"id": parts[0], "message": parts[1] if len(parts) > 1 else "",
                    "details": parts[2] if len(parts) > 2 and parts[2] != "-" else "",
                    "solution": parts[3] if len(parts) > 3 and parts[3] != "-" else ""}
            data["warnings" if key.startswith("warning") else "suggestions"].append(item)
        elif key.endswith("[]"):
            data.setdefault(key[:-2], []).append(value)
        else:
            data[key] = value
    try:
        data["hardening_index"] = int(data.get("hardening_index", "") or 0)
    except ValueError:
        data["hardening_index"] = 0
    return data


def summarize(data: dict) -> dict:
    return {
        "hardening_index": data.get("hardening_index", 0),
        "lynis_version": data.get("lynis_version", ""),
        "started": data.get("report_datetime_start", ""),
        "ended": data.get("report_datetime_end", ""),
        "tests_performed": len(data.get("tests_executed", [])) if isinstance(data.get("tests_executed"), list) else data.get("tests_performed", ""),
        "warnings": data.get("warnings", []),
        "suggestions": data.get("suggestions", []),
    }


CUSTOM_PRF = "/etc/lynis/custom.prf"


def read_skipped(profile_path: str = CUSTOM_PRF) -> list[dict]:
    """custom.prf 의 skip-test 항목과 바로 위 주석(이유)."""
    out = []
    try:
        with open(profile_path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return out
    pending_comment = []
    for line in lines:
        st = line.strip()
        if st.startswith("#"):
            pending_comment.append(st.lstrip("# ").strip())
        elif st.startswith("skip-test="):
            out.append({"id": st.split("=", 1)[1].strip(), "reason": " ".join(pending_comment)[:200]})
            pending_comment = []
        elif not st:
            pending_comment = []
    return out


def brief_markdown(latest: dict, skipped: list[dict], host: dict, item_id: str | None = None) -> str:
    """Claude 등 대화형 도구에 붙여넣을 수 있는 자기완결 브리프."""
    lines = ["# Lynis 강화 작업 목록 검토 요청", ""]
    lines.append(f"- 호스트: {host.get('hostname', '?')} · {host.get('os', '?')} · 커널 {host.get('kernel', '?')}")
    if host.get("role"):
        lines.append(f"- 서버 역할: {host['role']}")
    lines.append(f"- 감사 시각: {latest.get('started', '?')} · Lynis {latest.get('lynis_version', '?')} · 강화 지수 {latest.get('hardening_index', '?')}/100")
    lines.append("- 보안 대시보드가 이미 담당: 파일 무결성(diff), auditd execve/파일 쓰기 기록, fail2ban 연동, NTP 동기화 감시, 미적용 보안 업데이트, USN 대조")
    lines.append("")
    warnings = [w for w in latest.get("warnings", []) if not item_id or w["id"] == item_id]
    suggestions = [s for s in latest.get("suggestions", []) if not item_id or s["id"] == item_id]
    if warnings:
        lines += ["## 경고", ""]
        for w in warnings:
            lines.append(f"- **{w['id']}** {w['message']}" + (f" — {w['details']}" if w.get("details") else "") + (f" (해결: {w['solution']})" if w.get("solution") else ""))
        lines.append("")
    if suggestions:
        lines += ["## 제안", ""]
        for s in suggestions:
            lines.append(f"- **{s['id']}** {s['message']}" + (f" — {s['details']}" if s.get("details") else "") + (f" (해결: {s['solution']})" if s.get("solution") else ""))
        lines.append("")
    if skipped and not item_id:
        lines += ["## 이미 결정해 건너뛰는 테스트 (다시 제안하지 말 것)", ""]
        for k in skipped:
            lines.append(f"- {k['id']}" + (f": {k['reason']}" if k.get("reason") else ""))
        lines.append("")
    lines += ["## 요청", ""]
    if item_id:
        lines.append(f"위 {item_id} 항목을 이 서버에서 적용 / 수용 / 이미 해결 중 무엇으로 분류해야 하는지, 적용이라면 부작용과 정확한 명령을 알려줘.")
    else:
        lines.append("각 항목을 (1) 지금 적용 (2) 수용하고 skip (3) 이미 다른 방식으로 해결 (4) 판단 필요 로 분류하고, 적용 항목은 부작용과 정확한 명령을 함께 제시해줘. 판단이 필요한 항목은 어떤 정보가 더 필요한지 질문해줘.")
    lines.append("상세 확인 명령: `sudo lynis show details <TEST-ID>`")
    return "\n".join(lines)


class LynisMonitor(BaseMonitor):
    name = "LynisMonitor"
    label = "보안 감사 (Lynis)"
    interval = 600

    def __init__(self, interval: int | None = None, report_path: str = REPORT_PATH, cron_path: str = CRON_PATH):
        super().__init__(interval)
        self.report_path = report_path
        self.cron_path = cron_path
        self.source = f"{report_path} (cron 04:15)"
        self.latest: dict = {}
        self.previous: dict = {}
        self._last_mtime: float | None = None

    # --- 스냅샷 저장 ---
    def _load_previous(self):
        db = SessionLocal()
        try:
            row = db.query(IntegrityBaseline).filter(IntegrityBaseline.key == "lynis:last").first()
            if row and row.snapshot:
                self.previous = json.loads(row.snapshot)
                self.latest = self.previous
                self._last_mtime = float(row.digest) if row.digest else None
        except Exception as e:
            self.log.error(f"load previous lynis snapshot failed: {e}")
        finally:
            db.close()

    def _save(self, summary: dict, mtime: float):
        db = SessionLocal()
        try:
            row = db.query(IntegrityBaseline).filter(IntegrityBaseline.key == "lynis:last").first()
            snap = json.dumps(summary, ensure_ascii=False)
            if row:
                row.digest, row.snapshot = str(mtime), snap
            else:
                db.add(IntegrityBaseline(key="lynis:last", digest=str(mtime), snapshot=snap))
            db.commit()
        finally:
            db.close()

    # --- 수명 주기 ---
    def setup(self):
        self._load_previous()
        self.tick()

    def _check_health(self) -> bool:
        installed = bool(shutil.which("lynis") or os.path.exists("/usr/sbin/lynis"))
        if not installed and not os.path.exists(self.report_path):
            self.set_health("degraded", "Lynis 미설치", "sudo apt install lynis 후 deploy/update.sh 를 실행하세요 (크론과 첫 감사를 설치).")
            return False
        if not os.path.exists(self.cron_path):
            self.set_health("degraded", "Lynis 크론 미설치 (수동 실행 결과만 반영됨)", f"deploy/cron-secdash-lynis 를 {self.cron_path} 에 설치하세요.")
            return True
        if not os.path.exists(self.report_path):
            self.set_health("degraded", "아직 감사 결과 없음 (첫 크론 실행 대기 중)", "지금 실행하려면: sudo lynis audit system --cronjob --quiet")
            return True
        try:
            age = time.time() - os.stat(self.report_path).st_mtime
        except OSError as e:
            self.set_health("degraded", f"보고서 읽기 실패: {e}", "서비스에 CAP_DAC_READ_SEARCH 가 있는지 확인하세요.")
            return False
        if age > STALE_DAYS * 86400:
            self.set_health("degraded", f"감사 결과가 {int(age // 86400)}일 전 것입니다 (크론이 돌지 않음)", "sudo run-parts --test /etc/cron.d 또는 grep lynis /var/log/syslog 로 확인하세요.")
            return True
        self.set_health("ok")
        return True

    def tick(self):
        if not self._check_health() or not os.path.exists(self.report_path):
            return
        try:
            st = os.stat(self.report_path)
            if self._last_mtime is not None and st.st_mtime <= self._last_mtime:
                return
            with open(self.report_path, encoding="utf-8", errors="replace") as f:
                data = parse_report(f.read())
        except PermissionError:
            self.set_health("degraded", f"보고서 읽기 권한 없음: {self.report_path}", "서비스에 CAP_DAC_READ_SEARCH 를 부여하세요.")
            return
        summary = summarize(data)
        # 감사가 중간에 실패하면(프로파일 오류 등) 빈 보고서가 남는다. 이를 '지수 0' 으로 비교하면 거짓 하락 알림이 된다.
        if not data.get("lynis_version") or (summary["hardening_index"] == 0 and not summary["warnings"] and not summary["suggestions"]):
            self.set_health("degraded", "Lynis 보고서가 비어 있음 (감사가 중단됨: 프로파일 오류 가능)",
                            "sudo lynis audit system --cronjob 을 직접 실행해 오류 메시지를 확인하세요. /etc/lynis/custom.prf 에 ASCII 외 문자가 있으면 실행이 중단됩니다.")
            self._last_mtime = st.st_mtime
            return
        self._compare_and_alert(self.previous, summary)
        self.previous, self.latest = summary, summary
        self._last_mtime = st.st_mtime
        self._save(summary, st.st_mtime)

    # --- 비교 ---
    def _compare_and_alert(self, prev: dict, cur: dict):
        idx, prev_idx = cur["hardening_index"], prev.get("hardening_index")
        warns = {w["id"]: w for w in cur["warnings"]}
        prev_warns = {w["id"]: w for w in prev.get("warnings", [])}
        d = {"hardening_index": idx, "previous_index": prev_idx, "warnings": len(warns), "suggestions": len(cur["suggestions"]),
             "new_warnings": sorted(set(warns) - set(prev_warns)), "resolved_warnings": sorted(set(prev_warns) - set(warns)),
             "message_ko": f"Lynis 감사 완료: 강화 지수 {idx}" + (f" (이전 {prev_idx})" if prev_idx is not None else "") + f", 경고 {len(warns)}건, 제안 {len(cur['suggestions'])}건"}
        self.log_event("LYNIS_AUDIT", "INFO", f"Lynis audit: index {idx}, {len(warns)} warnings, {len(cur['suggestions'])} suggestions", d)

        for wid in d["new_warnings"]:
            w = warns[wid]
            raise_alert(
                "lynis_warning", "WARNING", f"Lynis warning {wid}: {w['message']}",
                fingerprint=f"lynis:warn:{wid}",
                title_ko=f"Lynis 경고 {wid}: {w['message']}",
                summary_ko=w["details"] or "Lynis 가 새로 보고한 경고입니다.",
                action_ko=(w["solution"] or f"자세한 내용: sudo lynis show details {wid}") + " · 조치 후 다음 감사에서 사라지면 자동 해결됩니다.",
                details={"test_id": wid, **w},
            )
        for wid in d["resolved_warnings"]:
            auto_resolve(f"lynis:warn:{wid}", "다음 Lynis 감사에서 경고가 사라짐")

        if prev_idx is not None and idx <= prev_idx - INDEX_DROP_THRESHOLD:
            raise_alert(
                "lynis_index_drop", "WARNING", f"Hardening index dropped {prev_idx} -> {idx}",
                fingerprint="lynis:index_drop",
                title_ko=f"강화 지수 하락: {prev_idx} → {idx}",
                summary_ko="새 경고: " + (", ".join(d["new_warnings"]) or "없음") + ". 설정이 느슨해졌거나 새 서비스가 추가되었을 수 있습니다.",
                action_ko="sudo lynis audit system 으로 재확인하고 강화 작업 목록에서 새로 늘어난 항목을 처리하세요.",
                details=d,
            )
        elif prev_idx is not None and idx >= prev_idx:
            auto_resolve("lynis:index_drop", "강화 지수 회복")

    def status_payload(self) -> dict:
        return {"available": bool(self.latest), "health": self.health, "health_reason": self.health_reason, "fix_hint": self.fix_hint, **(self.latest or {})}
