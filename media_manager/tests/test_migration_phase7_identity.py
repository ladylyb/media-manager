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
    assert "canonical_assignments" in tables
    assert "canonical_recompute_runs" in tables
    assert "canonical_recompute_items" in tables


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


def test_phase81_canonical_assignment_indexes_exist(db_engine) -> None:
    inspector = inspect(db_engine)
    names = {idx["name"] for idx in inspector.get_indexes("canonical_assignments")}
    assert {"idx_canonical_assignments_content_id", "idx_canonical_assignments_instance_id", "idx_canonical_assignments_latest"}.issubset(
        names
    )


def test_phase81_backfill_creates_one_assignment_per_content(db_engine) -> None:
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO file_contents (content_id, sha256_hash, first_seen_at, canonical_file_instance_id)
                VALUES
                  ('00000000-0000-0000-0000-000000000001', 'h1', now(), NULL),
                  ('00000000-0000-0000-0000-000000000002', 'h2', now(), NULL)
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO file_instances (
                    file_instance_id, content_id, absolute_path, first_seen_at, last_seen_at, status
                )
                VALUES
                  ('00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000000001', '/tmp/a', now(), now(), 'ACTIVE'),
                  ('00000000-0000-0000-0000-000000000201', '00000000-0000-0000-0000-000000000002', '/tmp/b', now(), now(), 'ACTIVE')
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO canonical_assignments (
                    assignment_id, content_id, canonical_instance_id, policy_name, policy_version, assigned_at
                )
                SELECT
                    fc.content_id, fc.content_id, fi.file_instance_id, 'FIRST_SEEN', 'v1', now()
                FROM file_contents fc
                JOIN file_instances fi ON fi.content_id = fc.content_id
                """
            )
        )
        count_content = conn.execute(text("SELECT COUNT(*) FROM file_contents")).scalar_one()
        count_assignment = conn.execute(text("SELECT COUNT(*) FROM canonical_assignments")).scalar_one()
        assert count_assignment == count_content

