from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from statistics import mean
from time import perf_counter

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.core.logging_config import get_logger
from media_manager.app.persistence.base import transactional_session
from media_manager.app.persistence.models import (
    CanonicalAssignment,
    CanonicalTag,
    FileContent,
    MediaMetadata,
    MetadataCode,
    Tag,
    TagEnrichmentItem,
    TagEnrichmentItemResult,
    TagEnrichmentRun,
    TagEnrichmentScope,
    TagEnrichmentStatus,
    TagSource,
)
from media_manager.app.persistence.tagging import normalize_tag_name, upsert_canonical_tag

logger = get_logger(__name__)


class EnrichmentScope(StrEnum):
    ALL = "ALL"
    SINGLE = "SINGLE"


@dataclass(frozen=True)
class TagEnrichmentCommand:
    scope: EnrichmentScope
    canonical_id: uuid.UUID | None = None
    batch_size: int = 100
    source: TagSource = TagSource.SYSTEM


@dataclass(frozen=True)
class TagEnrichmentSummary:
    run_id: uuid.UUID
    timestamp: datetime
    number_of_items_processed: int
    average_confidence: float | None
    duration_ms: int
    status: str
    failed_items: int
    scope: str

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": str(self.run_id),
            "timestamp": self.timestamp.isoformat(),
            "number_of_items_processed": self.number_of_items_processed,
            "average_confidence": self.average_confidence,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "failed_items": self.failed_items,
            "scope": self.scope,
        }


@dataclass(frozen=True)
class _ProcessedItem:
    average_confidence: float | None
    emitted_confidences: tuple[float, ...]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def run_tag_enrichment(
    session_factory: sessionmaker[Session],
    command: TagEnrichmentCommand,
) -> TagEnrichmentSummary:
    if command.batch_size <= 0:
        raise ValueError("batch_size must be > 0")
    if command.scope == EnrichmentScope.SINGLE and command.canonical_id is None:
        raise ValueError("canonical_id is required for SINGLE scope")
    if command.scope == EnrichmentScope.ALL and command.canonical_id is not None:
        raise ValueError("canonical_id must be omitted for ALL scope")

    target_ids = _resolve_target_canonical_ids(session_factory, command)
    run_id = _create_run(session_factory, command)
    started_at = _utcnow()
    processed_count = 0
    failed_items = 0
    emitted_confidences: list[float] = []
    sequence_no = 0

    try:
        for offset in range(0, len(target_ids), command.batch_size):
            batch = target_ids[offset : offset + command.batch_size]
            logger.info(
                "Tag enrichment batch started",
                extra={
                    "run_id": str(run_id),
                    "phase": "tag_enrichment",
                    "scope": command.scope.value,
                    "source": command.source.value,
                    "batch_size": command.batch_size,
                    "batch_offset": offset,
                    "batch_count": len(batch),
                },
            )
            for canonical_id in batch:
                sequence_no += 1
                processed_count += 1
                try:
                    item = _process_canonical_item(
                        session_factory,
                        run_id=run_id,
                        sequence_no=sequence_no,
                        canonical_id=canonical_id,
                        source=command.source,
                    )
                    emitted_confidences.extend(item.emitted_confidences)
                except Exception as exc:
                    failed_items += 1
                    _record_failed_item(
                        session_factory,
                        run_id=run_id,
                        canonical_id=canonical_id,
                        sequence_no=sequence_no,
                        error_message=str(exc),
                    )
                    logger.exception(
                        "Tag enrichment item failed",
                        extra={
                            "run_id": str(run_id),
                            "phase": "tag_enrichment",
                            "canonical_id": str(canonical_id),
                            "sequence_no": sequence_no,
                        },
                    )

        completed_at = _utcnow()
        duration_ms = int(max(0.0, (completed_at - started_at).total_seconds() * 1000.0))
        avg_conf = round(mean(emitted_confidences), 4) if emitted_confidences else None
        status = (
            TagEnrichmentStatus.COMPLETED_WITH_ERRORS.value
            if failed_items > 0
            else TagEnrichmentStatus.COMPLETED.value
        )
        _finalize_run(
            session_factory,
            run_id=run_id,
            completed_at=completed_at,
            processed_count=processed_count,
            average_confidence=avg_conf,
            duration_ms=duration_ms,
            status=status,
            failed_items=failed_items,
            error_message=None,
        )
        logger.info(
            "Tag enrichment run completed",
            extra={
                "run_id": str(run_id),
                "phase": "tag_enrichment",
                "scope": command.scope.value,
                "source": command.source.value,
                "status": status,
                "processed_count": processed_count,
                "failed_items": failed_items,
                "duration_ms": duration_ms,
            },
        )
        return TagEnrichmentSummary(
            run_id=run_id,
            timestamp=started_at,
            number_of_items_processed=processed_count,
            average_confidence=avg_conf,
            duration_ms=duration_ms,
            status=status,
            failed_items=failed_items,
            scope=command.scope.value,
        )
    except Exception as exc:
        completed_at = _utcnow()
        duration_ms = int(max(0.0, (completed_at - started_at).total_seconds() * 1000.0))
        _finalize_run(
            session_factory,
            run_id=run_id,
            completed_at=completed_at,
            processed_count=processed_count,
            average_confidence=None,
            duration_ms=duration_ms,
            status=TagEnrichmentStatus.FAILED.value,
            failed_items=failed_items + 1,
            error_message=str(exc),
        )
        raise


def _latest_canonical_content_ids_query():
    latest = (
        select(
            CanonicalAssignment.content_id.label("content_id"),
            func.row_number()
            .over(
                partition_by=CanonicalAssignment.content_id,
                order_by=(
                    CanonicalAssignment.assigned_at.desc(),
                    CanonicalAssignment.assignment_id.desc(),
                ),
            )
            .label("rn"),
        ).subquery()
    )
    return (
        select(latest.c.content_id)
        .where(latest.c.rn == 1)
        .order_by(latest.c.content_id.asc())
    )


def _resolve_target_canonical_ids(
    session_factory: sessionmaker[Session],
    command: TagEnrichmentCommand,
) -> list[uuid.UUID]:
    with transactional_session(session_factory) as session:
        all_ids = list(session.scalars(_latest_canonical_content_ids_query()).all())
    if command.scope == EnrichmentScope.ALL:
        return all_ids
    assert command.canonical_id is not None
    if command.canonical_id not in set(all_ids):
        raise ValueError(f"canonical_id is not a current canonical content id: {command.canonical_id}")
    return [command.canonical_id]


def _create_run(
    session_factory: sessionmaker[Session],
    command: TagEnrichmentCommand,
) -> uuid.UUID:
    with transactional_session(session_factory) as session:
        row = TagEnrichmentRun(
            scope=TagEnrichmentScope(command.scope.value).value,
            target_canonical_id=command.canonical_id,
            source=command.source.value,
            batch_size=command.batch_size,
            number_of_items_processed=0,
            average_confidence=None,
            duration_ms=0,
            status=TagEnrichmentStatus.STARTED.value,
            failed_items=0,
            error_message=None,
        )
        session.add(row)
        session.flush()
        return row.id


def _finalize_run(
    session_factory: sessionmaker[Session],
    *,
    run_id: uuid.UUID,
    completed_at: datetime,
    processed_count: int,
    average_confidence: float | None,
    duration_ms: int,
    status: str,
    failed_items: int,
    error_message: str | None,
) -> None:
    with transactional_session(session_factory) as session:
        row = session.get(TagEnrichmentRun, run_id)
        if row is None:
            return
        row.completed_at = completed_at
        row.number_of_items_processed = processed_count
        row.average_confidence = average_confidence
        row.duration_ms = duration_ms
        row.status = status
        row.failed_items = failed_items
        row.error_message = error_message


def _process_canonical_item(
    session_factory: sessionmaker[Session],
    *,
    run_id: uuid.UUID,
    sequence_no: int,
    canonical_id: uuid.UUID,
    source: TagSource,
) -> _ProcessedItem:
    started = _utcnow()
    t0 = perf_counter()
    with transactional_session(session_factory) as session:
        content_exists = session.scalar(select(FileContent.content_id).where(FileContent.content_id == canonical_id))
        if content_exists is None:
            raise ValueError(f"canonical_id not found in file_contents: {canonical_id}")

        desired = _build_desired_tag_confidence_map(session, canonical_id)
        existing = session.execute(
            select(
                CanonicalTag.tag_id,
                CanonicalTag.confidence_score,
                CanonicalTag.enrichment_version,
                Tag.normalized_name,
            )
            .join(Tag, Tag.id == CanonicalTag.tag_id)
            .where(
                CanonicalTag.canonical_id == canonical_id,
                CanonicalTag.source == source.value,
            )
            .order_by(Tag.normalized_name.asc())
        ).all()
        existing_map = {normalized_name: round(float(conf), 4) for _tag_id, conf, _ver, normalized_name in existing}
        desired_map = {name: conf for name, conf in desired}

        previous_version = max((int(ver) for _tag_id, _conf, ver, _name in existing if ver is not None), default=0) or None
        changed = existing_map != desired_map
        new_version = None
        result = TagEnrichmentItemResult.UNCHANGED.value

        if changed:
            next_version = max((int(ver) for _tag_id, _conf, ver, _name in existing if ver is not None), default=0) + 1
            new_version = next_version
            for normalized_name, confidence in desired:
                upsert_canonical_tag(
                    session,
                    canonical_id=canonical_id,
                    tag_name=normalized_name,
                    source=source,
                    confidence_score=confidence,
                    enrichment_version=next_version,
                )
            stale_tag_ids = [tag_id for tag_id, _conf, _ver, name in existing if name not in desired_map]
            if stale_tag_ids:
                session.execute(
                    delete(CanonicalTag).where(
                        CanonicalTag.canonical_id == canonical_id,
                        CanonicalTag.source == source.value,
                        CanonicalTag.tag_id.in_(stale_tag_ids),
                    )
                )
            result = TagEnrichmentItemResult.UPDATED.value

        avg_conf = round(mean(desired_map.values()), 4) if desired_map else None
        duration_ms = int(max(0.0, (perf_counter() - t0) * 1000.0))
        item_row = TagEnrichmentItem(
            run_id=run_id,
            canonical_id=canonical_id,
            sequence_no=sequence_no,
            result=result,
            tags_emitted_count=len(desired),
            average_confidence=avg_conf,
            previous_version=previous_version,
            new_version=new_version,
            started_at=started,
            completed_at=_utcnow(),
            duration_ms=duration_ms,
            error_message=None,
        )
        session.add(item_row)
        logger.info(
            "Tag enrichment item completed",
            extra={
                "run_id": str(run_id),
                "phase": "tag_enrichment",
                "canonical_id": str(canonical_id),
                "sequence_no": sequence_no,
                "result": result,
                "tags_emitted_count": len(desired),
                "previous_version": previous_version,
                "new_version": new_version,
                "duration_ms": duration_ms,
            },
        )
        return _ProcessedItem(
            average_confidence=avg_conf,
            emitted_confidences=tuple(desired_map.values()),
        )


def _record_failed_item(
    session_factory: sessionmaker[Session],
    *,
    run_id: uuid.UUID,
    canonical_id: uuid.UUID,
    sequence_no: int,
    error_message: str,
) -> None:
    started = _utcnow()
    with transactional_session(session_factory) as session:
        session.add(
            TagEnrichmentItem(
                run_id=run_id,
                canonical_id=canonical_id,
                sequence_no=sequence_no,
                result=TagEnrichmentItemResult.FAILED.value,
                tags_emitted_count=0,
                average_confidence=None,
                previous_version=None,
                new_version=None,
                started_at=started,
                completed_at=_utcnow(),
                duration_ms=0,
                error_message=error_message,
            )
        )


def _build_desired_tag_confidence_map(session: Session, canonical_id: uuid.UUID) -> list[tuple[str, float]]:
    rows = session.execute(
        select(MetadataCode.code_type, MediaMetadata.decode_value)
        .join(MediaMetadata, MediaMetadata.code_id == MetadataCode.id)
        .where(MediaMetadata.content_id == canonical_id)
    ).all()
    metadata = {str(code): str(value) for code, value in rows}
    tag_scores: dict[str, float] = {}

    def _add_tag(value: str, confidence: float) -> None:
        try:
            normalized = normalize_tag_name(value)
        except ValueError:
            return
        tag_scores[normalized] = max(tag_scores.get(normalized, 0.0), round(confidence, 4))

    tags_value = metadata.get("TAGS")
    if tags_value:
        for raw_token in re.split(r"[,|;]", tags_value):
            _add_tag(raw_token, 0.95)

    owner = metadata.get("OWNER")
    if owner:
        _add_tag(owner, 0.75)

    context = metadata.get("CONTEXT")
    if context:
        _add_tag(context, 0.75)

    camera_model = metadata.get("CAMERA_MODEL")
    if camera_model:
        _add_tag(camera_model, 0.65)

    return sorted(((name, round(conf, 4)) for name, conf in tag_scores.items()), key=lambda x: x[0])
