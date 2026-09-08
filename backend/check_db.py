from database import SessionLocal, Event

db = SessionLocal()
# Get last 10 events
events = db.query(Event).order_by(Event.timestamp.desc()).limit(10).all()
for e in events:
    print(f"[{e.timestamp}] {e.event_type}: {e.description}")
db.close()
