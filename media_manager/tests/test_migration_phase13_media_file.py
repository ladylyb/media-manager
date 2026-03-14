from __future__ import annotations

import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError


def test_phase13_media_file_table_columns_and_indexes_exist(db_engine) -> None:
    inspector = inspect(db_engine)

    tables = set(inspector.get_table_names())
    assert "media_file" in tables

    columns = {col["name"] for col in inspector.get_columns("media_file")}
    assert {
        "id",
        "discovered_path",
        "current_path",
        "size_bytes",
        "hash_sha256",
        "discovered_at",
        "ingested_at",
        "status",
        "quarantined_at",
        "deleted_at",
    }.issubset(columns)
    assert "canonical_id" not in columns

    indexes = {idx["name"] for idx in inspector.get_indexes("media_file")}
    assert {"idx_media_file_hash_sha256_not_null", "idx_media_file_status", "uq_media_file_current_path_live"}.issubset(
        indexes
    )
    assert "idx_media_file_canonical_id" not in indexes


def test_phase13_media_file_constraints_exist(db_engine) -> None:
    inspector = inspect(db_engine)
    checks = {item["name"] for item in inspector.get_check_constraints("media_file")}
    fks = inspector.get_foreign_keys("media_file")

    assert {
        "ck_media_file_status",
        "ck_media_file_lifecycle_consistency",
        "ck_media_file_ingest_after_discovery",
    }.issubset(checks)
    assert "ck_media_file_not_self_canonical" not in checks
    assert all(fk.get("name") != "fk_media_file_canonical_id" for fk in fks)


def test_phase13_media_file_status_defaults_to_ingested(db_engine) -> None:
    with db_engine.begin() as conn:
        row = conn.execute(
            text("INSERT INTO media_file DEFAULT VALUES RETURNING id, status"),
        ).first()

    assert row is not None
    value = row[0]
    assert isinstance(value, uuid.UUID)
    assert row[1] == "INGESTED"


def test_phase13_media_file_status_and_lifecycle_checks_enforced(db_engine) -> None:
    with db_engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO media_file (status)
                    VALUES ('BROKEN')
                    """
                )
            )

    with db_engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO media_file (status, deleted_at)
                    VALUES ('INGESTED', now())
                    """
                )
            )

    with db_engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO media_file (status)
                    VALUES ('DELETED')
                    """
                )
            )


def test_phase13_media_file_live_path_index_enforced(db_engine) -> None:
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO media_file (current_path, status)
                VALUES (:path, 'INGESTED')
                """
                ),
                {"path": "/tmp/a.jpg"},
            )
    with db_engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO media_file (current_path, status)
                    VALUES (:path, 'PROCESSED')
                    """
                ),
                {"path": "/tmp/a.jpg"},
            )

    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO media_file (current_path, status, deleted_at)
                VALUES (:path, 'DELETED', now())
                """
            ),
            {"path": "/tmp/a.jpg"},
        )
