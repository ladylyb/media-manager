from __future__ import annotations

from sqlalchemy import inspect, text


def test_phase12_search_indexes_exist(db_engine) -> None:
    inspector = inspect(db_engine)

    tags_indexes = {item["name"] for item in inspector.get_indexes("tags")}
    canonical_tags_indexes = {item["name"] for item in inspector.get_indexes("canonical_tags")}
    file_content_indexes = {item["name"] for item in inspector.get_indexes("file_contents")}

    assert "idx_tags_normalized_name" in tags_indexes
    assert "idx_tags_normalized_name_trgm" in tags_indexes
    assert {
        "idx_canonical_tags_tag_id",
        "idx_canonical_tags_tag_canonical_confidence",
        "idx_canonical_tags_canonical_confidence",
    }.issubset(canonical_tags_indexes)
    assert "idx_file_contents_first_seen_content" in file_content_indexes


def test_phase12_search_trigram_index_is_gin(db_engine) -> None:
    with db_engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND tablename = 'tags'
                  AND indexname = 'idx_tags_normalized_name_trgm'
                """
            )
        ).first()

    assert row is not None
    indexdef = row[0]
    assert "USING gin" in indexdef
    assert "gin_trgm_ops" in indexdef


def test_phase12_search_index_sql_is_idempotent(db_engine) -> None:
    with db_engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tags_normalized_name ON tags (normalized_name)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_canonical_tags_tag_id ON canonical_tags (tag_id)"))
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_canonical_tags_tag_canonical_confidence
                ON canonical_tags (tag_id, canonical_id, confidence_score DESC)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_canonical_tags_canonical_confidence
                ON canonical_tags (canonical_id, confidence_score DESC)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_file_contents_first_seen_content
                ON file_contents (first_seen_at DESC, content_id ASC)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_tags_normalized_name_trgm
                ON tags USING GIN (normalized_name gin_trgm_ops)
                """
            )
        )
