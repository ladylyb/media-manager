from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from media_manager.app.persistence.base import create_db_engine, create_session_factory
from media_manager.app.persistence.materialized_reads import fetch_canonical_metadata, refresh_materialized_view


def _insert_assignment_fixture(db_url: str) -> tuple[uuid.UUID, uuid.UUID]:
    engine = create_db_engine(db_url)
    content_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    winner_instance_id = uuid.UUID("cccccccc-cccc-cccc-cccc-ccccccccccc2")

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO file_contents (content_id, sha256_hash)
                VALUES (:content_id, :sha)
                """
            ),
            {"content_id": content_id, "sha": "f" * 64},
        )

        for suffix, instance_id in (
            ("1", uuid.UUID("cccccccc-cccc-cccc-cccc-ccccccccccc1")),
            ("2", winner_instance_id),
            ("3", uuid.UUID("cccccccc-cccc-cccc-cccc-ccccccccccc3")),
        ):
            path = f"/tmp/determinism/{suffix}.jpg"
            conn.execute(
                text(
                    """
                    INSERT INTO file_instances (file_instance_id, content_id, absolute_path, status)
                    VALUES (:instance_id, :content_id, :path, 'ACTIVE')
                    """
                ),
                {"instance_id": instance_id, "content_id": content_id, "path": path},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO content_objects (hash, size_bytes)
                    VALUES (:hash, :size)
                    ON CONFLICT (hash) DO NOTHING
                    """
                ),
                {"hash": f"legacy-{suffix}", "size": 100 + int(suffix)},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO files (id, path, mime_type, size_bytes, hash, is_duplicate)
                    VALUES (:id, :path, 'image/jpeg', :size, :hash, false)
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "path": path,
                    "size": 100 + int(suffix),
                    "hash": f"legacy-{suffix}",
                },
            )

        tie_ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        older_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)

        conn.execute(
            text(
                """
                INSERT INTO canonical_assignments (
                    assignment_id, content_id, canonical_instance_id, policy_name, policy_version, assigned_at
                ) VALUES
                    (:a0, :content_id, :i3, 'FIRST_SEEN', 'v1', :older_ts),
                    (:a1, :content_id, :i1, 'FIRST_SEEN', 'v1', :tie_ts),
                    (:a2, :content_id, :i2, 'FIRST_SEEN', 'v1', :tie_ts)
                """
            ),
            {
                "a0": uuid.UUID("00000000-0000-0000-0000-0000000000f0"),
                "a1": uuid.UUID("00000000-0000-0000-0000-0000000000f1"),
                "a2": uuid.UUID("00000000-0000-0000-0000-0000000000f2"),
                "content_id": content_id,
                "i1": uuid.UUID("cccccccc-cccc-cccc-cccc-ccccccccccc1"),
                "i2": winner_instance_id,
                "i3": uuid.UUID("cccccccc-cccc-cccc-cccc-ccccccccccc3"),
                "older_ts": older_ts,
                "tie_ts": tie_ts,
            },
        )

    engine.dispose()
    return content_id, winner_instance_id


def test_mv_latest_assignment_selection_is_deterministic(test_database_url: str, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    content_id, winner_instance_id = _insert_assignment_fixture(test_database_url)

    engine = create_db_engine(test_database_url)
    refresh_materialized_view(engine, concurrently=False)

    with create_session_factory(engine)() as session:
        base_rows = fetch_canonical_metadata(session, use_mv=False, sample_size=0, use_cache=False)
        mv_rows = fetch_canonical_metadata(session, use_mv=True, sample_size=0, use_cache=False)

        uniqueness_check = session.execute(
            text(
                """
                SELECT
                    COUNT(*) AS total_count,
                    COUNT(DISTINCT assignment_id) AS distinct_ids
                FROM canonical_assignments
                """
            )
        ).mappings().one()
        tie_check = session.execute(
            text(
                """
                SELECT COUNT(*) AS duplicate_order_keys
                FROM (
                    SELECT assigned_at, assignment_id
                    FROM canonical_assignments
                    GROUP BY assigned_at, assignment_id
                    HAVING COUNT(*) > 1
                ) t
                """
            )
        ).mappings().one()

    target_base = [row for row in base_rows if row.content_id == content_id]
    target_mv = [row for row in mv_rows if row.content_id == content_id]

    assert len(target_base) == 1
    assert target_base == target_mv
    assert target_base[0].canonical_instance_id == winner_instance_id
    assert int(uniqueness_check["total_count"]) == int(uniqueness_check["distinct_ids"])
    assert int(tie_check["duplicate_order_keys"]) == 0
