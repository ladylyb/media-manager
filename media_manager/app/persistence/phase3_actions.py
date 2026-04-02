"""Phase 3 planned/apply-backed archive and quarantine actions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.core.logging_config import get_logger
from media_manager.app.core.state_machine import RunState, validate_transition
from media_manager.app.persistence.apply import ApplyService
from media_manager.app.persistence.base import transactional_session
from media_manager.app.persistence.models import (
    DuplicateBinState,
    DuplicateReclaimItem,
    DuplicateReclaimItemStatus,
    DuplicateReclaimRecord,
    DuplicateReclaimStatus,
    FailureEvent,
    FailurePhase,
    FileContent,
    FileInstance,
    FileInstanceStatus,
    IntegrityCheck,
    IntegrityQuarantineRecord,
    IntegrityQuarantineStatus,
    PlannedAction,
    PlannedActionRole,
    Run,
    RunStateDB,
)
from media_manager.app.persistence.runs import RunService
from media_manager.app.persistence.policy_settings import PolicySettingsService

LOGGER = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _duplicate_bin_archive_path(*, recycle_root: Path, content_id: UUID, file_instance_id: UUID, source_path: str) -> str:
    return str(recycle_root / "duplicates" / str(content_id) / f"{file_instance_id}-{Path(source_path).name}")


def _path_is_within_root(path_value: str | None, root: Path) -> bool:
    if not path_value:
        return False
    candidate = Path(path_value).resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    try:
        candidate.relative_to(resolved_root)
        return True
    except ValueError:
        return False


def _duplicate_restore_expiry(item: DuplicateReclaimItem) -> datetime | None:
    return item.restore_expires_at or item.expires_at


def _duplicate_restore_source_path(item: DuplicateReclaimItem) -> str | None:
    if item.bin_state == DuplicateBinState.IN_BIN.value and item.bin_path:
        return item.bin_path
    if item.item_status == DuplicateReclaimItemStatus.ARCHIVED.value and item.archive_path:
        return item.archive_path
    return None


def _duplicate_current_location_path(item: DuplicateReclaimItem) -> str | None:
    if item.bin_state == DuplicateBinState.IN_BIN.value and item.bin_path:
        return item.bin_path
    if item.item_status == DuplicateReclaimItemStatus.RECYCLED.value:
        return item.recycle_path
    return None


class Phase3ActionService:
    """Plan and execute reversible reclaim/quarantine actions through planned/apply state."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def _policy(self):
        return PolicySettingsService(self._session_factory).get_settings()

    def execute_duplicate_reclaim(self, *, content_ids: list[UUID] | None = None, retention_days: int = 14) -> dict[str, object]:
        planned = self._plan_duplicate_reclaim(content_ids=content_ids, retention_days=retention_days)
        run_id = planned["run_id"]
        summary = ApplyService(self._session_factory).apply_run(run_id)
        diagnostics = {
            **planned["diagnostics"],
            "applied_count": summary.applied_count,
            "skipped_count": summary.skipped_count,
            "result_type": (
                "applied"
                if summary.applied_count > 0
                else "planned_skipped"
                if planned["diagnostics"]["planned_action_count"] > 0 and summary.skipped_count > 0
                else "zero_planned"
            ),
        }
        LOGGER.debug(
            "duplicate_reclaim_debug: execute summary",
            extra={
                "stage": "duplicate_reclaim_execute_summary",
                "run_id": str(run_id),
                "requested_content_ids": [str(item) for item in content_ids or []],
                "planned_action_count": diagnostics["planned_action_count"],
                "applied_count": diagnostics["applied_count"],
                "skipped_count": diagnostics["skipped_count"],
                "result_type": diagnostics["result_type"],
            },
        )
        return {"run_id": str(run_id), "summary": summary.to_dict(), "diagnostics": diagnostics}

    def restore_duplicate_reclaim(self, *, file_instance_ids: list[UUID] | None = None) -> dict[str, object]:
        run_id = self._plan_duplicate_restore(file_instance_ids=file_instance_ids)
        summary = ApplyService(self._session_factory).apply_run(run_id)
        return {"run_id": str(run_id), "summary": summary.to_dict()}

    def quarantine_integrity_issue(self, *, check_id: UUID) -> dict[str, object]:
        run_id = self._plan_integrity_quarantine(check_id=check_id)
        summary = ApplyService(self._session_factory).apply_run(run_id)
        return {"run_id": str(run_id), "summary": summary.to_dict()}

    def restore_integrity_quarantine(self, *, file_instance_id: UUID) -> dict[str, object]:
        run_id = self._plan_integrity_restore(file_instance_id=file_instance_id)
        summary = ApplyService(self._session_factory).apply_run(run_id)
        return {"run_id": str(run_id), "summary": summary.to_dict()}

    def recycle_duplicate_reclaim(self, *, file_instance_ids: list[UUID] | None = None) -> dict[str, object]:
        run_id = self._plan_duplicate_recycle(file_instance_ids=file_instance_ids)
        summary = ApplyService(self._session_factory).apply_run(run_id)
        return {"run_id": str(run_id), "summary": summary.to_dict()}

    def recycle_integrity_quarantine(self, *, file_instance_ids: list[UUID] | None = None) -> dict[str, object]:
        run_id = self._plan_integrity_recycle(file_instance_ids=file_instance_ids)
        summary = ApplyService(self._session_factory).apply_run(run_id)
        return {"run_id": str(run_id), "summary": summary.to_dict()}

    def purge_duplicate_reclaim(self, *, file_instance_ids: list[UUID] | None = None) -> dict[str, object]:
        run_id = self._plan_duplicate_purge(file_instance_ids=file_instance_ids)
        summary = ApplyService(self._session_factory).apply_run(run_id)
        return {"run_id": str(run_id), "summary": summary.to_dict()}

    def purge_integrity_quarantine(self, *, file_instance_ids: list[UUID] | None = None) -> dict[str, object]:
        run_id = self._plan_integrity_purge(file_instance_ids=file_instance_ids)
        summary = ApplyService(self._session_factory).apply_run(run_id)
        return {"run_id": str(run_id), "summary": summary.to_dict()}

    def _plan_duplicate_reclaim(self, *, content_ids: list[UUID] | None, retention_days: int) -> dict[str, object]:
        run = RunService(self._session_factory).create_run(owner="SYSTEM", context="DuplicateReclaim")
        policy = self._policy()
        recycle_root = Path(policy.recycle_bin_root)
        effective_retention_days = max(1, retention_days)
        expires_at = _utcnow() + timedelta(days=effective_retention_days)
        planned_action_count = 0
        group_results: dict[UUID, dict[str, object]] = {}
        with transactional_session(self._session_factory) as session:
            run_row = session.get(Run, run.id)
            assert run_row is not None
            validate_transition(RunState(run_row.state.value), RunState.PLANNED)
            run_row.state = RunStateDB.PLANNED
            run_row.updated_at = func.now()
            run_row.version += 1

            if content_ids:
                requested_records = {
                    row.content_id: row
                    for row in session.scalars(
                        select(DuplicateReclaimRecord).where(DuplicateReclaimRecord.content_id.in_(content_ids))
                    ).all()
                }
                requested_canonical_ids = {
                    content_id: canonical_file_instance_id
                    for content_id, canonical_file_instance_id in session.execute(
                        select(FileContent.content_id, FileContent.canonical_file_instance_id).where(
                            FileContent.content_id.in_(content_ids)
                        )
                    ).all()
                }
                active_instances = {}
                for content_id, file_instance_id in session.execute(
                    select(FileInstance.content_id, FileInstance.file_instance_id).where(
                        FileInstance.content_id.in_(content_ids),
                        FileInstance.status == FileInstanceStatus.ACTIVE.value,
                    )
                ).all():
                    active_instances.setdefault(content_id, []).append(file_instance_id)
                for content_id in content_ids:
                    reclaim_record = requested_records.get(content_id)
                    canonical_instance_id = requested_canonical_ids.get(content_id)
                    candidate_duplicate_ids = [
                        file_instance_id
                        for file_instance_id in active_instances.get(content_id, [])
                        if file_instance_id != canonical_instance_id
                    ]
                    if reclaim_record is None or reclaim_record.reclaim_status != DuplicateReclaimStatus.REVIEWED_SAFE_TO_RECLAIM.value:
                        reason = "reclaim_status_not_reviewed_safe"
                    elif canonical_instance_id is None:
                        reason = "missing_canonical_file_content_mapping"
                    elif not candidate_duplicate_ids:
                        reason = "no_active_duplicate_instances"
                    else:
                        reason = None
                    group_results[content_id] = {
                        "content_id": str(content_id),
                        "reclaim_status": reclaim_record.reclaim_status if reclaim_record is not None else None,
                        "canonical_file_instance_id": str(canonical_instance_id) if canonical_instance_id is not None else None,
                        "candidate_duplicate_file_instance_ids": [str(file_id) for file_id in candidate_duplicate_ids],
                        "planned": False,
                        "reason": reason,
                    }
                    LOGGER.debug(
                        "duplicate_reclaim_debug: planner requested group",
                        extra={
                            "stage": "duplicate_reclaim_plan_group",
                            "run_id": str(run.id),
                            "content_id": str(content_id),
                            "reclaim_status": reclaim_record.reclaim_status if reclaim_record is not None else "",
                            "canonical_file_instance_id": str(canonical_instance_id) if canonical_instance_id is not None else "",
                            "candidate_duplicate_file_instance_ids": [str(file_id) for file_id in candidate_duplicate_ids],
                            "reason": reason or "candidate_pending",
                            "recycle_bin_root": str(recycle_root),
                        },
                    )

            stmt = (
                select(FileInstance, DuplicateReclaimRecord, FileContent.canonical_file_instance_id)
                .join(DuplicateReclaimRecord, DuplicateReclaimRecord.content_id == FileInstance.content_id)
                .join(FileContent, FileContent.content_id == FileInstance.content_id)
                .where(
                    FileInstance.status == FileInstanceStatus.ACTIVE.value,
                    DuplicateReclaimRecord.reclaim_status == DuplicateReclaimStatus.REVIEWED_SAFE_TO_RECLAIM.value,
                    FileContent.canonical_file_instance_id.is_not(None),
                    FileInstance.file_instance_id != FileContent.canonical_file_instance_id,
                )
                .order_by(FileInstance.content_id.asc(), FileInstance.absolute_path.asc())
            )
            if content_ids:
                stmt = stmt.where(FileInstance.content_id.in_(content_ids))

            rows = session.execute(stmt).all()
            for file_instance, reclaim_record, _canonical_instance_id in rows:
                archive_path = _duplicate_bin_archive_path(
                    recycle_root=recycle_root,
                    content_id=file_instance.content_id,
                    file_instance_id=file_instance.file_instance_id,
                    source_path=file_instance.absolute_path,
                )
                existing = session.get(DuplicateReclaimItem, file_instance.file_instance_id)
                now = _utcnow()
                if existing is None:
                    session.add(
                        DuplicateReclaimItem(
                            file_instance_id=file_instance.file_instance_id,
                            content_id=file_instance.content_id,
                            original_path=file_instance.absolute_path,
                            archive_path=archive_path,
                            planned_bin_path=archive_path,
                            bin_path=None,
                            item_status=DuplicateReclaimItemStatus.PENDING.value,
                            reclaimed_at=None,
                            bin_entered_at=None,
                            expires_at=expires_at,
                            restore_expires_at=expires_at,
                            bin_state=DuplicateBinState.PENDING_MOVE.value,
                            restored_at=None,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                else:
                    # Transitional compatibility note: archive_path may point to either the legacy
                    # reclaim-root location or the new recycle-bin-root location. Restore continues
                    # to use this field as the source of truth during the migration window.
                    existing.original_path = file_instance.absolute_path
                    existing.archive_path = archive_path
                    existing.planned_bin_path = archive_path
                    existing.bin_path = None
                    existing.item_status = DuplicateReclaimItemStatus.PENDING.value
                    existing.expires_at = expires_at
                    existing.bin_entered_at = None
                    existing.restore_expires_at = expires_at
                    existing.bin_state = DuplicateBinState.PENDING_MOVE.value
                    existing.recycle_path = None
                    existing.recycled_at = None
                    existing.purge_after_at = None
                    existing.restored_at = None
                    existing.updated_at = now

                session.add(
                    PlannedAction(
                        run_id=run.id,
                        file_id=file_instance.file_instance_id,
                        action_type="RECLAIM_ARCHIVE",
                        role=PlannedActionRole.DUPLICATE.value,
                        duplicate_index=None,
                        source_path=file_instance.absolute_path,
                        target_path=archive_path,
                    )
                )
                reclaim_record.updated_at = now
                planned_action_count += 1
                if file_instance.content_id in group_results:
                    group_results[file_instance.content_id]["planned"] = True
                    group_results[file_instance.content_id]["reason"] = None
                    planned_ids = group_results[file_instance.content_id].setdefault("planned_action_file_instance_ids", [])
                    if isinstance(planned_ids, list):
                        planned_ids.append(str(file_instance.file_instance_id))
                LOGGER.debug(
                    "duplicate_reclaim_debug: planner planned action",
                    extra={
                        "stage": "duplicate_reclaim_plan_action",
                        "run_id": str(run.id),
                        "content_id": str(file_instance.content_id),
                        "file_instance_id": str(file_instance.file_instance_id),
                        "canonical_file_instance_id": str(_canonical_instance_id) if _canonical_instance_id is not None else "",
                        "reclaim_status": reclaim_record.reclaim_status,
                        "archive_path": archive_path,
                        "recycle_bin_root": str(recycle_root),
                    },
                )
            session.flush()
        diagnostics = {
            "requested_group_count": len(content_ids or []),
            "planned_action_count": planned_action_count,
            "group_results": list(group_results.values()),
            "reclaim_root": str(Path(policy.duplicate_reclaim_archive_root)),
            "recycle_bin_root": str(policy.recycle_bin_root),
            "current_move_root": str(recycle_root),
            "recycle_purge_days": int(policy.recycle_purge_days),
            "policy_duplicate_reclaim_default_retention_days": int(policy.duplicate_reclaim_default_retention_days),
            "retention_days": effective_retention_days,
            "policy_source": "persisted_or_default_policy_snapshot",
        }
        return {"run_id": run.id, "diagnostics": diagnostics}

    def _plan_duplicate_restore(self, *, file_instance_ids: list[UUID] | None) -> UUID:
        run = RunService(self._session_factory).create_run(owner="SYSTEM", context="DuplicateRestore")
        with transactional_session(self._session_factory) as session:
            run_row = session.get(Run, run.id)
            assert run_row is not None
            validate_transition(RunState(run_row.state.value), RunState.PLANNED)
            run_row.state = RunStateDB.PLANNED
            run_row.updated_at = func.now()
            run_row.version += 1

            stmt = select(DuplicateReclaimItem).where(
                DuplicateReclaimItem.item_status == DuplicateReclaimItemStatus.ARCHIVED.value
            )
            if file_instance_ids:
                stmt = stmt.where(DuplicateReclaimItem.file_instance_id.in_(file_instance_ids))
            items = session.scalars(stmt.order_by(DuplicateReclaimItem.file_instance_id.asc())).all()
            now = _utcnow()
            for item in items:
                restore_expires_at = _duplicate_restore_expiry(item)
                if restore_expires_at is not None and restore_expires_at <= now:
                    session.add(
                        FailureEvent(
                            run_id=run.id,
                            phase=FailurePhase.PLANNING,
                            error_code="DUPLICATE_RESTORE_EXPIRED",
                            error_message=f"{item.file_instance_id}:{restore_expires_at.isoformat()}",
                        )
                    )
                    continue

                restore_source_path = _duplicate_restore_source_path(item)
                if restore_source_path is None:
                    session.add(
                        FailureEvent(
                            run_id=run.id,
                            phase=FailurePhase.PLANNING,
                            error_code="DUPLICATE_RESTORE_SOURCE_MISSING",
                            error_message=str(item.file_instance_id),
                        )
                    )
                    continue

                item.item_status = DuplicateReclaimItemStatus.PENDING.value
                item.updated_at = now
                session.add(
                    PlannedAction(
                        run_id=run.id,
                        file_id=item.file_instance_id,
                        action_type="RECLAIM_RESTORE",
                        role=PlannedActionRole.DUPLICATE.value,
                        duplicate_index=None,
                        source_path=restore_source_path,
                        target_path=item.original_path,
                    )
                )
            session.flush()
        return run.id

    def _plan_integrity_quarantine(self, *, check_id: UUID) -> UUID:
        run = RunService(self._session_factory).create_run(owner="SYSTEM", context="IntegrityQuarantine")
        policy = self._policy()
        quarantine_root = Path(policy.integrity_quarantine_root)
        with transactional_session(self._session_factory) as session:
            run_row = session.get(Run, run.id)
            assert run_row is not None
            validate_transition(RunState(run_row.state.value), RunState.PLANNED)
            run_row.state = RunStateDB.PLANNED
            run_row.updated_at = func.now()
            run_row.version += 1

            check = session.get(IntegrityCheck, check_id)
            if check is None:
                raise ValueError(f"integrity check not found: {check_id}")
            file_instance = session.get(FileInstance, check.file_instance_id)
            if file_instance is None:
                raise ValueError(f"file instance not found: {check.file_instance_id}")
            quarantine_path = str(quarantine_root / f"{file_instance.file_instance_id}-{Path(file_instance.absolute_path).name}")
            now = _utcnow()
            expires_at = now + timedelta(days=policy.integrity_quarantine_retention_days)
            record = session.get(IntegrityQuarantineRecord, file_instance.file_instance_id)
            if record is None:
                session.add(
                    IntegrityQuarantineRecord(
                        file_instance_id=file_instance.file_instance_id,
                        check_id=check.id,
                        original_path=file_instance.absolute_path,
                        quarantine_path=quarantine_path,
                        quarantine_status=IntegrityQuarantineStatus.PENDING.value,
                        quarantined_at=None,
                        expires_at=expires_at,
                        recycle_path=None,
                        recycled_at=None,
                        purge_after_at=None,
                        restored_at=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                record.original_path = file_instance.absolute_path
                record.quarantine_path = quarantine_path
                record.quarantine_status = IntegrityQuarantineStatus.PENDING.value
                record.expires_at = expires_at
                record.recycle_path = None
                record.recycled_at = None
                record.purge_after_at = None
                record.updated_at = now

            session.add(
                PlannedAction(
                    run_id=run.id,
                    file_id=file_instance.file_instance_id,
                    action_type="INTEGRITY_QUARANTINE",
                    role=PlannedActionRole.CANONICAL.value,
                    duplicate_index=None,
                    source_path=file_instance.absolute_path,
                    target_path=quarantine_path,
                )
            )
            session.flush()
        return run.id

    def _plan_integrity_restore(self, *, file_instance_id: UUID) -> UUID:
        run = RunService(self._session_factory).create_run(owner="SYSTEM", context="IntegrityRestore")
        with transactional_session(self._session_factory) as session:
            run_row = session.get(Run, run.id)
            assert run_row is not None
            validate_transition(RunState(run_row.state.value), RunState.PLANNED)
            run_row.state = RunStateDB.PLANNED
            run_row.updated_at = func.now()
            run_row.version += 1

            record = session.get(IntegrityQuarantineRecord, file_instance_id)
            if record is None:
                raise ValueError(f"quarantine record not found: {file_instance_id}")
            record.quarantine_status = IntegrityQuarantineStatus.PENDING.value
            record.updated_at = _utcnow()
            session.add(
                PlannedAction(
                    run_id=run.id,
                    file_id=file_instance_id,
                    action_type="INTEGRITY_RESTORE",
                    role=PlannedActionRole.CANONICAL.value,
                    duplicate_index=None,
                    source_path=record.quarantine_path,
                    target_path=record.original_path,
                )
            )
            session.flush()
        return run.id

    def _plan_duplicate_recycle(self, *, file_instance_ids: list[UUID] | None) -> UUID:
        run = RunService(self._session_factory).create_run(owner="SYSTEM", context="DuplicateRecycle")
        policy = self._policy()
        recycle_root = Path(policy.recycle_bin_root)
        purge_after_at = _utcnow() + timedelta(days=policy.recycle_purge_days)
        with transactional_session(self._session_factory) as session:
            run_row = session.get(Run, run.id)
            assert run_row is not None
            validate_transition(RunState(run_row.state.value), RunState.PLANNED)
            run_row.state = RunStateDB.PLANNED
            run_row.updated_at = func.now()
            run_row.version += 1

            stmt = select(DuplicateReclaimItem).where(
                DuplicateReclaimItem.item_status == DuplicateReclaimItemStatus.ARCHIVED.value,
            )
            if file_instance_ids:
                stmt = stmt.where(DuplicateReclaimItem.file_instance_id.in_(file_instance_ids))

            items = session.scalars(stmt.order_by(DuplicateReclaimItem.file_instance_id.asc())).all()
            now = _utcnow()
            for item in items:
                retention_expires_at = _duplicate_restore_expiry(item)
                if retention_expires_at is None or retention_expires_at > now:
                    continue
                current_location_path = _duplicate_current_location_path(item)
                if current_location_path is None:
                    continue
                already_under_target_root = _path_is_within_root(current_location_path, recycle_root)
                recycle_path = (
                    current_location_path
                    if already_under_target_root
                    else str(
                        recycle_root
                        / "duplicates"
                        / str(item.content_id)
                        / f"{item.file_instance_id}-{Path(current_location_path).name}"
                    )
                )
                item.recycle_path = recycle_path
                item.purge_after_at = purge_after_at
                item.updated_at = now
                session.add(
                    PlannedAction(
                        run_id=run.id,
                        file_id=item.file_instance_id,
                        action_type="RECLAIM_RECYCLE",
                        role=PlannedActionRole.DUPLICATE.value,
                        duplicate_index=None,
                        source_path=current_location_path,
                        target_path=current_location_path if already_under_target_root else recycle_path,
                    )
                )
            session.flush()
        return run.id

    def _plan_integrity_recycle(self, *, file_instance_ids: list[UUID] | None) -> UUID:
        run = RunService(self._session_factory).create_run(owner="SYSTEM", context="IntegrityRecycle")
        policy = self._policy()
        recycle_root = Path(policy.recycle_bin_root)
        purge_after_at = _utcnow() + timedelta(days=policy.recycle_purge_days)
        with transactional_session(self._session_factory) as session:
            run_row = session.get(Run, run.id)
            assert run_row is not None
            validate_transition(RunState(run_row.state.value), RunState.PLANNED)
            run_row.state = RunStateDB.PLANNED
            run_row.updated_at = func.now()
            run_row.version += 1

            stmt = select(IntegrityQuarantineRecord).where(
                IntegrityQuarantineRecord.quarantine_status == IntegrityQuarantineStatus.QUARANTINED.value,
                IntegrityQuarantineRecord.expires_at.is_not(None),
                IntegrityQuarantineRecord.expires_at <= _utcnow(),
            )
            if file_instance_ids:
                stmt = stmt.where(IntegrityQuarantineRecord.file_instance_id.in_(file_instance_ids))

            items = session.scalars(stmt.order_by(IntegrityQuarantineRecord.file_instance_id.asc())).all()
            for item in items:
                recycle_path = str(
                    recycle_root / "integrity" / f"{item.file_instance_id}-{Path(item.quarantine_path).name}"
                )
                item.recycle_path = recycle_path
                item.purge_after_at = purge_after_at
                item.updated_at = _utcnow()
                session.add(
                    PlannedAction(
                        run_id=run.id,
                        file_id=item.file_instance_id,
                        action_type="INTEGRITY_RECYCLE",
                        role=PlannedActionRole.CANONICAL.value,
                        duplicate_index=None,
                        source_path=item.quarantine_path,
                        target_path=recycle_path,
                    )
                )
            session.flush()
        return run.id

    def _plan_duplicate_purge(self, *, file_instance_ids: list[UUID] | None) -> UUID:
        run = RunService(self._session_factory).create_run(owner="SYSTEM", context="DuplicatePurge")
        with transactional_session(self._session_factory) as session:
            run_row = session.get(Run, run.id)
            assert run_row is not None
            validate_transition(RunState(run_row.state.value), RunState.PLANNED)
            run_row.state = RunStateDB.PLANNED
            run_row.updated_at = func.now()
            run_row.version += 1

            stmt = select(DuplicateReclaimItem).where(
                DuplicateReclaimItem.item_status == DuplicateReclaimItemStatus.RECYCLED.value,
                DuplicateReclaimItem.purge_after_at.is_not(None),
                DuplicateReclaimItem.purge_after_at <= _utcnow(),
                DuplicateReclaimItem.recycle_path.is_not(None),
            )
            if file_instance_ids:
                stmt = stmt.where(DuplicateReclaimItem.file_instance_id.in_(file_instance_ids))

            items = session.scalars(stmt.order_by(DuplicateReclaimItem.file_instance_id.asc())).all()
            for item in items:
                session.add(
                    PlannedAction(
                        run_id=run.id,
                        file_id=item.file_instance_id,
                        action_type="RECLAIM_PURGE",
                        role=PlannedActionRole.DUPLICATE.value,
                        duplicate_index=None,
                        source_path=item.recycle_path or item.archive_path,
                        target_path=None,
                    )
                )
            session.flush()
        return run.id

    def _plan_integrity_purge(self, *, file_instance_ids: list[UUID] | None) -> UUID:
        run = RunService(self._session_factory).create_run(owner="SYSTEM", context="IntegrityPurge")
        with transactional_session(self._session_factory) as session:
            run_row = session.get(Run, run.id)
            assert run_row is not None
            validate_transition(RunState(run_row.state.value), RunState.PLANNED)
            run_row.state = RunStateDB.PLANNED
            run_row.updated_at = func.now()
            run_row.version += 1

            stmt = select(IntegrityQuarantineRecord).where(
                IntegrityQuarantineRecord.quarantine_status == IntegrityQuarantineStatus.RECYCLED.value,
                IntegrityQuarantineRecord.purge_after_at.is_not(None),
                IntegrityQuarantineRecord.purge_after_at <= _utcnow(),
                IntegrityQuarantineRecord.recycle_path.is_not(None),
            )
            if file_instance_ids:
                stmt = stmt.where(IntegrityQuarantineRecord.file_instance_id.in_(file_instance_ids))

            items = session.scalars(stmt.order_by(IntegrityQuarantineRecord.file_instance_id.asc())).all()
            for item in items:
                session.add(
                    PlannedAction(
                        run_id=run.id,
                        file_id=item.file_instance_id,
                        action_type="INTEGRITY_PURGE",
                        role=PlannedActionRole.CANONICAL.value,
                        duplicate_index=None,
                        source_path=item.recycle_path or item.quarantine_path,
                        target_path=None,
                    )
                )
            session.flush()
        return run.id
