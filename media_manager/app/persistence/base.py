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
from sqlalchemy.orm import Session, sessionmaker


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL must be set for PostgreSQL execution.")
    if "postgresql" not in url:
        raise RuntimeError("DATABASE_URL must point to PostgreSQL; SQLite is not supported.")
    return url


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
