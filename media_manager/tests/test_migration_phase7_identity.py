from __future__ import annotations

from sqlalchemy import inspect, text


def test_phase7_identity_tables_exist(db_engine) -> None:
    inspector = inspect(db_engine)
    tables = set(inspector.get_table_names())
    assert "file_contents" in tables
    assert "file_instances" in tables
    assert "media_metadata" in tables


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

