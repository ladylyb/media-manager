from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from media_manager.app.persistence.models import CanonicalTag, Tag, TagSource
from media_manager.app.persistence.tag_normalization import normalize_tag_name


def _round_confidence(value: float) -> float:
    return round(float(value), 4)


def get_or_create_tag(session: Session, name: str) -> Tag:
    normalized = normalize_tag_name(name)
    stmt = (
        insert(Tag)
        .values(name=name.strip(), normalized_name=normalized)
        .on_conflict_do_update(
            index_elements=[Tag.normalized_name],
            set_={"name": insert(Tag).excluded.name},
        )
        .returning(Tag.id)
    )
    tag_id = session.execute(stmt).scalar_one()
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise RuntimeError(f"Tag upsert returned missing row for normalized_name={normalized!r}.")
    return tag


def upsert_canonical_tag(
    session: Session,
    *,
    canonical_id: uuid.UUID,
    tag_name: str,
    source: TagSource | str,
    confidence_score: float,
    enrichment_version: int,
) -> CanonicalTag:
    source_value = TagSource(source).value if isinstance(source, str) else source.value
    rounded_confidence = _round_confidence(confidence_score)
    tag = get_or_create_tag(session, tag_name)
    stmt = (
        insert(CanonicalTag)
        .values(
            canonical_id=canonical_id,
            tag_id=tag.id,
            source=source_value,
            confidence_score=rounded_confidence,
            enrichment_version=enrichment_version,
        )
        .on_conflict_do_update(
            index_elements=[CanonicalTag.canonical_id, CanonicalTag.tag_id, CanonicalTag.source],
            set_={
                "confidence_score": rounded_confidence,
                "enrichment_version": enrichment_version,
                "updated_at": func.now(),
            },
        )
    )
    session.execute(stmt)
    row = session.scalar(
        select(CanonicalTag)
        .where(
            CanonicalTag.canonical_id == canonical_id,
            CanonicalTag.tag_id == tag.id,
            CanonicalTag.source == source_value,
        )
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise RuntimeError(
            f"CanonicalTag upsert returned missing row for canonical_id={canonical_id} tag_id={tag.id} source={source_value}."
        )
    return row


@dataclass(frozen=True)
class CanonicalTagUpsert:
    canonical_id: uuid.UUID
    tag_name: str
    source: TagSource | str
    confidence_score: float
    enrichment_version: int


def query_canonical_tags(
    *,
    min_confidence: float | None = None,
    max_confidence: float | None = None,
    sort_confidence: str = "asc",
    normalized_tag_names: Iterable[str] | None = None,
    source: TagSource | str | None = None,
    canonical_id: uuid.UUID | None = None,
) -> Select[tuple[CanonicalTag]]:
    """Build deterministic canonical-tag query filters.

    `normalized_tag_names` uses ANY semantics. When provided as an empty iterable,
    no tag-name filter is applied.
    """
    stmt = select(CanonicalTag).join(Tag, Tag.id == CanonicalTag.tag_id)

    if min_confidence is not None:
        stmt = stmt.where(CanonicalTag.confidence_score >= _round_confidence(min_confidence))
    if max_confidence is not None:
        stmt = stmt.where(CanonicalTag.confidence_score <= _round_confidence(max_confidence))

    if normalized_tag_names is not None:
        normalized_values = sorted(
            {
                normalize_tag_name(value)
                for value in normalized_tag_names
            }
        )
        if normalized_values:
            stmt = stmt.where(Tag.normalized_name.in_(normalized_values))

    if source is not None:
        source_value = TagSource(source).value if isinstance(source, str) else source.value
        stmt = stmt.where(CanonicalTag.source == source_value)

    if canonical_id is not None:
        stmt = stmt.where(CanonicalTag.canonical_id == canonical_id)

    sort = sort_confidence.strip().lower()
    if sort not in {"asc", "desc"}:
        raise ValueError("sort_confidence must be 'asc' or 'desc'.")
    if sort == "asc":
        stmt = stmt.order_by(
            CanonicalTag.confidence_score.asc(),
            Tag.normalized_name.asc(),
            CanonicalTag.canonical_id.asc(),
        )
    else:
        stmt = stmt.order_by(
            CanonicalTag.confidence_score.desc(),
            Tag.normalized_name.asc(),
            CanonicalTag.canonical_id.asc(),
        )
    return stmt


def upsert_canonical_tags(session: Session, rows: Iterable[CanonicalTagUpsert]) -> list[CanonicalTag]:
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            str(row.canonical_id),
            normalize_tag_name(row.tag_name),
            TagSource(row.source).value if isinstance(row.source, str) else row.source.value,
        ),
    )
    return [
        upsert_canonical_tag(
            session,
            canonical_id=row.canonical_id,
            tag_name=row.tag_name,
            source=row.source,
            confidence_score=row.confidence_score,
            enrichment_version=row.enrichment_version,
        )
        for row in sorted_rows
    ]
