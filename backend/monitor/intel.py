"""
위협 인텔 수집.
  - 일반 보안 뉴스 RSS (기본: The Hacker News)
  - Ubuntu Security Notice (USN) RSS: 각 공지의 JSON 에서 이 호스트 릴리스의 영향 패키지를 읽어
    설치된 버전과 비교한다. 취약한 버전이 설치돼 있으면 알림을 올린다.
    (패키지 목록은 외부로 보내지 않는다. 공개 URL 을 읽기만 한다.)
"""
import json
import re
import xml.etree.ElementTree as ET

import requests

import config
from alerts import auto_resolve, open_alerts_details, raise_alert
from database import Event, SessionLocal
from integrations import apt
from monitor.base import BaseMonitor


def parse_rss(content: bytes) -> list[dict]:
    root = ET.fromstring(content)
    items = []
    for item in root.findall(".//item"):
        def text(tag):
            el = item.find(tag)
            return (el.text or "").strip() if el is not None else ""
        guid = text("guid") or text("link")
        items.append({"guid": guid, "title": text("title") or "(no title)", "link": text("link"), "description": text("description")})
    return items


def match_usn(release_packages: dict, codename: str, installed: dict[str, str]) -> list[dict]:
    """USN 의 release_packages 와 설치 패키지를 대조해 취약한 항목을 돌려준다."""
    out = []
    for entry in release_packages.get(codename, []):
        if entry.get("is_source"):
            continue
        name, fixed = entry.get("name"), entry.get("version")
        if not name or not fixed or name not in installed:
            continue
        inst = installed[name]
        if apt.version_lt(inst, fixed):
            out.append({"package": name, "installed": inst, "fixed": fixed})
    return out


class IntelMonitor(BaseMonitor):
    name = "IntelMonitor"
    label = "위협 인텔 (뉴스 + Ubuntu USN)"
    interval = 3600

    def __init__(self, interval: int | None = None, feeds: list[str] | None = None, usn_url: str | None = None):
        super().__init__(interval)
        self.feeds = feeds if feeds is not None else config.INTEL_FEEDS
        self.usn_url = usn_url if usn_url is not None else (config.USN_FEED_URL if config.USN_MATCH else "")
        self.source = ", ".join(self.feeds + ([self.usn_url] if self.usn_url else []))
        self.seen_guids: set[str] = set()
        self.codename = apt.os_codename()

    def setup(self):
        self._load_seen()
        self._recheck_open()   # 재시작 직후, 그 사이 적용된 업데이트부터 정리한다

    def _load_seen(self):
        db = SessionLocal()
        try:
            for e in db.query(Event).filter(Event.event_type == "THREAT_INTEL").all():
                d = e.details_dict()
                if d.get("guid"):
                    self.seen_guids.add(d["guid"])
                else:  # 이전 버전 형식: "... - <link>"
                    parts = (e.description or "").rsplit(" - ", 1)
                    if len(parts) == 2:
                        self.seen_guids.add(parts[1].strip())
        finally:
            db.close()

    def tick(self):
        # 새 공지를 받아오기 전에, 이미 올려둔 알림이 아직도 유효한지 먼저 본다.
        self._recheck_open()
        errors = []
        for url in self.feeds:
            try:
                self._fetch_news(url)
            except Exception as e:
                errors.append(f"{url}: {e}")
        if self.usn_url:
            try:
                self._fetch_usn()
            except Exception as e:
                errors.append(f"USN: {e}")
        if errors:
            self.set_health("degraded", "피드 수집 실패: " + "; ".join(errors)[:300], "네트워크/프록시 설정을 확인하세요.")
        else:
            self.set_health("ok")

    def _recheck_open(self):
        """살아 있는 USN 알림을 지금 설치된 버전과 다시 대조한다.

        공지를 받은 시점의 판정은 그 시점의 사실일 뿐이다. 그 뒤에 업데이트를
        적용하면 알림은 이미 해결된 일인데도 사람이 손으로 닫을 때까지 남는다.
        그렇게 쌓인 목록은 결국 아무도 안 본다.

        대조는 알림에 저장해 둔 근거(details.affected)와 dpkg 로만 한다 — 네트워크를
        다시 타지 않는다. 설치 목록을 읽지 못하면 **아무 판단도 하지 않는다**:
        못 읽은 것을 '해결됨'으로 바꾸면 조용히 알림을 지우는 셈이다.
        """
        rows = open_alerts_details("usn_affects_host")
        if not rows:
            return
        installed = apt.installed_packages()
        if not installed:
            self.log.warning("설치 패키지 목록을 읽지 못해 USN 재대조를 건너뜁니다")
            return
        for fp, d in rows:
            affected = d.get("affected") or []
            if not affected:
                continue
            # 패키지가 지워졌거나(목록에 없음) 수정 버전 이상이면 더는 해당하지 않는다
            still = [a for a in affected
                     if a.get("package") in installed
                     and a.get("fixed")
                     and apt.version_lt(installed[a["package"]], a["fixed"])]
            if not still:
                n = auto_resolve(fp, "설치된 버전이 수정 버전 이상이라 자동 해결")
                if n:
                    self.log.info(f"{fp}: 수정 버전 적용 확인, 자동 해결")

    def _fetch_news(self, url: str):
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        n = 0
        for it in parse_rss(resp.content):
            if not it["guid"] or it["guid"] in self.seen_guids:
                continue
            self.seen_guids.add(it["guid"])
            d = {"guid": it["guid"], "feed": "news", "title": it["title"], "link": it["link"]}
            self.log_event("THREAT_INTEL", "INFO", f"{it['title']} - {it['link']}", d, description_ko="")
            n += 1
        self.log.info(f"{url}: {n} new items")

    def _fetch_usn(self):
        resp = requests.get(self.usn_url, timeout=15)
        resp.raise_for_status()
        items = [it for it in parse_rss(resp.content) if it["guid"] and it["guid"] not in self.seen_guids]
        if not items:
            return
        installed = apt.installed_packages() if self.codename else {}
        for it in items:
            self.seen_guids.add(it["guid"])
            usn_id = re.match(r"(USN-[\d-]+)", it["title"])
            affected: list[dict] = []
            cves: list[str] = []
            if installed and usn_id:
                try:
                    data = requests.get(f"https://ubuntu.com/security/notices/{usn_id.group(1)}.json", timeout=15).json()
                    affected = match_usn(data.get("release_packages", {}), self.codename, installed)
                    cves = data.get("cves_ids", [])[:10]
                except Exception as e:
                    self.log.warning(f"USN detail fetch failed for {usn_id.group(1)}: {e}")
            d = {"guid": it["guid"], "feed": "usn", "title": it["title"], "link": it["link"], "affects_host": bool(affected),
                 "affected": affected, "cves": cves, "codename": self.codename}
            self.log_event("THREAT_INTEL", "WARNING" if affected else "INFO", f"{it['title']} - {it['link']}", d, description_ko="")
            if affected:
                pk = ", ".join(f"{a['package']} {a['installed']} → {a['fixed']}" for a in affected[:8])
                raise_alert(
                    "usn_affects_host", "WARNING", f"{it['title']} affects installed packages",
                    fingerprint=f"usn:{usn_id.group(1) if usn_id else it['guid']}",
                    title_ko=f"이 서버에 영향 있는 보안 공지: {it['title']}",
                    summary_ko=f"취약한 설치 패키지: {pk}" + (f" (CVE: {', '.join(cves[:5])})" if cves else ""),
                    action_ko="`sudo apt update && sudo apt install --only-upgrade " + " ".join(a["package"] for a in affected[:8]) + "` 로 수정 버전을 적용하세요.",
                    evidence=it["description"][:1500], details=d,
                )
