"""간단한 DB 점검 도구: 최근 이벤트/알림을 출력한다."""
from database import Alert, Event, SessionLocal

db = SessionLocal()
try:
    print("== 최근 이벤트 ==")
    for e in db.query(Event).order_by(Event.timestamp.desc()).limit(10).all():
        print(f"[{e.timestamp}] {e.severity:8} {e.event_type:20} {e.description_ko or e.description}")
    print("\n== 미해결 알림 ==")
    for a in db.query(Alert).filter(Alert.status != "RESOLVED").order_by(Alert.last_seen_at.desc()).limit(10).all():
        print(f"[{a.last_seen_at}] {a.status:6} {a.severity:8} x{a.count} {a.title_ko or a.title}")
finally:
    db.close()
