from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
import re

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from media_manager.app.persistence.models import CanonicalTag, Tag, TagSource


def normalize_tag_name(name: str) -> str:
    normalized = re.sub(r"\s+", " ", name.strip().lower())
    if not normalized:
        raise ValueError("Tag name must not be empty after normalization.")
    return normalized


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
    tag = get_or_create_tag(session, tag_name)
    stmt = (
        insert(CanonicalTag)
        .values(
            canonical_id=canonical_id,
            tag_id=tag.id,
            source=source_value,
            confidence_score=confidence_score,
            enrichment_version=enrichment_version,
        )
        .on_conflict_do_update(
            index_elements=[CanonicalTag.canonical_id, CanonicalTag.tag_id, CanonicalTag.source],
            set_={
                "confidence_score": confidence_score,
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
