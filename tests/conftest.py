from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from dnd_summary import db as db_module
from dnd_summary.config import settings
from dnd_summary.models import Base


@pytest.fixture()
def settings_overrides() -> Iterator[Callable[..., None]]:
    original: dict[str, object] = {}

    def _set(**kwargs: object) -> None:
        for key, value in kwargs.items():
            if key not in original:
                original[key] = getattr(settings, key)
            setattr(settings, key, value)

    yield _set

    for key, value in original.items():
        setattr(settings, key, value)


@pytest.fixture()
def db_engine(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "ENGINE", engine)
    monkeypatch.setattr(db_module, "SessionLocal", SessionLocal)
    return engine


@pytest.fixture()
def db_session(db_engine):
    session = db_module.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def api_client(db_engine):
    from dnd_summary.api import app

    return TestClient(app)
