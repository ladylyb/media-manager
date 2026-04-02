from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


LEGACY_DUPLICATE_RECLAIM_RECORD_COLUMNS = {
    "content_id",
    "reclaim_status",
    "reviewed_at",
    "reviewed_by",
    "archive_path",
    "reclaimed_at",
    "expires_at",
    "restored_at",
    "created_at",
    "updated_at",
}

RETAINED_DUPLICATE_RECLAIM_RECORD_COLUMNS = {
    "content_id",
    "reclaim_status",
    "reviewed_at",
    "reviewed_by",
    "restored_at",
    "created_at",
    "updated_at",
}

DROPPED_DUPLICATE_RECLAIM_RECORD_COLUMNS = {
    "archive_path",
    "reclaimed_at",
    "expires_at",
}


def _duplicate_reclaim_record_columns(engine) -> dict[str, dict[str, object]]:
    inspector = inspect(engine)
    return {column["name"]: column for column in inspector.get_columns("duplicate_reclaim_records")}


def test_duplicate_reclaim_record_cleanup_migration_roundtrip(test_database_url: str) -> None:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", test_database_url)

    original_database_url = os.getenv("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_database_url
    engine = create_engine(test_database_url, future=True)
    try:
        command.downgrade(cfg, "0031")
        columns_at_0031 = set(_duplicate_reclaim_record_columns(engine))
        assert LEGACY_DUPLICATE_RECLAIM_RECORD_COLUMNS.issubset(columns_at_0031)

        command.upgrade(cfg, "0032")
        columns_at_0032 = set(_duplicate_reclaim_record_columns(engine))
        assert RETAINED_DUPLICATE_RECLAIM_RECORD_COLUMNS.issubset(columns_at_0032)
        assert DROPPED_DUPLICATE_RECLAIM_RECORD_COLUMNS.isdisjoint(columns_at_0032)

        command.downgrade(cfg, "0031")
        columns_after_downgrade = set(_duplicate_reclaim_record_columns(engine))
        assert LEGACY_DUPLICATE_RECLAIM_RECORD_COLUMNS.issubset(columns_after_downgrade)
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
        if original_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_database_url


def test_duplicate_reclaim_record_cleanup_migration_is_limited() -> None:
    migration_file = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "0032_drop_duplicate_reclaim_record_legacy_columns.py"
    )
    content = migration_file.read_text(encoding="utf-8")

    assert 'op.drop_column("duplicate_reclaim_records", "archive_path")' in content
    assert 'op.drop_column("duplicate_reclaim_records", "reclaimed_at")' in content
    assert 'op.drop_column("duplicate_reclaim_records", "expires_at")' in content

    assert 'op.drop_table("duplicate_reclaim_records")' not in content
    assert 'op.drop_column("duplicate_reclaim_items"' not in content
    assert 'op.alter_column("duplicate_reclaim_items"' not in content
