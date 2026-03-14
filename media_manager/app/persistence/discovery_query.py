from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from sqlalchemy import case, distinct, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.persistence.models import (
    CanonicalAssignment,
    CanonicalTag,
    FileContent,
    FileInstance,
    FileInstanceStatus,
    Tag,
    TagSource,
)
from media_manager.app.persistence.tag_normalization import normalize_tag_name

SortBy = Literal["created_at", "tag_name", "confidence_score"]
SortOrder = Literal["asc", "desc"]

_IMAGE_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".heic",
    ".heif",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
)
_VIDEO_EXTENSIONS = (
    ".mp4",
    ".mov",
    ".m4v",
    ".avi",
    ".mkv",
    ".wmv",
    ".3gp",
    ".webm",
)


@dataclass(frozen=True)
class DiscoveryQueryParams:
    page: int = 1
    limit: int = 30
    tags: tuple[str, ...] = ()
    sort_by: SortBy = "created_at"
    sort_order: SortOrder = "desc"
    source: TagSource | None = None
    min_confidence: float | None = None


@dataclass(frozen=True)
class DiscoveryItem:
    id: str
    content_id: str
    filename: str
    file_type: str
    media_url: str
    matched_tags: tuple[str, ...]
    top_confidence_score: float | None
    sort_tag_name: str | None
    created_at: datetime


@dataclass(frozen=True)
class DiscoveryPage:
    total_count: int
    page: int
    limit: int
    total_pages: int
    items: tuple[DiscoveryItem, ...]


class DiscoveryQueryService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def query(self, params: DiscoveryQueryParams) -> DiscoveryPage:
        page = max(1, int(params.page))
        limit = min(100, max(1, int(params.limit)))

        sort_by: SortBy = params.sort_by
        if sort_by not in {"created_at", "tag_name", "confidence_score"}:
            raise ValueError("sort_by must be one of: created_at, tag_name, confidence_score.")

        sort_order: SortOrder = params.sort_order
        if sort_order not in {"asc", "desc"}:
            raise ValueError("sort_order must be one of: asc, desc.")

        normalized_tags = self._normalize_tags(params.tags)
        if params.min_confidence is not None and not 0.0 <= float(params.min_confidence) <= 1.0:
            raise ValueError("min_confidence must be within [0.0, 1.0].")

        source_value = params.source.value if params.source is not None else None

        with self._session_factory() as session:
            aggregated = self._aggregated_subquery(
                source_value=source_value,
                min_confidence=params.min_confidence,
                normalized_tags=normalized_tags,
            )

            total_count = int(session.scalar(select(func.count()).select_from(aggregated)) or 0)
            total_pages = (total_count + limit - 1) // limit if total_count > 0 else 0
            offset = (page - 1) * limit

            stmt = select(aggregated)
            stmt = self._apply_ordering(stmt, aggregated, sort_by=sort_by, sort_order=sort_order)
            stmt = stmt.offset(offset).limit(limit)

            rows = session.execute(stmt).all()

        items: list[DiscoveryItem] = []
        for row in rows:
            mapping = row._mapping
            raw_tags = mapping["matched_tags"]
            deduped = sorted({tag for tag in (raw_tags or []) if tag})
            instance_id = str(mapping["canonical_instance_id"])
            path = str(mapping["absolute_path"])
            items.append(
                DiscoveryItem(
                    id=instance_id,
                    content_id=str(mapping["content_id"]),
                    filename=path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1],
                    file_type=str(mapping["file_type"]),
                    media_url=f"/media/{instance_id}",
                    matched_tags=tuple(deduped),
                    top_confidence_score=(
                        round(float(mapping["top_confidence_score"]), 4)
                        if mapping["top_confidence_score"] is not None
                        else None
                    ),
                    sort_tag_name=(
                        str(mapping["sort_tag_name"])
                        if mapping["sort_tag_name"] is not None
                        else None
                    ),
                    created_at=mapping["first_seen_at"],
                )
            )

        return DiscoveryPage(
            total_count=total_count,
            page=page,
            limit=limit,
            total_pages=total_pages,
            items=tuple(items),
        )

    def _normalize_tags(self, tags: tuple[str, ...]) -> tuple[str, ...]:
        normalized = {
            normalize_tag_name(tag)
            for tag in tags
            if tag.strip()
        }
        return tuple(sorted(normalized))

    def _media_type_expr(self):
        lower_path = func.lower(FileInstance.absolute_path)
        image_cond = or_(*[lower_path.like(f"%{ext}") for ext in _IMAGE_EXTENSIONS])
        video_cond = or_(*[lower_path.like(f"%{ext}") for ext in _VIDEO_EXTENSIONS])

        return case(
            (image_cond, "image"),
            (video_cond, "video"),
            else_=None,
        )

    def _aggregated_subquery(
        self,
        *,
        source_value: str | None,
        min_confidence: float | None,
        normalized_tags: tuple[str, ...],
    ):
        latest_assignments = (
            select(
                CanonicalAssignment.content_id.label("content_id"),
                CanonicalAssignment.canonical_instance_id.label("canonical_instance_id"),
                CanonicalAssignment.assignment_id.label("assignment_id"),
                func.row_number()
                .over(
                    partition_by=CanonicalAssignment.content_id,
                    order_by=(
                        CanonicalAssignment.assigned_at.desc(),
                        CanonicalAssignment.assignment_id.desc(),
                    ),
                )
                .label("rn"),
            )
            .subquery()
        )

        media_type_expr = self._media_type_expr()

        stmt = (
            select(
                latest_assignments.c.content_id.label("content_id"),
                latest_assignments.c.canonical_instance_id.label("canonical_instance_id"),
                FileInstance.absolute_path.label("absolute_path"),
                FileContent.first_seen_at.label("first_seen_at"),
                media_type_expr.label("file_type"),
                func.max(CanonicalTag.confidence_score).label("top_confidence_score"),
                func.min(Tag.normalized_name).label("sort_tag_name"),
                func.array_agg(distinct(Tag.normalized_name)).label("matched_tags"),
                func.count(distinct(Tag.normalized_name)).label("matched_tag_count"),
            )
            .join(
                FileInstance,
                FileInstance.file_instance_id == latest_assignments.c.canonical_instance_id,
            )
            .join(
                FileContent,
                FileContent.content_id == latest_assignments.c.content_id,
            )
            .outerjoin(CanonicalTag, CanonicalTag.canonical_id == latest_assignments.c.content_id)
            .outerjoin(Tag, Tag.id == CanonicalTag.tag_id)
            .where(
                latest_assignments.c.rn == 1,
                FileInstance.status == FileInstanceStatus.ACTIVE.value,
                media_type_expr.is_not(None),
            )
            .group_by(
                latest_assignments.c.content_id,
                latest_assignments.c.canonical_instance_id,
                FileInstance.absolute_path,
                FileContent.first_seen_at,
                media_type_expr,
            )
        )

        if source_value is not None:
            stmt = stmt.where(CanonicalTag.source == source_value)
        if min_confidence is not None:
            stmt = stmt.where(CanonicalTag.confidence_score >= float(min_confidence))
        if normalized_tags:
            stmt = stmt.where(Tag.normalized_name.in_(normalized_tags))

        tag_filtered = bool(normalized_tags or source_value is not None or min_confidence is not None)
        if tag_filtered:
            stmt = stmt.having(func.count(distinct(Tag.normalized_name)) > 0)
        if normalized_tags:
            stmt = stmt.having(func.count(distinct(Tag.normalized_name)) == len(normalized_tags))

        return stmt.subquery()

    def _apply_ordering(self, stmt, aggregated, *, sort_by: SortBy, sort_order: SortOrder):
        if sort_by == "created_at":
            primary = aggregated.c.first_seen_at.asc() if sort_order == "asc" else aggregated.c.first_seen_at.desc()
        elif sort_by == "tag_name":
            primary = (
                aggregated.c.sort_tag_name.asc().nulls_last()
                if sort_order == "asc"
                else aggregated.c.sort_tag_name.desc().nulls_last()
            )
        else:
            primary = (
                aggregated.c.top_confidence_score.asc().nulls_last()
                if sort_order == "asc"
                else aggregated.c.top_confidence_score.desc().nulls_last()
            )

        return stmt.order_by(primary, aggregated.c.content_id.asc())
