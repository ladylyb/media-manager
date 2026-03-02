from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from media_manager.app.persistence.discovery_query import DiscoveryQueryParams, DiscoveryQueryService
from media_manager.app.persistence.models import (
    CanonicalAssignment,
    CanonicalTag,
    FileContent,
    FileInstance,
    FileInstanceStatus,
    Tag,
    TagSource,
)


def _seed_base(session) -> dict[str, UUID]:
    base = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)

    content_ids = {
        "a": UUID("10000000-0000-0000-0000-000000000001"),
        "b": UUID("10000000-0000-0000-0000-000000000002"),
        "c": UUID("10000000-0000-0000-0000-000000000003"),
        "d": UUID("10000000-0000-0000-0000-000000000004"),
    }
    instance_ids = {
        "a": UUID("20000000-0000-0000-0000-000000000001"),
        "b": UUID("20000000-0000-0000-0000-000000000002"),
        "c": UUID("20000000-0000-0000-0000-000000000003"),
        "d": UUID("20000000-0000-0000-0000-000000000004"),
    }

    session.add_all(
        [
            FileContent(content_id=content_ids["a"], sha256_hash="aa" * 32, first_seen_at=base),
            FileContent(content_id=content_ids["b"], sha256_hash="bb" * 32, first_seen_at=base + timedelta(minutes=1)),
            FileContent(content_id=content_ids["c"], sha256_hash="cc" * 32, first_seen_at=base + timedelta(minutes=2)),
            FileContent(content_id=content_ids["d"], sha256_hash="dd" * 32, first_seen_at=base + timedelta(minutes=3)),
        ]
    )
    session.flush()

    session.add_all(
        [
            FileInstance(
                file_instance_id=instance_ids["a"],
                content_id=content_ids["a"],
                absolute_path="/gallery/a.jpg",
                filesystem_id="fs",
                first_seen_at=base,
                last_seen_at=base,
                status=FileInstanceStatus.ACTIVE.value,
            ),
            FileInstance(
                file_instance_id=instance_ids["b"],
                content_id=content_ids["b"],
                absolute_path="/gallery/b.mov",
                filesystem_id="fs",
                first_seen_at=base,
                last_seen_at=base,
                status=FileInstanceStatus.ACTIVE.value,
            ),
            FileInstance(
                file_instance_id=instance_ids["c"],
                content_id=content_ids["c"],
                absolute_path="/gallery/c.jpg",
                filesystem_id="fs",
                first_seen_at=base,
                last_seen_at=base,
                status=FileInstanceStatus.ACTIVE.value,
            ),
            FileInstance(
                file_instance_id=instance_ids["d"],
                content_id=content_ids["d"],
                absolute_path="/gallery/d.txt",
                filesystem_id="fs",
                first_seen_at=base,
                last_seen_at=base,
                status=FileInstanceStatus.ACTIVE.value,
            ),
        ]
    )

    session.add_all(
        [
            CanonicalAssignment(
                assignment_id=UUID("30000000-0000-0000-0000-000000000001"),
                content_id=content_ids["a"],
                canonical_instance_id=instance_ids["a"],
                policy_name="FIRST_SEEN",
                policy_version="v1",
                assigned_at=base,
            ),
            CanonicalAssignment(
                assignment_id=UUID("30000000-0000-0000-0000-000000000002"),
                content_id=content_ids["b"],
                canonical_instance_id=instance_ids["b"],
                policy_name="FIRST_SEEN",
                policy_version="v1",
                assigned_at=base + timedelta(seconds=1),
            ),
            CanonicalAssignment(
                assignment_id=UUID("30000000-0000-0000-0000-000000000003"),
                content_id=content_ids["c"],
                canonical_instance_id=instance_ids["c"],
                policy_name="FIRST_SEEN",
                policy_version="v1",
                assigned_at=base + timedelta(seconds=2),
            ),
            CanonicalAssignment(
                assignment_id=UUID("30000000-0000-0000-0000-000000000004"),
                content_id=content_ids["d"],
                canonical_instance_id=instance_ids["d"],
                policy_name="FIRST_SEEN",
                policy_version="v1",
                assigned_at=base + timedelta(seconds=3),
            ),
        ]
    )

    tags = {
        "city": Tag(id=UUID("40000000-0000-0000-0000-000000000001"), name="city", normalized_name="city"),
        "travel": Tag(id=UUID("40000000-0000-0000-0000-000000000002"), name="travel", normalized_name="travel"),
        "portrait": Tag(id=UUID("40000000-0000-0000-0000-000000000003"), name="portrait", normalized_name="portrait"),
    }
    session.add_all(list(tags.values()))

    session.add_all(
        [
            CanonicalTag(
                canonical_id=content_ids["a"],
                tag_id=tags["city"].id,
                source=TagSource.AI.value,
                confidence_score=0.81,
                enrichment_version=1,
            ),
            CanonicalTag(
                canonical_id=content_ids["a"],
                tag_id=tags["travel"].id,
                source=TagSource.AI.value,
                confidence_score=0.91,
                enrichment_version=1,
            ),
            CanonicalTag(
                canonical_id=content_ids["b"],
                tag_id=tags["city"].id,
                source=TagSource.MANUAL.value,
                confidence_score=1.0,
                enrichment_version=1,
            ),
            CanonicalTag(
                canonical_id=content_ids["c"],
                tag_id=tags["travel"].id,
                source=TagSource.AI.value,
                confidence_score=0.6,
                enrichment_version=1,
            ),
            CanonicalTag(
                canonical_id=content_ids["c"],
                tag_id=tags["portrait"].id,
                source=TagSource.AI.value,
                confidence_score=0.7,
                enrichment_version=1,
            ),
        ]
    )

    return {**content_ids, **{f"instance_{k}": v for k, v in instance_ids.items()}}


def test_discovery_query_and_filtering(session_factory) -> None:
    with session_factory.begin() as session:
        ids = _seed_base(session)

    svc = DiscoveryQueryService(session_factory)
    page = svc.query(
        DiscoveryQueryParams(
            tags=(" city ", "travel"),
            sort_by="created_at",
            sort_order="desc",
        )
    )

    assert page.total_count == 1
    assert len(page.items) == 1
    assert page.items[0].id == str(ids["instance_a"])
    assert page.items[0].matched_tags == ("city", "travel")


def test_discovery_query_sorting_modes(session_factory) -> None:
    with session_factory.begin() as session:
        ids = _seed_base(session)

    svc = DiscoveryQueryService(session_factory)

    created = svc.query(DiscoveryQueryParams(sort_by="created_at", sort_order="desc"))
    assert [item.id for item in created.items] == [str(ids["instance_c"]), str(ids["instance_b"]), str(ids["instance_a"])]

    by_tag = svc.query(DiscoveryQueryParams(sort_by="tag_name", sort_order="asc"))
    assert [item.id for item in by_tag.items] == [str(ids["instance_a"]), str(ids["instance_b"]), str(ids["instance_c"])]

    by_conf = svc.query(DiscoveryQueryParams(sort_by="confidence_score", sort_order="desc"))
    assert [item.id for item in by_conf.items] == [str(ids["instance_b"]), str(ids["instance_a"]), str(ids["instance_c"])]


def test_discovery_query_filters_by_source_and_min_confidence(session_factory) -> None:
    with session_factory.begin() as session:
        ids = _seed_base(session)

    svc = DiscoveryQueryService(session_factory)
    source_page = svc.query(DiscoveryQueryParams(source=TagSource.MANUAL))
    assert [item.id for item in source_page.items] == [str(ids["instance_b"])]

    conf_page = svc.query(DiscoveryQueryParams(min_confidence=0.9, sort_by="confidence_score", sort_order="desc"))
    assert [item.id for item in conf_page.items] == [str(ids["instance_b"]), str(ids["instance_a"])]


def test_discovery_query_pagination_defaults_and_out_of_range(session_factory) -> None:
    with session_factory.begin() as session:
        _seed_base(session)

    svc = DiscoveryQueryService(session_factory)

    default_page = svc.query(DiscoveryQueryParams())
    assert default_page.page == 1
    assert default_page.limit == 30
    assert default_page.total_count == 3

    paged = svc.query(DiscoveryQueryParams(page=2, limit=2))
    assert paged.limit == 2
    assert paged.total_pages == 2
    assert len(paged.items) == 1

    out_of_range = svc.query(DiscoveryQueryParams(page=5, limit=2))
    assert out_of_range.page == 5
    assert out_of_range.items == ()


def test_discovery_query_deterministic_tie_breaker(session_factory) -> None:
    with session_factory.begin() as session:
        ids = _seed_base(session)

    svc = DiscoveryQueryService(session_factory)
    first = svc.query(DiscoveryQueryParams(sort_by="created_at", sort_order="asc"))
    second = svc.query(DiscoveryQueryParams(sort_by="created_at", sort_order="asc"))

    assert [item.id for item in first.items] == [item.id for item in second.items]
    assert first.items[0].id == str(ids["instance_a"])


def test_discovery_query_rejects_invalid_min_confidence(session_factory) -> None:
    svc = DiscoveryQueryService(session_factory)

    with pytest.raises(ValueError, match="min_confidence"):
        svc.query(DiscoveryQueryParams(min_confidence=2.0))
