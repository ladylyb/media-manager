from __future__ import annotations

from sqlalchemy import inspect, text


def test_phase7_identity_tables_exist(db_engine) -> None:
    inspector = inspect(db_engine)
    tables = set(inspector.get_table_names())
    assert "file_contents" in tables
    assert "file_instances" in tables
    assert "media_metadata" in tables
    assert "apply_audit_runs" in tables
    assert "apply_audit_items" in tables


def test_media_metadata_uses_content_id_fk(db_engine) -> None:
    inspector = inspect(db_engine)
    columns = {col["name"] for col in inspector.get_columns("media_metadata")}
    assert "content_id" in columns
    assert "file_hash" not in columns


def test_no_duplicate_content_rows_for_same_hash(db_engine) -> None:
    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT sha256_hash, COUNT(*)
                FROM file_contents
                GROUP BY sha256_hash
                HAVING COUNT(*) > 1
                """
            )
        ).fetchall()
    assert rows == []


def test_phase8_apply_audit_columns_exist(db_engine) -> None:
    inspector = inspect(db_engine)
    run_columns = {col["name"] for col in inspector.get_columns("apply_audit_runs")}
    item_columns = {col["name"] for col in inspector.get_columns("apply_audit_items")}
    assert {"id", "run_id", "status", "error_message", "total_actions", "applied_actions", "skipped_actions"}.issubset(
        run_columns
    )
    assert {"id", "run_id", "planned_action_id", "result", "error_message"}.issubset(item_columns)

