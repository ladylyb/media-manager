from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean
import time
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
from media_manager.app.persistence.tag_normalization import normalize_tag_name
from media_manager.app.persistence.tagging import upsert_canonical_tag

logger = get_logger(__name__)
_TAG_PROGRESS_EVERY = 100


# Backward-compatible alias used by existing internal imports.
EnrichmentScope = TagEnrichmentScope


@dataclass(frozen=True)
class TagEnrichmentCommand:
    scope: TagEnrichmentScope
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


@dataclass(frozen=True)
class EnrichmentLastRunRecord:
    run_id: uuid.UUID
    canonical_id: uuid.UUID
    run_started_at: datetime
    run_status: str
    scope: str
    source: str
    sequence_no: int
    result: str
    duration_ms: int
    previous_version: int | None
    new_version: int | None
    previous_confidence: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": str(self.run_id),
            "canonical_id": str(self.canonical_id),
            "run_started_at": self.run_started_at.isoformat(),
            "run_status": self.run_status,
            "scope": self.scope,
            "source": self.source,
            "sequence_no": self.sequence_no,
            "result": self.result,
            "duration_ms": self.duration_ms,
            "previous_version": self.previous_version,
            "new_version": self.new_version,
            "previous_confidence": self.previous_confidence,
        }


@dataclass(frozen=True)
class EnrichmentDelta:
    run_id: uuid.UUID
    canonical_id: uuid.UUID
    source: str
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed_confidence: tuple[dict[str, float | str], ...]
    version_before: int | None
    version_after: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": str(self.run_id),
            "canonical_id": str(self.canonical_id),
            "source": self.source,
            "added": list(self.added),
            "removed": list(self.removed),
            "changed_confidence": list(self.changed_confidence),
            "version_before": self.version_before,
            "version_after": self.version_after,
        }


@dataclass(frozen=True)
class EnrichmentReprocessingRecord:
    run_id: uuid.UUID
    canonical_id: uuid.UUID
    source: str
    run_started_at: datetime
    sequence_no: int
    result: str
    duration_ms: int
    previous_version: int | None
    new_version: int | None
    previous_confidence: float | None
    tags_emitted_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": str(self.run_id),
            "canonical_id": str(self.canonical_id),
            "source": self.source,
            "run_started_at": self.run_started_at.isoformat(),
            "sequence_no": self.sequence_no,
            "result": self.result,
            "duration_ms": self.duration_ms,
            "previous_version": self.previous_version,
            "new_version": self.new_version,
            "previous_confidence": self.previous_confidence,
            "tags_emitted_count": self.tags_emitted_count,
        }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def run_tag_enrichment(
    session_factory: sessionmaker[Session],
    command: TagEnrichmentCommand,
) -> TagEnrichmentSummary:
    if command.batch_size <= 0:
        raise ValueError("batch_size must be > 0")
    if command.scope == TagEnrichmentScope.SINGLE and command.canonical_id is None:
        raise ValueError("canonical_id is required for SINGLE scope")
    if command.scope == TagEnrichmentScope.ALL and command.canonical_id is not None:
        raise ValueError("canonical_id must be omitted for ALL scope")

    target_ids = _resolve_target_canonical_ids(session_factory, command)
    run_id, started_at = _create_run(session_factory, command)
    processed_count = 0
    failed_items = 0
    emitted_confidences: list[float] = []
    sequence_no = 0

    try:
        logger.info(
            "Run started",
            extra={
                "run_id": str(run_id),
                "phase": "tag_enrichment",
                "stage": "enrich",
                "status": "running",
                "scope": command.scope.value,
                "source": command.source.value,
                "batch_size": command.batch_size,
                "total_count": len(target_ids),
            },
        )
        started_at_perf = time.time()
        for offset in range(0, len(target_ids), command.batch_size):
            batch = target_ids[offset : offset + command.batch_size]
            logger.info(
                "Tag enrichment batch started",
                extra={
                    "run_id": str(run_id),
                    "phase": "tag_enrichment",
                    "stage": "enrich",
                    "status": "running",
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
                        source=command.source,
                        error_message=str(exc),
                    )
                    logger.exception(
                        "Tag enrichment item failed",
                        extra={
                            "run_id": str(run_id),
                            "phase": "tag_enrichment",
                            "stage": "enrich",
                            "status": "error",
                            "canonical_id": str(canonical_id),
                            "sequence_no": sequence_no,
                        },
                    )
                if target_ids and (processed_count % _TAG_PROGRESS_EVERY == 0 or processed_count == len(target_ids)):
                    elapsed_seconds = max(time.time() - started_at_perf, 0.000001)
                    progress_percent = (processed_count / len(target_ids)) * 100.0
                    throughput_fps = processed_count / elapsed_seconds
                    logger.info(
                        (
                            f"Progress: {processed_count}/{len(target_ids)} items ({progress_percent:.1f}%) | "
                            f"{throughput_fps:.1f} items/sec | elapsed {elapsed_seconds:.1f}s"
                        ),
                        extra={
                            "run_id": str(run_id),
                            "phase": "tag_enrichment",
                            "stage": "enrich",
                            "status": "running",
                            "scope": command.scope.value,
                            "source": command.source.value,
                            "processed_count": processed_count,
                            "total_count": len(target_ids),
                            "progress_percent": progress_percent,
                            "elapsed_seconds": elapsed_seconds,
                            "throughput_fps": throughput_fps,
                            "failed_items": failed_items,
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
                "stage": "finalize",
                "scope": command.scope.value,
                "source": command.source.value,
                "status": status,
                "processed_count": processed_count,
                "total_count": len(target_ids),
                "progress_percent": 100.0 if target_ids else None,
                "elapsed_seconds": max(time.time() - started_at_perf, 0.000001),
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
        logger.exception(
            "Tag enrichment run failed",
            extra={
                "run_id": str(run_id),
                "phase": "tag_enrichment",
                "stage": "finalize",
                "scope": command.scope.value,
                "source": command.source.value,
                "status": TagEnrichmentStatus.FAILED.value,
                "processed_count": processed_count,
                "total_count": len(target_ids),
                "elapsed_seconds": max(time.time() - started_at_perf, 0.000001),
            },
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
    if command.scope == TagEnrichmentScope.ALL:
        return all_ids
    assert command.canonical_id is not None
    if command.canonical_id not in set(all_ids):
        raise ValueError(f"canonical_id is not a current canonical content id: {command.canonical_id}")
    return [command.canonical_id]


def _create_run(
    session_factory: sessionmaker[Session],
    command: TagEnrichmentCommand,
) -> tuple[uuid.UUID, datetime]:
    with transactional_session(session_factory) as session:
        persisted_run_id = uuid.uuid4()
        row = TagEnrichmentRun(
            id=persisted_run_id,
            run_id=persisted_run_id,
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
        return row.id, row.started_at


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
        existing = _load_existing_source_tags(
            session,
            canonical_id=canonical_id,
            source=source,
        )
        existing_map = {normalized_name: round(float(conf), 4) for _tag_id, conf, _ver, normalized_name in existing}
        desired_map = {name: conf for name, conf in desired}

        previous_tags, previous_confidence, previous_version = _derive_previous_snapshot(existing)
        changed = existing_map != desired_map
        new_version = None
        result = TagEnrichmentItemResult.UNCHANGED.value

        if changed:
            next_version = max((int(ver) for _tag_id, _conf, ver, _name in existing if ver is not None), default=0) + 1
            new_version = next_version
            for normalized_name, confidence in desired:
                if normalized_name not in existing_map or existing_map[normalized_name] != confidence:
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
            previous_tags=previous_tags,
            previous_confidence=previous_confidence,
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
    source: TagSource,
    error_message: str,
) -> None:
    started = _utcnow()
    with transactional_session(session_factory) as session:
        content_exists = session.scalar(select(FileContent.content_id).where(FileContent.content_id == canonical_id))
        previous_tags: list[dict[str, object]] | None = None
        previous_confidence: float | None = None
        previous_version: int | None = None
        if content_exists is not None:
            existing = _load_existing_source_tags(
                session,
                canonical_id=canonical_id,
                source=source,
            )
            previous_tags, previous_confidence, previous_version = _derive_previous_snapshot(existing)
        session.add(
            TagEnrichmentItem(
                run_id=run_id,
                canonical_id=canonical_id,
                sequence_no=sequence_no,
                result=TagEnrichmentItemResult.FAILED.value,
                tags_emitted_count=0,
                average_confidence=None,
                previous_tags=previous_tags,
                previous_confidence=previous_confidence,
                previous_version=previous_version,
                new_version=None,
                started_at=started,
                completed_at=_utcnow(),
                duration_ms=0,
                error_message=error_message,
            )
        )


def _load_existing_source_tags(
    session: Session,
    *,
    canonical_id: uuid.UUID,
    source: TagSource,
) -> list[tuple[uuid.UUID, float, int | None, str]]:
    return list(
        session.execute(
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
    )


def _derive_previous_snapshot(
    existing: list[tuple[uuid.UUID, float, int | None, str]],
) -> tuple[list[dict[str, object]], float | None, int | None]:
    tags: list[dict[str, object]] = []
    confidences: list[float] = []
    versions: list[int] = []
    for _tag_id, conf, version, normalized_name in existing:
        rounded_confidence = round(float(conf), 4)
        int_version = int(version) if version is not None else None
        tags.append(
            {
                "tag": normalized_name,
                "confidence": rounded_confidence,
                "version": int_version,
            }
        )
        confidences.append(rounded_confidence)
        if int_version is not None:
            versions.append(int_version)
    previous_confidence = round(mean(confidences), 4) if confidences else None
    previous_version = max(versions) if versions else None
    return tags, previous_confidence, previous_version


def get_last_run_for_canonical(
    session_factory: sessionmaker[Session],
    *,
    canonical_id: uuid.UUID,
    source: TagSource,
) -> EnrichmentLastRunRecord | None:
    with transactional_session(session_factory) as session:
        row = session.execute(
            select(TagEnrichmentRun, TagEnrichmentItem)
            .join(TagEnrichmentItem, TagEnrichmentItem.run_id == TagEnrichmentRun.id)
            .where(
                TagEnrichmentItem.canonical_id == canonical_id,
                TagEnrichmentRun.source == source.value,
            )
            .order_by(
                TagEnrichmentRun.started_at.desc(),
                TagEnrichmentItem.sequence_no.desc(),
                TagEnrichmentRun.id.desc(),
            )
            .limit(1)
        ).first()
    if row is None:
        return None
    run, item = row
    return EnrichmentLastRunRecord(
        run_id=run.run_id,
        canonical_id=item.canonical_id,
        run_started_at=run.started_at,
        run_status=run.status,
        scope=run.scope,
        source=run.source,
        sequence_no=item.sequence_no,
        result=item.result,
        duration_ms=item.duration_ms,
        previous_version=item.previous_version,
        new_version=item.new_version,
        previous_confidence=item.previous_confidence,
    )


def get_enrichment_delta(
    session_factory: sessionmaker[Session],
    *,
    run_id: uuid.UUID,
    canonical_id: uuid.UUID,
) -> EnrichmentDelta | None:
    with transactional_session(session_factory) as session:
        row = session.execute(
            select(TagEnrichmentRun, TagEnrichmentItem)
            .join(TagEnrichmentItem, TagEnrichmentItem.run_id == TagEnrichmentRun.id)
            .where(
                TagEnrichmentRun.run_id == run_id,
                TagEnrichmentItem.canonical_id == canonical_id,
            )
            .order_by(
                TagEnrichmentItem.sequence_no.desc(),
                TagEnrichmentRun.id.desc(),
            )
            .limit(1)
        ).first()
        if row is None:
            return None
        run, item = row

        current_rows = session.execute(
            select(Tag.normalized_name, CanonicalTag.confidence_score)
            .join(CanonicalTag, CanonicalTag.tag_id == Tag.id)
            .where(
                CanonicalTag.canonical_id == canonical_id,
                CanonicalTag.source == run.source,
            )
            .order_by(Tag.normalized_name.asc())
        ).all()

    previous_payload = item.previous_tags or []
    previous_map = {
        str(payload["tag"]): round(float(payload["confidence"]), 4)
        for payload in previous_payload
        if isinstance(payload, dict) and payload.get("tag") is not None and payload.get("confidence") is not None
    }
    current_map = {str(name): round(float(conf), 4) for name, conf in current_rows}

    added = tuple(sorted(name for name in current_map if name not in previous_map))
    removed = tuple(sorted(name for name in previous_map if name not in current_map))
    changed_confidence = tuple(
        {
            "tag": name,
            "previous_confidence": previous_map[name],
            "current_confidence": current_map[name],
        }
        for name in sorted(previous_map)
        if name in current_map and previous_map[name] != current_map[name]
    )
    version_after = item.new_version if item.new_version is not None else item.previous_version
    return EnrichmentDelta(
        run_id=run.run_id,
        canonical_id=canonical_id,
        source=run.source,
        added=added,
        removed=removed,
        changed_confidence=changed_confidence,
        version_before=item.previous_version,
        version_after=version_after,
    )


def list_reprocessing_history(
    session_factory: sessionmaker[Session],
    *,
    canonical_id: uuid.UUID,
    source: TagSource,
    limit: int = 50,
) -> tuple[EnrichmentReprocessingRecord, ...]:
    if limit <= 0:
        raise ValueError("limit must be > 0")
    with transactional_session(session_factory) as session:
        rows = session.execute(
            select(TagEnrichmentRun, TagEnrichmentItem)
            .join(TagEnrichmentItem, TagEnrichmentItem.run_id == TagEnrichmentRun.id)
            .where(
                TagEnrichmentItem.canonical_id == canonical_id,
                TagEnrichmentRun.source == source.value,
            )
            .order_by(
                TagEnrichmentRun.started_at.asc(),
                TagEnrichmentItem.sequence_no.asc(),
                TagEnrichmentRun.id.asc(),
            )
            .limit(limit)
        ).all()
    return tuple(
        EnrichmentReprocessingRecord(
            run_id=run.run_id,
            canonical_id=item.canonical_id,
            source=run.source,
            run_started_at=run.started_at,
            sequence_no=item.sequence_no,
            result=item.result,
            duration_ms=item.duration_ms,
            previous_version=item.previous_version,
            new_version=item.new_version,
            previous_confidence=item.previous_confidence,
            tags_emitted_count=item.tags_emitted_count,
        )
        for run, item in rows
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
