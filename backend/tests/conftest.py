import os
import sys
from pathlib import Path

# 백엔드 모듈을 import 하기 전에 테스트용 환경을 고정한다
os.environ["SECDASH_DB_URL"] = "sqlite://"
os.environ["SECDASH_API_TOKEN"] = "test-token"
os.environ["SLACK_WEBHOOK_URL"] = ""
os.environ["SECDASH_INTEL_TRANSLATE"] = "0"
os.environ["SECDASH_USN_MATCH"] = "0"
os.environ["ANTHROPIC_API_KEY"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

import database  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    database.init_db()
    yield
    with database.engine.begin() as conn:
        for table in reversed(database.Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def db():
    s = database.SessionLocal()
    try:
        yield s
    finally:
        s.close()
