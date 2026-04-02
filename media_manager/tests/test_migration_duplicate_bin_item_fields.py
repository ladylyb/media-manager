from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

LEGACY_DUPLICATE_RECLAIM_ITEM_COLUMNS = {
    "file_instance_id",
    "content_id",
    "original_path",
    "archive_path",
    "item_status",
    "reclaimed_at",
    "expires_at",
    "recycle_path",
    "recycled_at",
    "purge_after_at",
    "purged_at",
    "restored_at",
    "created_at",
    "updated_at",
}

PHASE1_DUPLICATE_BIN_ITEM_COLUMNS = {
    "planned_bin_path",
    "bin_path",
    "bin_entered_at",
    "restore_expires_at",
    "bin_state",
}


def _duplicate_reclaim_item_columns(engine) -> dict[str, dict[str, object]]:
    inspector = inspect(engine)
    return {column["name"]: column for column in inspector.get_columns("duplicate_reclaim_items")}


def test_duplicate_bin_item_fields_exist_and_are_nullable(db_engine) -> None:
    columns = _duplicate_reclaim_item_columns(db_engine)

    assert PHASE1_DUPLICATE_BIN_ITEM_COLUMNS.issubset(columns)
    assert columns["planned_bin_path"]["nullable"] is True
    assert columns["bin_path"]["nullable"] is True
    assert columns["bin_entered_at"]["nullable"] is True
    assert columns["restore_expires_at"]["nullable"] is True
    assert columns["bin_state"]["nullable"] is True


def test_duplicate_bin_item_field_migration_preserves_legacy_columns(db_engine) -> None:
    columns = set(_duplicate_reclaim_item_columns(db_engine))
    assert LEGACY_DUPLICATE_RECLAIM_ITEM_COLUMNS.issubset(columns)


def test_duplicate_bin_item_field_migration_adds_exactly_five_columns(db_engine) -> None:
    columns = set(_duplicate_reclaim_item_columns(db_engine))
    assert columns - LEGACY_DUPLICATE_RECLAIM_ITEM_COLUMNS == PHASE1_DUPLICATE_BIN_ITEM_COLUMNS


def test_duplicate_bin_item_field_migration_roundtrip(test_database_url: str) -> None:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", test_database_url)

    original_database_url = os.getenv("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_database_url
    engine = create_engine(test_database_url, future=True)
    try:
        command.downgrade(cfg, "0029")
        columns_at_0029 = set(_duplicate_reclaim_item_columns(engine))
        assert LEGACY_DUPLICATE_RECLAIM_ITEM_COLUMNS.issubset(columns_at_0029)
        assert PHASE1_DUPLICATE_BIN_ITEM_COLUMNS.isdisjoint(columns_at_0029)

        command.upgrade(cfg, "0030")
        columns_at_0030 = _duplicate_reclaim_item_columns(engine)
        assert LEGACY_DUPLICATE_RECLAIM_ITEM_COLUMNS.issubset(columns_at_0030)
        assert set(columns_at_0030) - LEGACY_DUPLICATE_RECLAIM_ITEM_COLUMNS == PHASE1_DUPLICATE_BIN_ITEM_COLUMNS
        assert columns_at_0030["planned_bin_path"]["nullable"] is True
        assert columns_at_0030["bin_path"]["nullable"] is True
        assert columns_at_0030["bin_entered_at"]["nullable"] is True
        assert columns_at_0030["restore_expires_at"]["nullable"] is True
        assert columns_at_0030["bin_state"]["nullable"] is True

        command.downgrade(cfg, "0029")
        columns_after_downgrade = set(_duplicate_reclaim_item_columns(engine))
        assert LEGACY_DUPLICATE_RECLAIM_ITEM_COLUMNS.issubset(columns_after_downgrade)
        assert PHASE1_DUPLICATE_BIN_ITEM_COLUMNS.isdisjoint(columns_after_downgrade)

        command.upgrade(cfg, "0030")
        columns_after_reupgrade = set(_duplicate_reclaim_item_columns(engine))
        assert LEGACY_DUPLICATE_RECLAIM_ITEM_COLUMNS.issubset(columns_after_reupgrade)
        assert columns_after_reupgrade - LEGACY_DUPLICATE_RECLAIM_ITEM_COLUMNS == PHASE1_DUPLICATE_BIN_ITEM_COLUMNS
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
        if original_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_database_url


def test_duplicate_bin_item_field_migration_is_additive_only() -> None:
    migration_file = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "0030_duplicate_bin_item_fields.py"
    )
    content = migration_file.read_text(encoding="utf-8")

    assert 'op.add_column("duplicate_reclaim_items", sa.Column("planned_bin_path", sa.Text(), nullable=True))' in content
    assert 'op.add_column("duplicate_reclaim_items", sa.Column("bin_path", sa.Text(), nullable=True))' in content
    assert (
        'op.add_column("duplicate_reclaim_items", sa.Column("bin_entered_at", sa.DateTime(timezone=True), nullable=True))'
        in content
    )
    assert (
        'op.add_column("duplicate_reclaim_items", sa.Column("restore_expires_at", sa.DateTime(timezone=True), nullable=True))'
        in content
    )
    assert 'op.add_column("duplicate_reclaim_items", sa.Column("bin_state", sa.Text(), nullable=True))' in content

    assert 'op.drop_table("duplicate_reclaim_items")' not in content
    assert 'op.drop_constraint("ck_duplicate_reclaim_items_status"' not in content
    assert 'op.drop_index("idx_duplicate_reclaim_items_status"' not in content
    assert 'op.alter_column("duplicate_reclaim_items"' not in content
