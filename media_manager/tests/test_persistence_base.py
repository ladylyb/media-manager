from __future__ import annotations

import pytest

from media_manager.app.persistence.base import get_database_url


def test_get_database_url_accepts_valid_postgres_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://mm_user:mm_user1@db-host:5432/media_manager_test",
    )

    assert get_database_url() == "postgresql+psycopg://mm_user:mm_user1@db-host:5432/media_manager_test"


def test_get_database_url_rejects_unresolved_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://mm_user:mm_user1@${WINDOWS_DB_HOST}:5432/media_manager_test",
    )

    with pytest.raises(RuntimeError, match="unresolved environment variable placeholder"):
        get_database_url()


def test_get_database_url_rejects_missing_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://mm_user:mm_user1@/media_manager_test",
    )

    with pytest.raises(RuntimeError, match="must include an explicit PostgreSQL host"):
        get_database_url()


def test_get_database_url_rejects_non_postgres_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///media-manager.db")

    with pytest.raises(RuntimeError, match="must point to PostgreSQL"):
        get_database_url()
