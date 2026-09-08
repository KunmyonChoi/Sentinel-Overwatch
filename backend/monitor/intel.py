import requests
import logging
import time
import xml.etree.ElementTree as ET
from database import SessionLocal, Event

logger = logging.getLogger("intel_monitor")

RSS_FEED_URL = "https://feeds.feedburner.com/TheHackersNews"

class IntelMonitor:
    def __init__(self, interval=3600): # Check every hour
        self.interval = interval
        self.running = False
        self.seen_guids = set()

    def monitor(self):
        self.running = True
        logger.info("Starting Intel Monitor")
        self._load_seen_guids_from_db()
        while self.running:
            self.fetch_feed()
            time.sleep(self.interval)

    def _load_seen_guids_from_db(self):
        """Seed seen_guids from DB on startup to survive restarts."""
        db = SessionLocal()
        try:
            events = db.query(Event).filter(Event.event_type == "THREAT_INTEL").all()
            for e in events:
                # Extract URL (used as GUID) from stored description
                parts = e.description.rsplit(" - ", 1)
                if len(parts) == 2:
                    self.seen_guids.add(parts[1].strip())
            logger.info(f"Loaded {len(self.seen_guids)} known GUIDs from DB")
        except Exception as ex:
            logger.error(f"Failed to load GUIDs from DB: {ex}")
        finally:
            db.close()

    def fetch_feed(self):
        try:
            response = requests.get(RSS_FEED_URL, timeout=10)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                new_count = 0
                for item in root.findall(".//item"):
                    guid_el = item.find("guid")
                    link_el = item.find("link")
                    title_el = item.find("title")
                    guid = (guid_el.text if guid_el is not None else None) or (link_el.text if link_el is not None else None)
                    title = title_el.text if title_el is not None else "(no title)"
                    link = link_el.text if link_el is not None else ""

                    if guid and guid not in self.seen_guids:
                        self.seen_guids.add(guid)
                        desc = f"New Threat Intel: {title} - {link}"
                        logger.info(desc)
                        self.log_event("THREAT_INTEL", "INFO", "RSSFeed", desc)
                        new_count += 1
                logger.info(f"Feed fetched: {new_count} new items ingested")
            else:
                logger.error(f"Failed to fetch feed: {response.status_code}")
        except Exception as e:
            logger.error(f"Intel fetch error: {e}")

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
        except Exception as e:
            logger.error(f"Database error: {e}")
        finally:
            db.close()
