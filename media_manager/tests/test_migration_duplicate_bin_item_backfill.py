from __future__ import annotations

import importlib.util
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from media_manager.tests.test_migration_duplicate_bin_item_fields import (
    LEGACY_DUPLICATE_RECLAIM_ITEM_COLUMNS,
    PHASE1_DUPLICATE_BIN_ITEM_COLUMNS,
    _duplicate_reclaim_item_columns,
)


def _load_0031_module():
    path = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0031_duplicate_bin_item_backfill.py"
    spec = importlib.util.spec_from_file_location("duplicate_bin_item_backfill_0031", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _insert_duplicate_reclaim_item(
    engine,
    *,
    file_instance_id,
    content_id,
    original_path: str,
    archive_path: str,
    item_status: str,
    reclaimed_at,
    expires_at,
    recycle_path,
    recycled_at,
    purge_after_at,
    purged_at,
    restored_at,
    planned_bin_path=None,
    bin_path=None,
    bin_entered_at=None,
    restore_expires_at=None,
    bin_state=None,
) -> None:
    now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO file_contents (content_id, sha256_hash, first_seen_at)
                VALUES (:content_id, :sha256_hash, :first_seen_at)
                """
            ),
            {
                "content_id": content_id,
                "sha256_hash": content_id.hex.ljust(64, "0"),
                "first_seen_at": now,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO file_instances (
                    file_instance_id, content_id, absolute_path, filesystem_id, first_seen_at, last_seen_at, status
                ) VALUES (
                    :file_instance_id, :content_id, :absolute_path, :filesystem_id, :first_seen_at, :last_seen_at, :status
                )
                """
            ),
            {
                "file_instance_id": file_instance_id,
                "content_id": content_id,
                "absolute_path": original_path,
                "filesystem_id": "fs-1",
                "first_seen_at": now,
                "last_seen_at": now,
                "status": "ACTIVE",
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO duplicate_reclaim_items (
                    file_instance_id,
                    content_id,
                    original_path,
                    archive_path,
                    planned_bin_path,
                    bin_path,
                    item_status,
                    reclaimed_at,
                    bin_entered_at,
                    expires_at,
                    restore_expires_at,
                    bin_state,
                    recycle_path,
                    recycled_at,
                    purge_after_at,
                    purged_at,
                    restored_at,
                    created_at,
                    updated_at
                ) VALUES (
                    :file_instance_id,
                    :content_id,
                    :original_path,
                    :archive_path,
                    :planned_bin_path,
                    :bin_path,
                    :item_status,
                    :reclaimed_at,
                    :bin_entered_at,
                    :expires_at,
                    :restore_expires_at,
                    :bin_state,
                    :recycle_path,
                    :recycled_at,
                    :purge_after_at,
                    :purged_at,
                    :restored_at,
                    :created_at,
                    :updated_at
                )
                """
            ),
            {
                "file_instance_id": file_instance_id,
                "content_id": content_id,
                "original_path": original_path,
                "archive_path": archive_path,
                "planned_bin_path": planned_bin_path,
                "bin_path": bin_path,
                "item_status": item_status,
                "reclaimed_at": reclaimed_at,
                "bin_entered_at": bin_entered_at,
                "expires_at": expires_at,
                "restore_expires_at": restore_expires_at,
                "bin_state": bin_state,
                "recycle_path": recycle_path,
                "recycled_at": recycled_at,
                "purge_after_at": purge_after_at,
                "purged_at": purged_at,
                "restored_at": restored_at,
                "created_at": now,
                "updated_at": now,
            },
        )


def test_duplicate_bin_item_backfill_migration_roundtrip_and_mappings(test_database_url: str) -> None:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", test_database_url)

    original_database_url = os.getenv("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_database_url
    engine = create_engine(test_database_url, future=True)
    try:
        command.downgrade(cfg, "0030")

        base = datetime(2026, 4, 2, 13, 0, tzinfo=UTC)
        pending_file_id = uuid4()
        archived_file_id = uuid4()
        recycled_file_id = uuid4()
        restored_file_id = uuid4()

        pending_content_id = uuid4()
        archived_content_id = uuid4()
        recycled_content_id = uuid4()
        restored_content_id = uuid4()

        _insert_duplicate_reclaim_item(
            engine,
            file_instance_id=pending_file_id,
            content_id=pending_content_id,
            original_path="/library/pending.jpg",
            archive_path="/bin/pending.jpg",
            item_status="PENDING",
            reclaimed_at=None,
            expires_at=base + timedelta(days=7),
            recycle_path=None,
            recycled_at=None,
            purge_after_at=None,
            purged_at=None,
            restored_at=None,
        )
        _insert_duplicate_reclaim_item(
            engine,
            file_instance_id=archived_file_id,
            content_id=archived_content_id,
            original_path="/library/archived.jpg",
            archive_path="/bin/archived.jpg",
            item_status="ARCHIVED",
            reclaimed_at=base,
            expires_at=base + timedelta(days=7),
            recycle_path=None,
            recycled_at=None,
            purge_after_at=None,
            purged_at=None,
            restored_at=None,
        )
        _insert_duplicate_reclaim_item(
            engine,
            file_instance_id=recycled_file_id,
            content_id=recycled_content_id,
            original_path="/library/recycled.jpg",
            archive_path="/bin/archive-recycled.jpg",
            item_status="RECYCLED",
            reclaimed_at=base - timedelta(days=10),
            expires_at=base - timedelta(days=3),
            recycle_path="/bin/recycled.jpg",
            recycled_at=base - timedelta(days=2),
            purge_after_at=base + timedelta(days=20),
            purged_at=None,
            restored_at=None,
        )
        _insert_duplicate_reclaim_item(
            engine,
            file_instance_id=restored_file_id,
            content_id=restored_content_id,
            original_path="/library/restored.jpg",
            archive_path="/bin/restored.jpg",
            item_status="RESTORED",
            reclaimed_at=base - timedelta(days=5),
            expires_at=base + timedelta(days=2),
            recycle_path=None,
            recycled_at=None,
            purge_after_at=None,
            purged_at=None,
            restored_at=base - timedelta(days=1),
        )

        command.upgrade(cfg, "0031")

        with engine.connect() as conn:
            rows = {
                row["file_instance_id"]: row
                for row in conn.execute(
                    text(
                        """
                        SELECT
                            file_instance_id,
                            original_path,
                            archive_path,
                            item_status,
                            reclaimed_at,
                            expires_at,
                            recycle_path,
                            purged_at,
                            planned_bin_path,
                            bin_path,
                            bin_entered_at,
                            restore_expires_at,
                            bin_state
                        FROM duplicate_reclaim_items
                        ORDER BY file_instance_id
                        """
                    )
                ).mappings()
            }

        pending = rows[pending_file_id]
        assert pending["planned_bin_path"] == pending["archive_path"]
        assert pending["bin_path"] is None
        assert pending["bin_entered_at"] is None
        assert pending["restore_expires_at"] == pending["expires_at"]
        assert pending["bin_state"] == "PENDING_MOVE"

        archived = rows[archived_file_id]
        assert archived["planned_bin_path"] is None
        assert archived["bin_path"] == archived["archive_path"]
        assert archived["bin_entered_at"] == archived["reclaimed_at"]
        assert archived["restore_expires_at"] == archived["expires_at"]
        assert archived["bin_state"] == "IN_BIN"

        recycled = rows[recycled_file_id]
        assert recycled["planned_bin_path"] is None
        assert recycled["bin_path"] == recycled["recycle_path"]
        assert recycled["bin_entered_at"] == recycled["reclaimed_at"]
        assert recycled["restore_expires_at"] == recycled["expires_at"]
        assert recycled["bin_state"] == "IN_BIN"

        restored = rows[restored_file_id]
        assert restored["planned_bin_path"] is None
        assert restored["bin_path"] is None
        assert restored["bin_entered_at"] == restored["reclaimed_at"]
        assert restored["restore_expires_at"] == restored["expires_at"]
        assert restored["bin_state"] == "RESTORED"

        columns_at_0031 = set(_duplicate_reclaim_item_columns(engine))
        assert LEGACY_DUPLICATE_RECLAIM_ITEM_COLUMNS.issubset(columns_at_0031)
        assert PHASE1_DUPLICATE_BIN_ITEM_COLUMNS.issubset(columns_at_0031)

        command.downgrade(cfg, "0030")
        columns_at_0030_again = set(_duplicate_reclaim_item_columns(engine))
        assert LEGACY_DUPLICATE_RECLAIM_ITEM_COLUMNS.issubset(columns_at_0030_again)
        assert PHASE1_DUPLICATE_BIN_ITEM_COLUMNS.issubset(columns_at_0030_again)

        command.upgrade(cfg, "0031")
        columns_after_reupgrade = set(_duplicate_reclaim_item_columns(engine))
        assert LEGACY_DUPLICATE_RECLAIM_ITEM_COLUMNS.issubset(columns_after_reupgrade)
        assert PHASE1_DUPLICATE_BIN_ITEM_COLUMNS.issubset(columns_after_reupgrade)
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
        if original_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_database_url


def test_duplicate_bin_item_backfill_is_idempotent_and_does_not_clobber_phase2_rows(test_database_url: str) -> None:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", test_database_url)

    original_database_url = os.getenv("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_database_url
    engine = create_engine(test_database_url, future=True)
    module = _load_0031_module()
    try:
        command.downgrade(cfg, "0030")

        base = datetime(2026, 4, 2, 14, 0, tzinfo=UTC)
        historical_file_id = uuid4()
        phase2_file_id = uuid4()
        historical_content_id = uuid4()
        phase2_content_id = uuid4()

        _insert_duplicate_reclaim_item(
            engine,
            file_instance_id=historical_file_id,
            content_id=historical_content_id,
            original_path="/library/historical.jpg",
            archive_path="/bin/historical.jpg",
            item_status="ARCHIVED",
            reclaimed_at=base,
            expires_at=base + timedelta(days=7),
            recycle_path=None,
            recycled_at=None,
            purge_after_at=None,
            purged_at=None,
            restored_at=None,
        )
        _insert_duplicate_reclaim_item(
            engine,
            file_instance_id=phase2_file_id,
            content_id=phase2_content_id,
            original_path="/library/phase2.jpg",
            archive_path="/bin/phase2-legacy.jpg",
            item_status="ARCHIVED",
            reclaimed_at=base,
            expires_at=base + timedelta(days=7),
            recycle_path=None,
            recycled_at=None,
            purge_after_at=None,
            purged_at=None,
            restored_at=None,
            planned_bin_path="/bin/phase2-planned.jpg",
            bin_path="/bin/phase2-current.jpg",
            bin_entered_at=base + timedelta(minutes=1),
            restore_expires_at=base + timedelta(days=8),
            bin_state="IN_BIN",
        )

        with engine.begin() as conn:
            module.backfill_duplicate_bin_item_fields(conn)
            module.backfill_duplicate_bin_item_fields(conn)

        with engine.connect() as conn:
            rows = {
                row["file_instance_id"]: row
                for row in conn.execute(
                    text(
                        """
                        SELECT
                            file_instance_id,
                            archive_path,
                            planned_bin_path,
                            bin_path,
                            bin_entered_at,
                            restore_expires_at,
                            bin_state
                        FROM duplicate_reclaim_items
                        ORDER BY file_instance_id
                        """
                    )
                ).mappings()
            }

        historical = rows[historical_file_id]
        assert historical["planned_bin_path"] is None
        assert historical["bin_path"] == historical["archive_path"]
        assert historical["bin_state"] == "IN_BIN"

        phase2 = rows[phase2_file_id]
        assert phase2["planned_bin_path"] == "/bin/phase2-planned.jpg"
        assert phase2["bin_path"] == "/bin/phase2-current.jpg"
        assert phase2["bin_state"] == "IN_BIN"
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
        if original_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_database_url


def test_duplicate_bin_item_backfill_normalizes_reachable_partial_rows(test_database_url: str) -> None:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", test_database_url)

    original_database_url = os.getenv("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_database_url
    engine = create_engine(test_database_url, future=True)
    module = _load_0031_module()
    try:
        command.downgrade(cfg, "0030")

        base = datetime(2026, 4, 2, 15, 0, tzinfo=UTC)
        archived_after_phase2_file_id = uuid4()
        restored_after_phase2_file_id = uuid4()
        recycled_after_phase2_file_id = uuid4()

        archived_after_phase2_content_id = uuid4()
        restored_after_phase2_content_id = uuid4()
        recycled_after_phase2_content_id = uuid4()

        _insert_duplicate_reclaim_item(
            engine,
            file_instance_id=archived_after_phase2_file_id,
            content_id=archived_after_phase2_content_id,
            original_path="/library/archived-after-phase2.jpg",
            archive_path="/bin/archived-after-phase2.jpg",
            item_status="ARCHIVED",
            reclaimed_at=base,
            expires_at=base + timedelta(days=7),
            recycle_path=None,
            recycled_at=None,
            purge_after_at=None,
            purged_at=None,
            restored_at=None,
            planned_bin_path=None,
            bin_path="/bin/archived-after-phase2.jpg",
            bin_entered_at=base,
            restore_expires_at=base + timedelta(days=7),
            bin_state="IN_BIN",
        )
        _insert_duplicate_reclaim_item(
            engine,
            file_instance_id=restored_after_phase2_file_id,
            content_id=restored_after_phase2_content_id,
            original_path="/library/restored-after-phase2.jpg",
            archive_path="/bin/restored-after-phase2.jpg",
            item_status="RESTORED",
            reclaimed_at=base - timedelta(days=5),
            expires_at=base + timedelta(days=2),
            recycle_path=None,
            recycled_at=None,
            purge_after_at=None,
            purged_at=None,
            restored_at=base - timedelta(days=1),
            planned_bin_path="/bin/restored-after-phase2.jpg",
            bin_path="/bin/restored-after-phase2.jpg",
            bin_entered_at=base - timedelta(days=5),
            restore_expires_at=base + timedelta(days=2),
            bin_state="IN_BIN",
        )
        _insert_duplicate_reclaim_item(
            engine,
            file_instance_id=recycled_after_phase2_file_id,
            content_id=recycled_after_phase2_content_id,
            original_path="/library/recycled-after-phase2.jpg",
            archive_path="/bin/archive-recycled-after-phase2.jpg",
            item_status="RECYCLED",
            reclaimed_at=base - timedelta(days=10),
            expires_at=base - timedelta(days=3),
            recycle_path="/bin/recycled-after-phase2.jpg",
            recycled_at=base - timedelta(days=2),
            purge_after_at=base + timedelta(days=20),
            purged_at=None,
            restored_at=None,
            planned_bin_path="/bin/archive-recycled-after-phase2.jpg",
            bin_path="/bin/archive-recycled-after-phase2.jpg",
            bin_entered_at=base - timedelta(days=10),
            restore_expires_at=base - timedelta(days=3),
            bin_state="IN_BIN",
        )

        with engine.begin() as conn:
            module.backfill_duplicate_bin_item_fields(conn)
            module.backfill_duplicate_bin_item_fields(conn)

        with engine.connect() as conn:
            rows = {
                row["file_instance_id"]: row
                for row in conn.execute(
                    text(
                        """
                        SELECT
                            file_instance_id,
                            archive_path,
                            recycle_path,
                            planned_bin_path,
                            bin_path,
                            bin_entered_at,
                            reclaimed_at,
                            restore_expires_at,
                            expires_at,
                            bin_state
                        FROM duplicate_reclaim_items
                        ORDER BY file_instance_id
                        """
                    )
                ).mappings()
            }

        archived_after_phase2 = rows[archived_after_phase2_file_id]
        assert archived_after_phase2["planned_bin_path"] is None
        assert archived_after_phase2["bin_path"] == archived_after_phase2["archive_path"]
        assert archived_after_phase2["bin_entered_at"] == archived_after_phase2["reclaimed_at"]
        assert archived_after_phase2["restore_expires_at"] == archived_after_phase2["expires_at"]
        assert archived_after_phase2["bin_state"] == "IN_BIN"

        restored_after_phase2 = rows[restored_after_phase2_file_id]
        assert restored_after_phase2["planned_bin_path"] is None
        assert restored_after_phase2["bin_path"] is None
        assert restored_after_phase2["bin_entered_at"] == restored_after_phase2["reclaimed_at"]
        assert restored_after_phase2["restore_expires_at"] == restored_after_phase2["expires_at"]
        assert restored_after_phase2["bin_state"] == "RESTORED"

        recycled_after_phase2 = rows[recycled_after_phase2_file_id]
        assert recycled_after_phase2["planned_bin_path"] is None
        assert recycled_after_phase2["bin_path"] == recycled_after_phase2["recycle_path"]
        assert recycled_after_phase2["bin_entered_at"] == recycled_after_phase2["reclaimed_at"]
        assert recycled_after_phase2["restore_expires_at"] == recycled_after_phase2["expires_at"]
        assert recycled_after_phase2["bin_state"] == "IN_BIN"
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
        if original_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_database_url
