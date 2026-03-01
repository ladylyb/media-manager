from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from media_manager.app.core.config import load_environment
from media_manager.app.persistence.base import create_session_factory
from media_manager.app.persistence.runs import RunService


@pytest.fixture(scope="session")
def test_database_url() -> str:
    load_environment()
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        raise RuntimeError("TEST_DATABASE_URL must be set to a PostgreSQL database URL.")
    if "postgresql" not in url:
        raise RuntimeError("TEST_DATABASE_URL must point to PostgreSQL.")
    return url


@pytest.fixture(scope="session")
def db_engine(test_database_url: str) -> Iterator[Engine]:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", test_database_url)

    original_database_url = os.getenv("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_database_url
    try:
        command.upgrade(cfg, "head")
    finally:
        if original_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_database_url
    engine = create_engine(test_database_url, future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables(db_engine: Engine) -> None:
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE media_metadata, metadata_codes, planned_actions, "
                "apply_audit_items, apply_audit_runs, "
                "file_instances, file_contents, failure_events, files, content_objects, runs "
                "RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
def session_factory(db_engine: Engine) -> sessionmaker:
    return create_session_factory(db_engine)


@pytest.fixture
def run_service(session_factory: sessionmaker) -> RunService:
    return RunService(session_factory)
