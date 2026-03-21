"""Database engine/session primitives.

Crash-safety model:
- All state-changing operations must run inside an explicit transaction.
- If a process crashes before commit, the DB transaction is rolled back by PostgreSQL.
- No implicit autocommit behavior is allowed.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.core.config import load_environment


def _validate_database_url(url: str) -> str:
    if "${" in url:
        raise RuntimeError(
            "DATABASE_URL contains an unresolved environment variable placeholder. "
            "Expand placeholders such as ${WINDOWS_DB_HOST} before starting the application."
        )

    try:
        parsed = make_url(url)
    except Exception as exc:  # pragma: no cover - delegated parser error details
        raise RuntimeError("DATABASE_URL is not a valid SQLAlchemy database URL.") from exc

    if not parsed.drivername.startswith("postgresql"):
        raise RuntimeError("DATABASE_URL must point to PostgreSQL; SQLite is not supported.")
    if not parsed.host:
        raise RuntimeError(
            "DATABASE_URL must include an explicit PostgreSQL host. "
            "Without a host psycopg attempts a local Unix socket, which fails unless PostgreSQL is running locally."
        )
    return url


def get_database_url() -> str:
    load_environment()
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL must be set for PostgreSQL execution.")
    return _validate_database_url(url)


def create_db_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_database_url()
    return create_engine(url, future=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@contextmanager
def transactional_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        with session.begin():
            yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
