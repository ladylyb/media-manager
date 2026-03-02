from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError


def test_phase12_tag_enrichment_tables_exist(db_engine) -> None:
    inspector = inspect(db_engine)
    tables = set(inspector.get_table_names())
    assert "tag_enrichment_runs" in tables
    assert "tag_enrichment_items" in tables


def test_phase12_tag_enrichment_columns_and_indexes_exist(db_engine) -> None:
    inspector = inspect(db_engine)
    run_columns = {col["name"] for col in inspector.get_columns("tag_enrichment_runs")}
    item_columns = {col["name"] for col in inspector.get_columns("tag_enrichment_items")}
    run_indexes = {idx["name"] for idx in inspector.get_indexes("tag_enrichment_runs")}
    item_indexes = {idx["name"] for idx in inspector.get_indexes("tag_enrichment_items")}

    assert {
        "id",
        "started_at",
        "completed_at",
        "scope",
        "target_canonical_id",
        "source",
        "batch_size",
        "number_of_items_processed",
        "average_confidence",
        "duration_ms",
        "status",
        "failed_items",
        "error_message",
    }.issubset(run_columns)
    assert {
        "id",
        "run_id",
        "canonical_id",
        "sequence_no",
        "result",
        "tags_emitted_count",
        "average_confidence",
        "previous_version",
        "new_version",
        "started_at",
        "completed_at",
        "duration_ms",
        "error_message",
    }.issubset(item_columns)
    assert {"idx_tag_enrichment_runs_started_at", "idx_tag_enrichment_runs_status"}.issubset(run_indexes)
    assert {"idx_tag_enrichment_items_run_id", "idx_tag_enrichment_items_canonical_id"}.issubset(item_indexes)


def test_phase12_tag_enrichment_unique_constraints_exist(db_engine) -> None:
    inspector = inspect(db_engine)
    item_uniques = {item["name"] for item in inspector.get_unique_constraints("tag_enrichment_items")}
    assert "uq_tag_enrichment_items_run_sequence" in item_uniques
    assert "uq_tag_enrichment_items_run_canonical" in item_uniques


def test_phase12_tag_enrichment_foreign_keys_target_expected_tables(db_engine) -> None:
    inspector = inspect(db_engine)
    run_fks = inspector.get_foreign_keys("tag_enrichment_runs")
    item_fks = inspector.get_foreign_keys("tag_enrichment_items")

    assert any(
        fk.get("referred_table") == "file_contents"
        and fk.get("constrained_columns") == ["target_canonical_id"]
        and fk.get("referred_columns") == ["content_id"]
        for fk in run_fks
    )
    assert any(
        fk.get("referred_table") == "tag_enrichment_runs"
        and fk.get("constrained_columns") == ["run_id"]
        and fk.get("referred_columns") == ["id"]
        for fk in item_fks
    )
    assert any(
        fk.get("referred_table") == "file_contents"
        and fk.get("constrained_columns") == ["canonical_id"]
        and fk.get("referred_columns") == ["content_id"]
        for fk in item_fks
    )


def test_phase12_tag_enrichment_migration_downgrade_order_is_fk_safe() -> None:
    migration_file = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "0012_phase12_tag_enrichment_runs.py"
    )
    content = migration_file.read_text(encoding="utf-8")
    drop_items_index = content.index('op.drop_table("tag_enrichment_items")')
    drop_runs_index = content.index('op.drop_table("tag_enrichment_runs")')
    assert drop_items_index < drop_runs_index


def test_phase12_tag_enrichment_scope_status_result_checks_enforced(db_engine) -> None:
    canonical_id = uuid.uuid4()
    run_id = uuid.uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO file_contents (content_id, sha256_hash) VALUES (:id, :sha)"),
            {"id": canonical_id, "sha": canonical_id.hex.ljust(64, "0")},
        )
    with db_engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO tag_enrichment_runs (
                        id, scope, target_canonical_id, source, batch_size, status
                    ) VALUES (:id, :scope, :target, :source, :batch_size, :status)
                    """
                ),
                {
                    "id": run_id,
                    "scope": "MANY",
                    "target": canonical_id,
                    "source": "system",
                    "batch_size": 10,
                    "status": "STARTED",
                },
            )
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO tag_enrichment_runs (
                    id, scope, target_canonical_id, source, batch_size, status
                ) VALUES (:id, :scope, :target, :source, :batch_size, :status)
                """
            ),
            {
                "id": run_id,
                "scope": "SINGLE",
                "target": canonical_id,
                "source": "system",
                "batch_size": 10,
                "status": "STARTED",
            },
        )
    with db_engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO tag_enrichment_items (
                        id, run_id, canonical_id, sequence_no, result
                    ) VALUES (:id, :run_id, :canonical_id, :sequence_no, :result)
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "run_id": run_id,
                    "canonical_id": canonical_id,
                    "sequence_no": 1,
                    "result": "BROKEN",
                },
            )
