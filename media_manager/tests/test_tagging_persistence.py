from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from media_manager.app.persistence.models import CanonicalTag, FileContent, Tag, TagSource
from media_manager.app.persistence.tagging import (
    CanonicalTagUpsert,
    get_or_create_tag,
    normalize_tag_name,
    upsert_canonical_tag,
    upsert_canonical_tags,
)


def test_normalize_tag_name_trims_and_lowercases() -> None:
    assert normalize_tag_name("  SUMMER Trip  ") == "summer trip"


def test_normalize_tag_name_rejects_empty() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        normalize_tag_name("   ")


def test_get_or_create_tag_is_idempotent_by_normalized_name(session_factory) -> None:
    with session_factory() as session:
        first = get_or_create_tag(session, "  Foo  ")
        session.commit()
        first_id = first.id

    with session_factory() as session:
        second = get_or_create_tag(session, "foo")
        session.commit()
        second_id = second.id
        all_tags = session.scalars(select(Tag)).all()

    assert first_id == second_id
    assert len(all_tags) == 1
    assert all_tags[0].normalized_name == "foo"


def test_upsert_canonical_tag_updates_on_replay(session_factory) -> None:
    canonical_id = uuid.uuid4()
    with session_factory() as session:
        session.add(FileContent(content_id=canonical_id, sha256_hash="a" * 64))
        session.commit()

    with session_factory() as session:
        first = upsert_canonical_tag(
            session,
            canonical_id=canonical_id,
            tag_name="Nature",
            source=TagSource.AI,
            confidence_score=0.2,
            enrichment_version=1,
        )
        first_created_at = first.created_at
        session.commit()

    with session_factory() as session:
        second = upsert_canonical_tag(
            session,
            canonical_id=canonical_id,
            tag_name="nature",
            source=TagSource.AI,
            confidence_score=0.9,
            enrichment_version=2,
        )
        session.commit()
        rows = session.scalars(select(CanonicalTag)).all()

    assert len(rows) == 1
    assert second.confidence_score == 0.9
    assert second.enrichment_version == 2
    assert second.created_at == first_created_at
    assert second.updated_at >= second.created_at


def test_upsert_canonical_tag_allows_distinct_sources_for_same_tag(session_factory) -> None:
    canonical_id = uuid.uuid4()
    with session_factory() as session:
        session.add(FileContent(content_id=canonical_id, sha256_hash="b" * 64))
        session.commit()

    with session_factory() as session:
        upsert_canonical_tag(
            session,
            canonical_id=canonical_id,
            tag_name="Portrait",
            source=TagSource.AI,
            confidence_score=0.7,
            enrichment_version=1,
        )
        upsert_canonical_tag(
            session,
            canonical_id=canonical_id,
            tag_name=" portrait ",
            source=TagSource.MANUAL,
            confidence_score=1.0,
            enrichment_version=1,
        )
        session.commit()
        rows = session.scalars(select(CanonicalTag).order_by(CanonicalTag.source.asc())).all()

    assert len(rows) == 2
    assert [row.source for row in rows] == ["ai", "manual"]


def test_upsert_canonical_tag_rejects_out_of_range_confidence(session_factory) -> None:
    canonical_id = uuid.uuid4()
    with session_factory() as session:
        session.add(FileContent(content_id=canonical_id, sha256_hash="c" * 64))
        session.commit()

    with session_factory() as session:
        with pytest.raises(Exception):
            upsert_canonical_tag(
                session,
                canonical_id=canonical_id,
                tag_name="City",
                source=TagSource.AI,
                confidence_score=1.2,
                enrichment_version=1,
            )
        session.rollback()


def test_upsert_canonical_tags_batch_is_deterministic_and_idempotent(session_factory) -> None:
    content_a = uuid.uuid4()
    content_b = uuid.uuid4()
    with session_factory() as session:
        session.add_all(
            [
                FileContent(content_id=content_a, sha256_hash="d" * 64),
                FileContent(content_id=content_b, sha256_hash="e" * 64),
            ]
        )
        session.commit()

    rows = [
        CanonicalTagUpsert(
            canonical_id=content_b,
            tag_name="Travel",
            source=TagSource.AI,
            confidence_score=0.4,
            enrichment_version=1,
        ),
        CanonicalTagUpsert(
            canonical_id=content_a,
            tag_name="travel",
            source=TagSource.MANUAL,
            confidence_score=1.0,
            enrichment_version=1,
        ),
    ]
    with session_factory() as session:
        upsert_canonical_tags(session, rows)
        upsert_canonical_tags(session, list(reversed(rows)))
        session.commit()
        tags = session.scalars(select(Tag)).all()
        links = session.scalars(select(CanonicalTag)).all()

    assert len(tags) == 1
    assert len(links) == 2
