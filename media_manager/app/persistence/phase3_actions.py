"""Phase 3 planned/apply-backed archive and quarantine actions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.core.state_machine import RunState, validate_transition
from media_manager.app.persistence.apply import ApplyService
from media_manager.app.persistence.base import transactional_session
from media_manager.app.persistence.models import (
    DuplicateReclaimItem,
    DuplicateReclaimItemStatus,
    DuplicateReclaimRecord,
    DuplicateReclaimStatus,
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


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _reclaim_root() -> Path:
    raw = (os.getenv("MEDIA_MANAGER_RECLAIM_ROOT", "") or "").strip()
    return Path(raw) if raw else Path("/tmp/media-manager/reclaim")


def _quarantine_root() -> Path:
    raw = (os.getenv("MEDIA_MANAGER_QUARANTINE_ROOT", "") or "").strip()
    return Path(raw) if raw else Path("/tmp/media-manager/quarantine")


def _recycle_root() -> Path:
    raw = (os.getenv("MEDIA_MANAGER_RECYCLE_BIN_ROOT", "") or "").strip()
    return Path(raw) if raw else Path("/tmp/media-manager/recycle-bin")


def _quarantine_retention_days() -> int:
    raw = (os.getenv("MEDIA_MANAGER_QUARANTINE_RETENTION_DAYS", "") or "").strip()
    try:
        return max(1, int(raw)) if raw else 14
    except ValueError:
        return 14


def _recycle_purge_days() -> int:
    raw = (os.getenv("MEDIA_MANAGER_RECYCLE_PURGE_DAYS", "") or "").strip()
    try:
        return max(1, int(raw)) if raw else 30
    except ValueError:
        return 30


class Phase3ActionService:
    """Plan and execute reversible reclaim/quarantine actions through planned/apply state."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def execute_duplicate_reclaim(self, *, content_ids: list[UUID] | None = None, retention_days: int = 14) -> dict[str, object]:
        run_id = self._plan_duplicate_reclaim(content_ids=content_ids, retention_days=retention_days)
        summary = ApplyService(self._session_factory).apply_run(run_id)
        return {"run_id": str(run_id), "summary": summary.to_dict()}

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

    def _plan_duplicate_reclaim(self, *, content_ids: list[UUID] | None, retention_days: int) -> UUID:
        run = RunService(self._session_factory).create_run(owner="SYSTEM", context="DuplicateReclaim")
        reclaim_root = _reclaim_root()
        expires_at = _utcnow() + timedelta(days=max(1, retention_days))
        with transactional_session(self._session_factory) as session:
            run_row = session.get(Run, run.id)
            assert run_row is not None
            validate_transition(RunState(run_row.state.value), RunState.PLANNED)
            run_row.state = RunStateDB.PLANNED
            run_row.updated_at = func.now()
            run_row.version += 1

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
                archive_path = str(reclaim_root / str(file_instance.content_id) / f"{file_instance.file_instance_id}-{Path(file_instance.absolute_path).name}")
                existing = session.get(DuplicateReclaimItem, file_instance.file_instance_id)
                now = _utcnow()
                if existing is None:
                    session.add(
                        DuplicateReclaimItem(
                            file_instance_id=file_instance.file_instance_id,
                            content_id=file_instance.content_id,
                            original_path=file_instance.absolute_path,
                            archive_path=archive_path,
                            item_status=DuplicateReclaimItemStatus.PENDING.value,
                            reclaimed_at=None,
                            expires_at=expires_at,
                            restored_at=None,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                else:
                    existing.original_path = file_instance.absolute_path
                    existing.archive_path = archive_path
                    existing.item_status = DuplicateReclaimItemStatus.PENDING.value
                    existing.expires_at = expires_at
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
            session.flush()
        return run.id

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
            for item in items:
                item.item_status = DuplicateReclaimItemStatus.PENDING.value
                item.updated_at = _utcnow()
                session.add(
                    PlannedAction(
                        run_id=run.id,
                        file_id=item.file_instance_id,
                        action_type="RECLAIM_RESTORE",
                        role=PlannedActionRole.DUPLICATE.value,
                        duplicate_index=None,
                        source_path=item.archive_path,
                        target_path=item.original_path,
                    )
                )
            session.flush()
        return run.id

    def _plan_integrity_quarantine(self, *, check_id: UUID) -> UUID:
        run = RunService(self._session_factory).create_run(owner="SYSTEM", context="IntegrityQuarantine")
        quarantine_root = _quarantine_root()
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
            expires_at = now + timedelta(days=_quarantine_retention_days())
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
        recycle_root = _recycle_root()
        purge_after_at = _utcnow() + timedelta(days=_recycle_purge_days())
        with transactional_session(self._session_factory) as session:
            run_row = session.get(Run, run.id)
            assert run_row is not None
            validate_transition(RunState(run_row.state.value), RunState.PLANNED)
            run_row.state = RunStateDB.PLANNED
            run_row.updated_at = func.now()
            run_row.version += 1

            stmt = select(DuplicateReclaimItem).where(
                DuplicateReclaimItem.item_status == DuplicateReclaimItemStatus.ARCHIVED.value,
                DuplicateReclaimItem.expires_at.is_not(None),
                DuplicateReclaimItem.expires_at <= _utcnow(),
            )
            if file_instance_ids:
                stmt = stmt.where(DuplicateReclaimItem.file_instance_id.in_(file_instance_ids))

            items = session.scalars(stmt.order_by(DuplicateReclaimItem.file_instance_id.asc())).all()
            for item in items:
                recycle_path = str(
                    recycle_root / "duplicates" / str(item.content_id) / f"{item.file_instance_id}-{Path(item.archive_path).name}"
                )
                item.recycle_path = recycle_path
                item.purge_after_at = purge_after_at
                item.updated_at = _utcnow()
                session.add(
                    PlannedAction(
                        run_id=run.id,
                        file_id=item.file_instance_id,
                        action_type="RECLAIM_RECYCLE",
                        role=PlannedActionRole.DUPLICATE.value,
                        duplicate_index=None,
                        source_path=item.archive_path,
                        target_path=recycle_path,
                    )
                )
            session.flush()
        return run.id

    def _plan_integrity_recycle(self, *, file_instance_ids: list[UUID] | None) -> UUID:
        run = RunService(self._session_factory).create_run(owner="SYSTEM", context="IntegrityRecycle")
        recycle_root = _recycle_root()
        purge_after_at = _utcnow() + timedelta(days=_recycle_purge_days())
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
