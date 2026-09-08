from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime

SQLALCHEMY_DATABASE_URL = "sqlite:///./security_monitor.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    event_type = Column(String, index=True) # e.g., 'INTRUSION', 'MALWARE', 'SYSTEM'
    severity = Column(String) # 'INFO', 'WARNING', 'CRITICAL'
    source = Column(String) # 'SSH', 'Process', 'Network'
    description = Column(Text)
    details = Column(Text, nullable=True) # JSON or extra details

class BlockedIP(Base):
    __tablename__ = "blocked_ips"

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String, unique=True, index=True)
    reason = Column(String)
    blocked_at = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String, default="ACTIVE") # 'ACTIVE', 'UNBLOCKED'

class TranslationCache(Base):
    __tablename__ = "translation_cache"

    id = Column(Integer, primary_key=True, index=True)
    source_text = Column(Text, unique=True, index=True)
    translated_text = Column(Text)
    urgency = Column(String, nullable=True)  # CRITICAL / HIGH / MEDIUM / LOW

class DailyReport(Base):
    __tablename__ = "daily_reports"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(String, unique=True, index=True) # YYYY-MM-DD
    summary = Column(Text)
    total_events = Column(Integer, default=0)
    critical_events = Column(Integer, default=0)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
