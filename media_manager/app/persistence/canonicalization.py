from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.canonical.context import CanonicalContext
from media_manager.app.canonical.policies import CanonicalPolicy
from media_manager.app.core.date_extraction import filename_has_date
from media_manager.app.core.logging_config import get_logger
from media_manager.app.persistence.base import transactional_session
from media_manager.app.persistence.models import (
    CanonicalAssignment,
    CanonicalRecomputeItem,
    CanonicalRecomputeItemResult,
    CanonicalRecomputeMode,
    CanonicalRecomputeRun,
    CanonicalRecomputeStatus,
    FileInstance,
    MediaMetadata,
    MetadataCode,
)

logger = get_logger(__name__)
_CANONICAL_PROGRESS_EVERY = 100


class RecomputeMode(StrEnum):
    DRY_RUN = "DRY_RUN"
    APPLY = "APPLY"


@dataclass(frozen=True)
class RecomputeSummary:
    run_id: uuid.UUID
    scanned_count: int
    changed_count: int
    failed_count: int
    applied_count: int
    status: str
    changed_content_ids: tuple[str, ...]
    failed_content_ids: tuple[str, ...]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_active_assignment(session: Session, content_id: uuid.UUID) -> CanonicalAssignment | None:
    return session.scalar(
        select(CanonicalAssignment)
        .where(CanonicalAssignment.content_id == content_id)
        .order_by(CanonicalAssignment.assigned_at.desc(), CanonicalAssignment.assignment_id.desc())
        .limit(1)
    )


def append_assignment(
    session: Session,
    *,
    content_id: uuid.UUID,
    canonical_instance_id: uuid.UUID,
    policy_name: str,
    policy_version: str,
) -> CanonicalAssignment:
    row = CanonicalAssignment(
        content_id=content_id,
        canonical_instance_id=canonical_instance_id,
        policy_name=policy_name,
        policy_version=policy_version,
        assigned_at=_utcnow(),
    )
    session.add(row)
    session.flush()
    return row


def build_selection_context(
    session: Session,
    *,
    content_id: uuid.UUID,
    instances: list[FileInstance],
    preferred_roots: tuple[Path, ...] = (),
) -> CanonicalContext:
    metadata_map = {
        code_type: value
        for code_type, value in session.execute(
            select(MetadataCode.code_type, MediaMetadata.decode_value)
            .select_from(MediaMetadata)
            .join(MetadataCode, MediaMetadata.code_id == MetadataCode.id)
            .where(MediaMetadata.content_id == content_id)
        ).all()
    }
    filename_evidence_instance_ids = frozenset(
        str(instance.file_instance_id)
        for instance in instances
        if filename_has_date(Path(instance.absolute_path).name)
    )
    return CanonicalContext(
        preferred_roots=preferred_roots,
        taken_dt_source=metadata_map.get("TAKEN_DT_SOURCE"),
        filename_evidence_instance_ids=filename_evidence_instance_ids,
    )


def recompute_canonical_assignments(
    session_factory: sessionmaker[Session],
    *,
    policy: CanonicalPolicy,
    context: CanonicalContext,
    mode: RecomputeMode,
) -> RecomputeSummary:
    run_id = _create_recompute_run(session_factory, policy.name, policy.version, mode)
    scanned_count = 0
    changed_count = 0
    failed_count = 0
    applied_count = 0
    sequence_no = 0
    changed_content_ids: list[str] = []
    failed_content_ids: list[str] = []

    try:
        with transactional_session(session_factory) as session:
            duplicate_content_ids = session.scalars(
                select(FileInstance.content_id)
                .group_by(FileInstance.content_id)
                .having(func.count(FileInstance.file_instance_id) > 1)
                .order_by(FileInstance.content_id.asc())
            ).all()
        logger.info(
            "Run started",
            extra={
                "run_id": str(run_id),
                "phase": "canonical",
                "stage": "recompute",
                "status": "running",
                "policy_name": policy.name,
                "policy_version": policy.version,
                "recompute_mode": mode.value,
                "total_count": len(duplicate_content_ids),
            },
        )
        started_at = time.time()

        for content_id in duplicate_content_ids:
            sequence_no += 1
            scanned_count += 1
            try:
                with transactional_session(session_factory) as session:
                    instances = session.scalars(
                        select(FileInstance)
                        .where(FileInstance.content_id == content_id)
                        .order_by(
                            FileInstance.first_seen_at.asc(),
                            FileInstance.absolute_path.asc(),
                            FileInstance.file_instance_id.asc(),
                        )
                    ).all()
                    active_assignment = get_active_assignment(session, content_id)
                    old_id = active_assignment.canonical_instance_id if active_assignment else None
                    selected = policy.select(
                        str(content_id),
                        instances,
                        build_selection_context(
                            session,
                            content_id=content_id,
                            instances=instances,
                            preferred_roots=context.preferred_roots,
                        ),
                    )
                    changed = old_id != selected.file_instance_id

                    if changed:
                        changed_count += 1
                        changed_content_ids.append(str(content_id))
                    item_result = (
                        CanonicalRecomputeItemResult.CHANGED.value
                        if changed
                        else CanonicalRecomputeItemResult.UNCHANGED.value
                    )
                    if mode == RecomputeMode.APPLY and changed:
                        append_assignment(
                            session,
                            content_id=content_id,
                            canonical_instance_id=selected.file_instance_id,
                            policy_name=policy.name,
                            policy_version=policy.version,
                        )
                        applied_count += 1
                        item_result = CanonicalRecomputeItemResult.APPLIED.value

                    session.add(
                        CanonicalRecomputeItem(
                            run_id=run_id,
                            content_id=content_id,
                            old_canonical_instance_id=old_id,
                            new_canonical_instance_id=selected.file_instance_id,
                            duplicate_count=len(instances),
                            result=item_result,
                            sequence_no=sequence_no,
                            error_message=None,
                        )
                    )
                    logger.info(
                        "Canonical recompute item",
                        extra={
                            "run_id": str(run_id),
                            "phase": "canonical",
                            "stage": "recompute",
                            "status": "running",
                            "action": "RECOMPUTE",
                            "content_id": str(content_id),
                            "canonical_instance_id": str(selected.file_instance_id),
                            "policy_name": policy.name,
                            "policy_version": policy.version,
                            "recompute_mode": mode.value,
                            "sequence_no": sequence_no,
                        },
                    )
            except Exception as exc:
                failed_count += 1
                failed_content_ids.append(str(content_id))
                with transactional_session(session_factory) as session:
                    session.add(
                        CanonicalRecomputeItem(
                            run_id=run_id,
                            content_id=content_id,
                            old_canonical_instance_id=None,
                            new_canonical_instance_id=None,
                            duplicate_count=0,
                            result=CanonicalRecomputeItemResult.FAILED.value,
                            sequence_no=sequence_no,
                            error_message=str(exc),
                        )
                    )
            if duplicate_content_ids and (
                scanned_count % _CANONICAL_PROGRESS_EVERY == 0 or scanned_count == len(duplicate_content_ids)
            ):
                elapsed_seconds = max(time.time() - started_at, 0.000001)
                progress_percent = (scanned_count / len(duplicate_content_ids)) * 100.0
                throughput_fps = scanned_count / elapsed_seconds
                logger.info(
                    (
                        f"Progress: {scanned_count}/{len(duplicate_content_ids)} items ({progress_percent:.1f}%) | "
                        f"{throughput_fps:.1f} items/sec | elapsed {elapsed_seconds:.1f}s"
                    ),
                    extra={
                        "run_id": str(run_id),
                        "phase": "canonical",
                        "stage": "recompute",
                        "status": "running",
                        "processed_count": scanned_count,
                        "total_count": len(duplicate_content_ids),
                        "progress_percent": progress_percent,
                        "elapsed_seconds": elapsed_seconds,
                        "throughput_fps": throughput_fps,
                        "recompute_mode": mode.value,
                    },
                )

        status = (
            CanonicalRecomputeStatus.COMPLETED_WITH_ERRORS.value
            if failed_count > 0
            else CanonicalRecomputeStatus.COMPLETED.value
        )
        _finalize_recompute_run(
            session_factory,
            run_id=run_id,
            status=status,
            scanned_count=scanned_count,
            changed_count=changed_count,
            failed_count=failed_count,
            applied_count=applied_count,
            error_message=None,
        )
        logger.info(
            "Run completed",
            extra={
                "run_id": str(run_id),
                "phase": "canonical",
                "stage": "finalize",
                "status": status,
                "processed_count": scanned_count,
                "total_count": len(duplicate_content_ids),
                "progress_percent": 100.0 if duplicate_content_ids else None,
                "elapsed_seconds": max(time.time() - started_at, 0.000001),
                "recompute_mode": mode.value,
                "summary": {
                    "scanned_count": scanned_count,
                    "changed_count": changed_count,
                    "failed_count": failed_count,
                    "applied_count": applied_count,
                },
            },
        )
        return RecomputeSummary(
            run_id=run_id,
            scanned_count=scanned_count,
            changed_count=changed_count,
            failed_count=failed_count,
            applied_count=applied_count,
            status=status,
            changed_content_ids=tuple(sorted(changed_content_ids)),
            failed_content_ids=tuple(sorted(failed_content_ids)),
        )
    except Exception as exc:
        _finalize_recompute_run(
            session_factory,
            run_id=run_id,
            status=CanonicalRecomputeStatus.FAILED.value,
            scanned_count=scanned_count,
            changed_count=changed_count,
            failed_count=failed_count + 1,
            applied_count=applied_count,
            error_message=str(exc),
        )
        logger.exception(
            "Canonical recompute failed",
            extra={
                "run_id": str(run_id),
                "phase": "canonical",
                "stage": "finalize",
                "status": CanonicalRecomputeStatus.FAILED.value,
                "processed_count": scanned_count,
                "total_count": scanned_count,
                "elapsed_seconds": max(time.time() - started_at, 0.000001),
                "recompute_mode": mode.value,
            },
        )
        raise


def _create_recompute_run(
    session_factory: sessionmaker[Session],
    policy_name: str,
    policy_version: str,
    mode: RecomputeMode,
) -> uuid.UUID:
    with transactional_session(session_factory) as session:
        row = CanonicalRecomputeRun(
            policy_name=policy_name,
            policy_version=policy_version,
            mode=CanonicalRecomputeMode(mode.value).value,
            status=CanonicalRecomputeStatus.STARTED.value,
            scanned_count=0,
            changed_count=0,
            failed_count=0,
            applied_count=0,
            started_at=_utcnow(),
            completed_at=None,
            error_message=None,
        )
        session.add(row)
        session.flush()
        logger.info(
            "Transitioning run state",
            extra={
                "run_id": str(row.id),
                "phase": "canonical",
                "stage": "recompute",
                "status": CanonicalRecomputeStatus.STARTED.value,
            },
        )
        return row.id


def _finalize_recompute_run(
    session_factory: sessionmaker[Session],
    *,
    run_id: uuid.UUID,
    status: str,
    scanned_count: int,
    changed_count: int,
    failed_count: int,
    applied_count: int,
    error_message: str | None,
) -> None:
    with transactional_session(session_factory) as session:
        row = session.get(CanonicalRecomputeRun, run_id)
        if row is None:
            return
        row.status = status
        row.scanned_count = scanned_count
        row.changed_count = changed_count
        row.failed_count = failed_count
        row.applied_count = applied_count
        row.completed_at = _utcnow()
        row.error_message = error_message
