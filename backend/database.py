import datetime
import json
import logging

from sqlalchemy import (
    Boolean, Column, DateTime, Integer, String, Text, create_engine, event, inspect, text,
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

import config

logger = logging.getLogger("database")

_engine_kwargs: dict = {}
if config.DB_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    if config.DB_URL in ("sqlite://", "sqlite:///:memory:"):
        # 테스트용 인메모리 DB: 모든 스레드가 같은 커넥션을 공유해야 한다
        _engine_kwargs["poolclass"] = StaticPool

engine = create_engine(config.DB_URL, **_engine_kwargs)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record):
    """여러 모니터 스레드가 동시에 쓰므로 WAL + busy timeout 을 켠다."""
    if not config.DB_URL.startswith("sqlite"):
        return
    cur = dbapi_conn.cursor()
    try:
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA synchronous=NORMAL")
    except Exception:  # 인메모리 등 WAL 미지원 환경
        pass
    finally:
        cur.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def utcnow() -> datetime.datetime:
    """naive UTC (SQLite 저장 형식 유지)."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


class Event(Base):
    """원시 이벤트. 모니터가 관찰한 사실을 그대로 기록한다 (판단은 Alert 가 담당)."""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=utcnow, index=True)
    event_type = Column(String, index=True)
    severity = Column(String, index=True)      # INFO / WARNING / CRITICAL
    source = Column(String)
    description = Column(Text)
    description_ko = Column(Text, nullable=True)   # 템플릿 기반 한국어 (외부 번역 없음)
    details = Column(Text, nullable=True)          # JSON
    is_simulation = Column(Boolean, default=False, index=True)

    def details_dict(self) -> dict:
        if not self.details:
            return {}
        try:
            return json.loads(self.details)
        except ValueError:
            return {}


class Alert(Base):
    """상관 분석된 알림. 운영자가 확인(ack)/해결(resolve)하는 단위."""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=utcnow, index=True)
    last_seen_at = Column(DateTime, default=utcnow, index=True)
    rule = Column(String, index=True)           # 예: brute_force, integrity_change
    fingerprint = Column(String, index=True)    # 중복 억제 키
    severity = Column(String, index=True)       # WARNING / CRITICAL
    title = Column(Text)
    title_ko = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    summary_ko = Column(Text, nullable=True)
    action_ko = Column(Text, nullable=True)     # 운영자가 지금 할 일
    evidence = Column(Text, nullable=True)      # 판단 근거 (로그 줄, diff 등)
    details = Column(Text, nullable=True)       # JSON
    count = Column(Integer, default=1)
    status = Column(String, default="OPEN", index=True)   # OPEN / ACKED / RESOLVED
    acked_at = Column(DateTime, nullable=True)
    acked_by = Column(String, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String, nullable=True)
    resolution_note = Column(Text, nullable=True)
    is_simulation = Column(Boolean, default=False, index=True)

    def details_dict(self) -> dict:
        if not self.details:
            return {}
        try:
            return json.loads(self.details)
        except ValueError:
            return {}


class BlockedIP(Base):
    __tablename__ = "blocked_ips"

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String, unique=True, index=True)
    reason = Column(String)
    blocked_at = Column(DateTime, default=utcnow)
    status = Column(String, default="ACTIVE")   # ACTIVE / RECOMMENDED / UNBLOCKED / EXPIRED
    source = Column(String, default="detector")  # fail2ban / detector / manual
    jail = Column(String, nullable=True)
    unblocked_at = Column(DateTime, nullable=True)


class TranslationCache(Base):
    __tablename__ = "translation_cache"

    id = Column(Integer, primary_key=True, index=True)
    source_text = Column(Text, unique=True, index=True)
    translated_text = Column(Text)
    urgency = Column(String, nullable=True)


class IntegrityBaseline(Base):
    """파일/파일집합 기준선. 재시작해도 유지되어 서비스 중지 중 변경도 잡는다."""
    __tablename__ = "integrity_baselines"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True)   # 예: file:/etc/passwd, cron:/etc/cron.d/x
    digest = Column(String, nullable=True)          # sha256, None = 없음
    snapshot = Column(Text, nullable=True)          # diff 용 내용 (비밀 파일은 저장 안 함)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class KnownLoginIP(Base):
    __tablename__ = "known_login_ips"

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String, unique=True, index=True)
    users = Column(String, default="")   # 쉼표 구분
    first_seen = Column(DateTime, default=utcnow)
    last_seen = Column(DateTime, default=utcnow)
    login_count = Column(Integer, default=0)


class KnownListener(Base):
    __tablename__ = "known_listeners"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True)   # "<addr>:<port>/<process>"
    port = Column(Integer)
    address = Column(String)
    process = Column(String, nullable=True)
    first_seen = Column(DateTime, default=utcnow)
    last_seen = Column(DateTime, default=utcnow)


class MaintenanceWindow(Base):
    """운영자가 선언한 계획 작업 창. 이 동안의 설정/패키지/영속화 알림은 자동 확인 처리된다."""
    __tablename__ = "maintenance_windows"

    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime, default=utcnow)
    ends_at = Column(DateTime, index=True)
    ended_at = Column(DateTime, nullable=True)
    note = Column(Text, nullable=True)
    by = Column(String, nullable=True)


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(String, unique=True, index=True)
    summary = Column(Text)
    total_events = Column(Integer, default=0)
    critical_events = Column(Integer, default=0)


_SQL_TYPES = {"INTEGER": "INTEGER", "VARCHAR": "VARCHAR", "TEXT": "TEXT", "DATETIME": "DATETIME", "BOOLEAN": "BOOLEAN"}


def _migrate():
    """기존 SQLite 테이블에 새 컬럼을 추가한다 (create_all 은 컬럼을 추가하지 않음)."""
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                coltype = col.type.compile(engine.dialect)
                base = coltype.split("(")[0].upper()
                ddl = f'ALTER TABLE {table.name} ADD COLUMN {col.name} {_SQL_TYPES.get(base, coltype)}'
                if col.default is not None and getattr(col.default, "arg", None) is not None and not callable(col.default.arg):
                    arg = col.default.arg
                    if isinstance(arg, bool):
                        ddl += f" DEFAULT {1 if arg else 0}"
                    elif isinstance(arg, (int, float)):
                        ddl += f" DEFAULT {arg}"
                    else:
                        ddl += f" DEFAULT '{arg}'"
                logger.info(f"migrate: {ddl}")
                conn.execute(text(ddl))


def init_db():
    Base.metadata.create_all(bind=engine)
    try:
        _migrate()
    except Exception as e:
        logger.error(f"migration failed: {e}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def apply_retention():
    """오래된 원시 이벤트와 해결된 알림을 삭제한다."""
    db = SessionLocal()
    try:
        ev_cut = utcnow() - datetime.timedelta(days=config.EVENT_RETENTION_DAYS)
        al_cut = utcnow() - datetime.timedelta(days=config.ALERT_RETENTION_DAYS)
        pending = db.query(Event).filter(Event.timestamp < ev_cut).count()
        if pending:
            logger.warning(f"retention: deleting {pending} events older than {config.EVENT_RETENTION_DAYS} days")
        n_ev = db.query(Event).filter(Event.timestamp < ev_cut).delete(synchronize_session=False)
        n_al = db.query(Alert).filter(Alert.status == "RESOLVED", Alert.resolved_at < al_cut).delete(synchronize_session=False)
        db.commit()
        if n_ev or n_al:
            logger.info(f"retention: removed {n_ev} events, {n_al} resolved alerts")
    except Exception as e:
        db.rollback()
        logger.error(f"retention failed: {e}")
    finally:
        db.close()
