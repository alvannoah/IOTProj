"""Runs on a temporary SQLite file by default.

Set TEST_DATABASE_URL to run on a real server. Every table in that database is
dropped, so point it at a throwaway database only.
"""
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["UTC_OFFSET_MINUTES"] = "180"
os.environ["CURRENCY"] = "TEST"

import pytest
from fastapi.testclient import TestClient

from config.database import Base, SessionLocal, engine
from main import app


@pytest.fixture(autouse=True)
def clean_tables():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()
