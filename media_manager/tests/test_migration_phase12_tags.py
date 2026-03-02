from __future__ import annotations

import uuid

import pytest
from sqlalchemy import inspect, text


def test_phase12_tag_tables_exist(db_engine) -> None:
    inspector = inspect(db_engine)
    tables = set(inspector.get_table_names())
    assert "tags" in tables
    assert "canonical_tags" in tables


def test_phase12_tag_columns_exist(db_engine) -> None:
    inspector = inspect(db_engine)
    tag_columns = {col["name"] for col in inspector.get_columns("tags")}
    canonical_tag_columns = {col["name"] for col in inspector.get_columns("canonical_tags")}

    assert {"id", "name", "normalized_name", "created_at"}.issubset(tag_columns)
    assert {
        "canonical_id",
        "tag_id",
        "source",
        "confidence_score",
        "enrichment_version",
        "created_at",
        "updated_at",
    }.issubset(canonical_tag_columns)


def test_phase12_tag_constraints_exist(db_engine) -> None:
    inspector = inspect(db_engine)
    unique_tags = {item["name"] for item in inspector.get_unique_constraints("tags")}
    unique_canonical_tags = {item["name"] for item in inspector.get_unique_constraints("canonical_tags")}
    canonical_tags_pk = inspector.get_pk_constraint("canonical_tags")
    checks = {item["name"] for item in inspector.get_check_constraints("canonical_tags")}

    assert "uq_tags_normalized_name" in unique_tags
    has_unique_triplet = "uq_canonical_tags_canonical_tag_source" in unique_canonical_tags
    pk_columns = set(canonical_tags_pk.get("constrained_columns") or [])
    has_pk_triplet = pk_columns == {"canonical_id", "tag_id", "source"}
    assert has_unique_triplet or has_pk_triplet
    assert "ck_canonical_tags_source" in checks
    assert "ck_canonical_tags_confidence_range" in checks


def test_phase12_confidence_constraint_enforced(db_engine) -> None:
    canonical_id = uuid.uuid4()
    tag_id = uuid.uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO file_contents (content_id, sha256_hash) VALUES (:content_id, :sha256_hash)"),
            {"content_id": canonical_id, "sha256_hash": f"{canonical_id.hex:0<64}"},
        )
        conn.execute(
            text("INSERT INTO tags (id, name, normalized_name) VALUES (:id, :name, :normalized_name)"),
            {"id": tag_id, "name": "Nature", "normalized_name": "nature"},
        )
        with pytest.raises(Exception):
            conn.execute(
                text(
                    """
                    INSERT INTO canonical_tags (
                        canonical_id, tag_id, source, confidence_score, enrichment_version
                    ) VALUES (:canonical_id, :tag_id, :source, :confidence_score, :enrichment_version)
                    """
                ),
                {
                    "canonical_id": canonical_id,
                    "tag_id": tag_id,
                    "source": "ai",
                    "confidence_score": 1.5,
                    "enrichment_version": 1,
                },
            )
