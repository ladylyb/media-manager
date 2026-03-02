from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from media_manager.app.persistence.models import CanonicalTag, FileContent, Tag, TagSource
from media_manager.app.persistence.tagging import (
    CanonicalTagUpsert,
    get_or_create_tag,
    normalize_tag_name,
    query_canonical_tags,
    upsert_canonical_tag,
    upsert_canonical_tags,
)


def test_normalize_tag_name_trims_and_lowercases() -> None:
    assert normalize_tag_name("  SUMMER Trip  ") == "summer trip"


def test_normalize_tag_name_collapses_internal_spaces() -> None:
    assert normalize_tag_name("Summer    Road   Trip") == "summer road trip"


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
    assert second.updated_at is not None


def test_upsert_canonical_tag_rounds_confidence_to_4_decimals(session_factory) -> None:
    canonical_id = uuid.uuid4()
    with session_factory() as session:
        session.add(FileContent(content_id=canonical_id, sha256_hash="aa" * 32))
        session.commit()

    with session_factory() as session:
        upsert_canonical_tag(
            session,
            canonical_id=canonical_id,
            tag_name="Rounded",
            source=TagSource.AI,
            confidence_score=0.123456,
            enrichment_version=1,
        )
        session.commit()
        stored = session.scalar(select(CanonicalTag).where(CanonicalTag.canonical_id == canonical_id))
        assert stored is not None
        assert stored.confidence_score == 0.1235


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
        with pytest.raises(IntegrityError):
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


def test_query_canonical_tags_supports_range_sort_and_any_tag_filter(session_factory) -> None:
    content_a = uuid.uuid4()
    content_b = uuid.uuid4()
    content_c = uuid.uuid4()
    with session_factory() as session:
        session.add_all(
            [
                FileContent(content_id=content_a, sha256_hash="fa" * 32),
                FileContent(content_id=content_b, sha256_hash="fb" * 32),
                FileContent(content_id=content_c, sha256_hash="fc" * 32),
            ]
        )
        session.commit()

    with session_factory() as session:
        upsert_canonical_tag(
            session,
            canonical_id=content_a,
            tag_name="Travel",
            source=TagSource.AI,
            confidence_score=0.70001,
            enrichment_version=1,
        )
        upsert_canonical_tag(
            session,
            canonical_id=content_b,
            tag_name="city",
            source=TagSource.AI,
            confidence_score=0.85,
            enrichment_version=1,
        )
        upsert_canonical_tag(
            session,
            canonical_id=content_c,
            tag_name="portrait",
            source=TagSource.AI,
            confidence_score=0.55,
            enrichment_version=1,
        )
        session.commit()

    with session_factory() as session:
        asc_rows = session.scalars(
            query_canonical_tags(
                min_confidence=0.6,
                max_confidence=0.9,
                sort_confidence="asc",
                normalized_tag_names=[" city ", "travel"],
                source=TagSource.AI,
            )
        ).all()
        desc_rows = session.scalars(
            query_canonical_tags(
                min_confidence=0.6,
                max_confidence=0.9,
                sort_confidence="desc",
                normalized_tag_names=[" city ", "travel"],
                source=TagSource.AI,
            )
        ).all()

    assert [row.canonical_id for row in asc_rows] == [content_a, content_b]
    assert [row.canonical_id for row in desc_rows] == [content_b, content_a]


def test_query_canonical_tags_empty_tag_filter_applies_no_tag_constraint(session_factory) -> None:
    content_a = uuid.uuid4()
    content_b = uuid.uuid4()
    with session_factory() as session:
        session.add_all(
            [
                FileContent(content_id=content_a, sha256_hash="da" * 32),
                FileContent(content_id=content_b, sha256_hash="db" * 32),
            ]
        )
        session.commit()
        upsert_canonical_tag(
            session,
            canonical_id=content_a,
            tag_name="A",
            source=TagSource.AI,
            confidence_score=0.7,
            enrichment_version=1,
        )
        upsert_canonical_tag(
            session,
            canonical_id=content_b,
            tag_name="B",
            source=TagSource.AI,
            confidence_score=0.8,
            enrichment_version=1,
        )
        session.commit()

    with session_factory() as session:
        rows = session.scalars(
            query_canonical_tags(
                min_confidence=0.6,
                max_confidence=0.9,
                normalized_tag_names=[],
                source=TagSource.AI,
            )
        ).all()

    assert [row.canonical_id for row in rows] == [content_a, content_b]


def test_query_canonical_tags_invalid_sort_raises_value_error(session_factory) -> None:
    with pytest.raises(ValueError, match="sort_confidence"):
        query_canonical_tags(sort_confidence="sideways")


def test_query_canonical_tags_applies_deterministic_tie_breakers(session_factory) -> None:
    content_a = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
    content_b = uuid.UUID("00000000-0000-0000-0000-0000000000bb")
    content_c = uuid.UUID("00000000-0000-0000-0000-0000000000cc")
    with session_factory() as session:
        session.add_all(
            [
                FileContent(content_id=content_a, sha256_hash="ca" * 32),
                FileContent(content_id=content_b, sha256_hash="cb" * 32),
                FileContent(content_id=content_c, sha256_hash="cc" * 32),
            ]
        )
        session.commit()
        upsert_canonical_tag(
            session,
            canonical_id=content_c,
            tag_name="alpha",
            source=TagSource.AI,
            confidence_score=0.7777,
            enrichment_version=1,
        )
        upsert_canonical_tag(
            session,
            canonical_id=content_b,
            tag_name="beta",
            source=TagSource.AI,
            confidence_score=0.7777,
            enrichment_version=1,
        )
        upsert_canonical_tag(
            session,
            canonical_id=content_a,
            tag_name="beta",
            source=TagSource.AI,
            confidence_score=0.7777,
            enrichment_version=1,
        )
        session.commit()

    with session_factory() as session:
        rows = session.execute(
            select(CanonicalTag.canonical_id, Tag.normalized_name)
            .join(Tag, Tag.id == CanonicalTag.tag_id)
            .from_statement(
                query_canonical_tags(
                    min_confidence=0.7777,
                    max_confidence=0.7777,
                    sort_confidence="asc",
                    source=TagSource.AI,
                )
                .with_only_columns(CanonicalTag.canonical_id, Tag.normalized_name)
            )
        ).all()

    assert rows == [
        (content_c, "alpha"),
        (content_a, "beta"),
        (content_b, "beta"),
    ]
