"""Deterministic apply service with short DB transactions and audit logging."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.core.errors import (
    ApplyIntegrityException,
    ApplyStateError,
    CanonicalUnreadableError,
    CollisionResolutionError,
    RunNotFoundError,
)
from media_manager.app.core.logging_config import get_logger
from media_manager.app.core.state_machine import RunState, validate_transition
from media_manager.app.observability import record_apply_metrics
from media_manager.app.persistence.base import transactional_session
from media_manager.app.persistence.models import (
    ApplyAuditItem,
    ApplyAuditRun,
    FailureEvent,
    FailurePhase,
    CanonicalAssignment,
    FileInstance,
    FileInstanceStatus,
    PlannedAction,
    Run,
    RunStateDB,
)

logger = get_logger(__name__)
_WINDOWS_DRIVE_PATH_RE = re.compile(r"^([A-Za-z]):[\\/](.*)$")
_APPLY_PROGRESS_EVERY = 100

CollisionMode = Literal["rename", "skip", "fail"]


@dataclass(frozen=True)
class ApplySummary:
    applied_count: int
    skipped_count: int
    duplicates_count: int
    noop_count: int
    errors_count: int
    moves_count: int

    def to_dict(self) -> dict[str, int]:
        return {
            "applied_count": self.applied_count,
            "skipped_count": self.skipped_count,
            "duplicates_count": self.duplicates_count,
            "noop_count": self.noop_count,
            "errors_count": self.errors_count,
            "moves_count": self.moves_count,
        }


@dataclass(frozen=True)
class ActionOutcome:
    result: Literal["APPLIED", "SKIPPED", "FAILED"]
    source_path: str
    target_path: str | None
    error_message: str | None
    collision_detected: bool
    collision_resolved: bool
    file_instance_id: uuid.UUID
    planned_action_id: uuid.UUID


@dataclass(frozen=True)
class CanonicalGuardContext:
    """Structured guard context used when canonical instance is unreadable."""

    content_id: uuid.UUID | None
    canonical_instance_id: uuid.UUID | None
    canonical_path: str | None
    reason: str


def is_canonical_readable(path: Path) -> bool:
    """Return True when canonical file can be opened/read in current runtime."""
    try:
        with path.open("rb") as handle:
            handle.read(1)
        return True
    except (OSError, IOError):
        return False


def _map_windows_path_to_wsl(raw_path: str) -> Path | None:
    """Map `C:\\foo\\bar` style paths to `/mnt/c/foo/bar` for WSL runtimes."""
    matched = _WINDOWS_DRIVE_PATH_RE.match(raw_path)
    if matched is None:
        return None
    drive = matched.group(1).lower()
    tail = matched.group(2).replace("\\", "/")
    return Path("/mnt") / drive / tail


def _resolve_runtime_path(raw_path: str) -> Path | None:
    """Resolve a runtime-readable path using direct and Windows->WSL fallback."""
    direct_path = Path(raw_path)
    if direct_path.exists() and direct_path.is_file():
        return direct_path

    mapped = _map_windows_path_to_wsl(raw_path)
    if mapped is not None and mapped.exists() and mapped.is_file():
        return mapped
    return None


class ApplyService:
    """Transactional apply-stage with deterministic rename/move behavior."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def apply_run(self, run_id: uuid.UUID, collision_mode: CollisionMode = "rename") -> ApplySummary:
        audit_run_id: uuid.UUID | None = None
        applied_count = 0
        skipped_count = 0
        duplicates_count = 0
        noop_count = 0
        moves_count = 0
        collision_detected_count = 0
        collision_resolved_count = 0
        verification_failures_count = 0

        try:
            audit_run_id, total_actions = self._create_audit_run(run_id)
            self._mark_applying(run_id, audit_run_id)
            actions = self._load_actions_for_apply(run_id)
            if len(actions) != total_actions:
                total_actions = len(actions)

            logger.info(
                "Run started",
                extra={
                    "run_id": str(run_id),
                    "phase": "apply",
                    "stage": "execute_actions",
                    "status": "running",
                    "action_type": "",
                    "total_count": total_actions,
                },
            )
            started_at = time.time()
            processed_count = 0

            for action in actions:
                try:
                    outcome = self._execute_action(run_id, action, collision_mode)
                except Exception:
                    logger.exception(
                        "Apply action failed",
                        extra={
                            "run_id": str(run_id),
                            "phase": "apply",
                            "planned_action_id": str(action.id),
                            "file_instance_id": str(action.file_id),
                            "collision_mode": collision_mode,
                        },
                    )
                    raise
                if outcome.collision_detected:
                    collision_detected_count += 1
                if outcome.collision_resolved:
                    collision_resolved_count += 1

                if outcome.result == "APPLIED":
                    verification_ok = self._verify_applied_action(outcome)
                    if not verification_ok:
                        verification_failures_count += 1
                        self._persist_action_item(audit_run_id, outcome, "post-apply verification failed")
                        raise ApplyIntegrityException(
                            f"Post-apply verification failed for planned_action_id={outcome.planned_action_id}"
                        )

                    self._persist_applied_action(audit_run_id, action, outcome)
                    applied_count += 1
                    if action.action_type in {"RENAME", "MOVE"}:
                        moves_count += 1
                    elif action.action_type in {"COLLISION_RESOLVED", "MARK_DUPLICATE"}:
                        duplicates_count += 1
                    elif action.action_type in {"SKIP", "NOOP"}:
                        noop_count += 1
                elif outcome.result == "SKIPPED":
                    self._persist_action_item(audit_run_id, outcome, outcome.error_message)
                    skipped_count += 1
                else:
                    self._persist_action_item(audit_run_id, outcome, outcome.error_message or "action failed")
                    raise RuntimeError(outcome.error_message or "apply action failed")

                processed_count += 1
                # Emit periodic action progress so long applies show forward movement without per-action chatter.
                if total_actions > 0 and (
                    processed_count % _APPLY_PROGRESS_EVERY == 0 or processed_count == total_actions
                ):
                    elapsed_seconds = max(time.time() - started_at, 0.000001)
                    progress_percent = (processed_count / total_actions) * 100.0
                    throughput_fps = processed_count / elapsed_seconds
                    logger.info(
                        (
                            f"Progress: {processed_count}/{total_actions} items ({progress_percent:.1f}%) | "
                            f"{throughput_fps:.1f} items/sec | elapsed {elapsed_seconds:.1f}s"
                        ),
                        extra={
                            "run_id": str(run_id),
                            "phase": "apply",
                            "stage": "execute_actions",
                            "status": "running",
                            "processed_count": processed_count,
                            "total_count": total_actions,
                            "progress_percent": progress_percent,
                            "elapsed_seconds": elapsed_seconds,
                            "throughput_fps": throughput_fps,
                            "applied": applied_count,
                            "skipped": skipped_count,
                            "duplicates": duplicates_count,
                            "moves": moves_count,
                        },
                    )

            self._complete_success(
                run_id=run_id,
                audit_run_id=audit_run_id,
                total_actions=total_actions,
                applied_actions=applied_count,
                skipped_actions=skipped_count,
                collision_count=collision_detected_count,
            )

            summary = ApplySummary(
                applied_count=applied_count,
                skipped_count=skipped_count,
                duplicates_count=duplicates_count,
                noop_count=noop_count,
                errors_count=0,
                moves_count=moves_count,
            )
            logger.info(
                "Summary counts",
                extra={
                    "run_id": str(run_id),
                    "phase": "apply",
                    "stage": "finalize",
                    "status": "completed",
                    "action_type": "",
                    "processed_count": applied_count + skipped_count,
                    "total_count": total_actions,
                    "progress_percent": 100.0 if total_actions > 0 else None,
                    "applied": summary.applied_count,
                    "skipped": summary.skipped_count,
                    "moves": summary.moves_count,
                    "duplicates": summary.duplicates_count,
                    "noop": summary.noop_count,
                    "errors": summary.errors_count,
                    "collision_detected_count": collision_detected_count,
                    "collision_resolved_count": collision_resolved_count,
                    "verification_failures_count": verification_failures_count,
                },
            )
            logger.info(
                "Run completed",
                extra={
                    "run_id": str(run_id),
                    "phase": "apply",
                    "stage": "finalize",
                    "status": "completed",
                    "action_type": "",
                    "processed_count": applied_count + skipped_count,
                    "total_count": total_actions,
                    "progress_percent": 100.0 if total_actions > 0 else None,
                    "summary": summary.to_dict(),
                },
            )
            try:
                record_apply_metrics(run_id=str(run_id), actions_executed=summary.applied_count + summary.skipped_count)
            except Exception:
                logger.exception(
                    "Observability metric emission failed",
                    extra={"run_id": str(run_id), "phase": "apply", "action_type": "METRICS"},
                )
            return summary
        except Exception as exc:
            logger.exception(
                "Apply failed",
                extra={
                    "run_id": str(run_id),
                    "phase": "apply",
                    "stage": "finalize",
                    "status": "error",
                    "action_type": "",
                    "collision_mode": collision_mode,
                },
            )
            if audit_run_id is not None:
                self._complete_failure(
                    run_id=run_id,
                    audit_run_id=audit_run_id,
                    applied_actions=applied_count,
                    skipped_actions=skipped_count,
                    collision_count=collision_detected_count,
                    error_message=f"apply failed: {exc}",
                )
            self._record_apply_failure_event(run_id, str(exc))
            raise

    def _lock_run(self, session: Session, run_id: uuid.UUID) -> Run:
        stmt = select(Run).where(Run.id == run_id).with_for_update()
        run = session.scalar(stmt)
        if run is None:
            raise RunNotFoundError(str(run_id))
        return run

    def _create_audit_run(self, run_id: uuid.UUID) -> tuple[uuid.UUID, int]:
        with transactional_session(self._session_factory) as session:
            run = self._lock_run(session, run_id)
            if run.state != RunStateDB.PLANNED:
                raise ApplyStateError(f"Apply is only allowed from PLANNED. Current state: {run.state.value}")

            total_actions = int(
                session.scalar(select(func.count()).select_from(PlannedAction).where(PlannedAction.run_id == run_id)) or 0
            )
            audit = ApplyAuditRun(
                run_id=run_id,
                started_at=_utcnow(),
                status="PLANNED",
                total_actions=total_actions,
                applied_actions=0,
                skipped_actions=0,
                collision_count=0,
                error_message=None,
            )
            session.add(audit)
            session.flush()
            return audit.id, total_actions

    def _mark_applying(self, run_id: uuid.UUID, audit_run_id: uuid.UUID) -> None:
        with transactional_session(self._session_factory) as session:
            run = self._lock_run(session, run_id)
            if run.state != RunStateDB.PLANNED:
                raise ApplyStateError(f"Apply is only allowed from PLANNED. Current state: {run.state.value}")

            old_state = run.state.value
            validate_transition(RunState(run.state.value), RunState.APPLYING)
            logger.info(
                "Transitioning run state",
                extra={
                    "run_id": str(run.id),
                    "phase": "apply",
                    "action_type": "",
                    "from": old_state,
                    "to": RunState.APPLYING.value,
                },
            )
            run.state = RunStateDB.APPLYING
            run.version += 1
            run.updated_at = func.now()

            audit = session.get(ApplyAuditRun, audit_run_id)
            if audit is not None:
                audit.status = "APPLYING"

    def _load_actions_for_apply(self, run_id: uuid.UUID) -> list[PlannedAction]:
        # Deterministic order contract:
        # target_path ASC NULLS LAST, file_instance_id ASC, planned_action_id ASC.
        # planned_actions.file_id is the persisted file_instance_id.
        with transactional_session(self._session_factory) as session:
            return session.scalars(
                select(PlannedAction)
                .where(PlannedAction.run_id == run_id)
                .order_by(
                    PlannedAction.target_path.asc().nulls_last(),
                    PlannedAction.file_id.asc(),
                    PlannedAction.id.asc(),
                )
            ).all()

    def _execute_action(self, run_id: uuid.UUID, action: PlannedAction, collision_mode: CollisionMode) -> ActionOutcome:
        source = Path(action.source_path)
        destination = Path(action.target_path) if action.target_path else source
        source_resolved = source.resolve(strict=False)
        destination_resolved = destination.resolve(strict=False)

        if not source.exists() or not source.is_file():
            if destination.exists() and destination.is_file():
                logger.info(
                    "Idempotent apply detected",
                    extra={
                        "run_id": str(run_id),
                        "phase": "apply",
                        "planned_action_id": str(action.id),
                        "file_instance_id": str(action.file_id),
                        "action_type": action.action_type,
                    },
                )
                return ActionOutcome(
                    result="APPLIED",
                    source_path=str(source_resolved),
                    target_path=str(destination_resolved),
                    error_message=None,
                    collision_detected=False,
                    collision_resolved=False,
                    file_instance_id=action.file_id,
                    planned_action_id=action.id,
                )
            logger.warning(
                "Skipped missing source",
                extra={
                    "run_id": str(run_id),
                    "phase": "apply",
                    "planned_action_id": str(action.id),
                    "file_instance_id": str(action.file_id),
                    "action_type": action.action_type,
                },
            )
            return ActionOutcome(
                result="SKIPPED",
                source_path=str(source_resolved),
                target_path=str(destination_resolved),
                error_message="missing source",
                collision_detected=False,
                collision_resolved=False,
                file_instance_id=action.file_id,
                planned_action_id=action.id,
            )

        if source_resolved == destination_resolved:
            return ActionOutcome(
                result="SKIPPED",
                source_path=str(source_resolved),
                target_path=str(destination_resolved),
                error_message="source equals target",
                collision_detected=False,
                collision_resolved=False,
                file_instance_id=action.file_id,
                planned_action_id=action.id,
            )

        guard_context = self._canonical_guard_context_for_action(action)
        if guard_context is not None:
            error = CanonicalUnreadableError(
                content_id=str(guard_context.content_id) if guard_context.content_id is not None else "-",
                canonical_instance_id=(
                    str(guard_context.canonical_instance_id)
                    if guard_context.canonical_instance_id is not None
                    else None
                ),
                canonical_path=guard_context.canonical_path,
                reason=guard_context.reason,
                runtime_context="apply_guard",
            )
            self._record_canonical_unreadable_event(run_id, str(error))
            logger.warning(
                "Canonical unreadable for duplicate mutation",
                extra={
                    "run_id": str(run_id),
                    "phase": "apply",
                    "planned_action_id": str(action.id),
                    "file_instance_id": str(action.file_id),
                    "content_id": str(guard_context.content_id) if guard_context.content_id is not None else "-",
                    "canonical_instance_id": (
                        str(guard_context.canonical_instance_id)
                        if guard_context.canonical_instance_id is not None
                        else "-"
                    ),
                    "canonical_path": guard_context.canonical_path or "-",
                    "reason": guard_context.reason,
                },
            )
            return ActionOutcome(
                result="SKIPPED",
                source_path=str(source_resolved),
                target_path=str(destination_resolved),
                error_message=str(error),
                collision_detected=False,
                collision_resolved=False,
                file_instance_id=action.file_id,
                planned_action_id=action.id,
            )

        destination.parent.mkdir(parents=True, exist_ok=True)
        collision_detected = destination.exists()
        collision_resolved = False

        final_destination = destination
        if collision_detected:
            if collision_mode == "skip":
                return ActionOutcome(
                    result="SKIPPED",
                    source_path=str(source_resolved),
                    target_path=str(destination_resolved),
                    error_message="collision skipped",
                    collision_detected=True,
                    collision_resolved=False,
                    file_instance_id=action.file_id,
                    planned_action_id=action.id,
                )
            if collision_mode == "fail":
                logger.error(
                    "Collision mode fail",
                    extra={
                        "run_id": str(run_id),
                        "phase": "apply",
                        "planned_action_id": str(action.id),
                        "file_instance_id": str(action.file_id),
                        "collision_mode": collision_mode,
                        "target_path": str(destination_resolved),
                    },
                )
                return ActionOutcome(
                    result="FAILED",
                    source_path=str(source_resolved),
                    target_path=str(destination_resolved),
                    error_message=f"collision at target path: {destination_resolved}",
                    collision_detected=True,
                    collision_resolved=False,
                    file_instance_id=action.file_id,
                    planned_action_id=action.id,
                )

            final_destination = self._resolve_collision_destination(destination, collision_mode)
            collision_resolved = True

        source.rename(final_destination)
        logger.info(
            "File renamed",
            extra={
                "run_id": str(run_id),
                "phase": "apply",
                "planned_action_id": str(action.id),
                "file_instance_id": str(action.file_id),
                "target_filename": final_destination.name,
                "action_type": action.action_type,
                "action": action.action_type,
            },
        )
        return ActionOutcome(
            result="APPLIED",
            source_path=str(source_resolved),
            target_path=str(final_destination.resolve(strict=False)),
            error_message=None,
            collision_detected=collision_detected,
            collision_resolved=collision_resolved,
            file_instance_id=action.file_id,
            planned_action_id=action.id,
        )

    def _resolve_collision_destination(self, target_path: Path, collision_mode: CollisionMode) -> Path:
        original_stem = target_path.stem
        ext = target_path.suffix
        for i in range(1, 101):
            candidate = target_path.with_name(f"{original_stem}__dup{i:02d}{ext}")
            if not candidate.exists():
                return candidate
        raise CollisionResolutionError(
            original_target_path=str(target_path.resolve(strict=False)),
            collision_mode=collision_mode,
            attempt_count=100,
        )

    def _verify_applied_action(self, outcome: ActionOutcome) -> bool:
        if outcome.target_path is None:
            return False
        target = Path(outcome.target_path)
        source = Path(outcome.source_path)
        return target.exists() and target.is_file() and not source.exists()

    def _persist_applied_action(self, audit_run_id: uuid.UUID, action: PlannedAction, outcome: ActionOutcome) -> None:
        with transactional_session(self._session_factory) as session:
            file_row = session.get(FileInstance, action.file_id)
            if file_row is not None and outcome.target_path is not None:
                file_row.absolute_path = outcome.target_path

            session.add(
                ApplyAuditItem(
                    run_id=audit_run_id,
                    planned_action_id=action.id,
                    source_path=outcome.source_path,
                    target_path=outcome.target_path,
                    result="APPLIED",
                    error_message=None,
                )
            )

    def _persist_action_item(self, audit_run_id: uuid.UUID, outcome: ActionOutcome, error_message: str | None) -> None:
        with transactional_session(self._session_factory) as session:
            session.add(
                ApplyAuditItem(
                    run_id=audit_run_id,
                    planned_action_id=outcome.planned_action_id,
                    source_path=outcome.source_path,
                    target_path=outcome.target_path,
                    result=outcome.result,
                    error_message=error_message,
                )
            )

    def _complete_success(
        self,
        *,
        run_id: uuid.UUID,
        audit_run_id: uuid.UUID,
        total_actions: int,
        applied_actions: int,
        skipped_actions: int,
        collision_count: int,
    ) -> None:
        with transactional_session(self._session_factory) as session:
            run = self._lock_run(session, run_id)
            if run.state != RunStateDB.APPLYING:
                raise ApplyStateError(f"Apply completion requires APPLYING state. Current state: {run.state.value}")
            old_state = run.state.value
            validate_transition(RunState(run.state.value), RunState.COMPLETED)
            logger.info(
                "Transitioning run state",
                extra={
                    "run_id": str(run.id),
                    "phase": "apply",
                    "action_type": "",
                    "from": old_state,
                    "to": RunState.COMPLETED.value,
                },
            )
            run.state = RunStateDB.COMPLETED
            run.version += 1
            run.updated_at = func.now()

            audit = session.get(ApplyAuditRun, audit_run_id)
            if audit is not None:
                audit.status = "COMPLETED"
                audit.completed_at = _utcnow()
                audit.total_actions = total_actions
                audit.applied_actions = applied_actions
                audit.skipped_actions = skipped_actions
                audit.collision_count = collision_count
                audit.error_message = None

    def _complete_failure(
        self,
        *,
        run_id: uuid.UUID,
        audit_run_id: uuid.UUID,
        applied_actions: int,
        skipped_actions: int,
        collision_count: int,
        error_message: str,
    ) -> None:
        with transactional_session(self._session_factory) as session:
            run = self._lock_run(session, run_id)
            if run.state == RunStateDB.PLANNED:
                old_state = run.state.value
                validate_transition(RunState(run.state.value), RunState.APPLYING)
                logger.info(
                    "Transitioning run state",
                    extra={
                        "run_id": str(run.id),
                        "phase": "apply",
                        "action_type": "",
                        "from": old_state,
                        "to": RunState.APPLYING.value,
                    },
                )
                run.state = RunStateDB.APPLYING
                run.version += 1
                run.updated_at = func.now()

            if run.state != RunStateDB.APPLYING:
                raise ApplyStateError(
                    "Apply failure finalization requires APPLYING state before transition to FAILED. "
                    f"Current state: {run.state.value}"
                )

            if run.state == RunStateDB.APPLYING:
                old_state = run.state.value
                validate_transition(RunState(run.state.value), RunState.FAILED)
                logger.info(
                    "Transitioning run state",
                    extra={
                        "run_id": str(run.id),
                        "phase": "apply",
                        "action_type": "",
                        "from": old_state,
                        "to": RunState.FAILED.value,
                    },
                )
                run.state = RunStateDB.FAILED
                run.version += 1
                run.updated_at = func.now()

            audit = session.get(ApplyAuditRun, audit_run_id)
            if audit is not None:
                audit.status = "FAILED"
                audit.completed_at = _utcnow()
                audit.applied_actions = applied_actions
                audit.skipped_actions = skipped_actions
                audit.collision_count = collision_count
                audit.error_message = error_message

    def _record_apply_failure_event(self, run_id: uuid.UUID, message: str) -> None:
        with transactional_session(self._session_factory) as session:
            run = session.scalar(select(Run).where(Run.id == run_id).with_for_update())
            if run is None:
                return
            session.add(
                FailureEvent(
                    run_id=run_id,
                    phase=FailurePhase.APPLY,
                    error_code="APPLY_FAILED",
                    error_message=message,
                )
            )

    def _record_canonical_unreadable_event(self, run_id: uuid.UUID, message: str) -> None:
        """Append a durable drift/failure fact for unreadable canonical guards."""
        with transactional_session(self._session_factory) as session:
            run = session.scalar(select(Run).where(Run.id == run_id).with_for_update())
            if run is None:
                return
            existing = session.scalar(
                select(FailureEvent.id).where(
                    FailureEvent.run_id == run_id,
                    FailureEvent.phase == FailurePhase.APPLY,
                    FailureEvent.error_code == "CANONICAL_UNREADABLE",
                    FailureEvent.error_message == message,
                )
            )
            if existing is not None:
                return
            session.add(
                FailureEvent(
                    run_id=run_id,
                    phase=FailurePhase.APPLY,
                    error_code="CANONICAL_UNREADABLE",
                    error_message=message,
                )
            )

    def _canonical_guard_context_for_action(self, action: PlannedAction) -> CanonicalGuardContext | None:
        """Return unreadable canonical context when duplicate-destructive action must be skipped."""
        with transactional_session(self._session_factory) as session:
            file_row = session.get(FileInstance, action.file_id)
            if file_row is None:
                return None
            content_id = file_row.content_id

            active_duplicate_count = int(
                session.scalar(
                    select(func.count())
                    .select_from(FileInstance)
                    .where(
                        FileInstance.content_id == content_id,
                        FileInstance.status == FileInstanceStatus.ACTIVE.value,
                    )
                )
                or 0
            )
            duplicate_action = action.action_type in {"COLLISION_RESOLVED", "MARK_DUPLICATE"}
            if not duplicate_action and active_duplicate_count <= 1:
                return None

            assignment = session.execute(
                select(
                    CanonicalAssignment.canonical_instance_id,
                    CanonicalAssignment.assigned_at,
                    CanonicalAssignment.assignment_id,
                )
                .where(CanonicalAssignment.content_id == content_id)
                .order_by(CanonicalAssignment.assigned_at.desc(), CanonicalAssignment.assignment_id.desc())
                .limit(1)
            ).first()
            if assignment is None:
                return CanonicalGuardContext(
                    content_id=content_id,
                    canonical_instance_id=None,
                    canonical_path=None,
                    reason="canonical_assignment_missing",
                )

            canonical_instance_id = assignment[0]
            canonical_instance = session.get(FileInstance, canonical_instance_id)
            if canonical_instance is None:
                return CanonicalGuardContext(
                    content_id=content_id,
                    canonical_instance_id=canonical_instance_id,
                    canonical_path=None,
                    reason="canonical_instance_missing",
                )
            if canonical_instance.status != FileInstanceStatus.ACTIVE.value:
                return CanonicalGuardContext(
                    content_id=content_id,
                    canonical_instance_id=canonical_instance_id,
                    canonical_path=canonical_instance.absolute_path,
                    reason="canonical_instance_inactive",
                )

            runtime_path = _resolve_runtime_path(canonical_instance.absolute_path)
            if runtime_path is None:
                return CanonicalGuardContext(
                    content_id=content_id,
                    canonical_instance_id=canonical_instance_id,
                    canonical_path=canonical_instance.absolute_path,
                    reason="unresolvable_path",
                )
            try:
                readable = is_canonical_readable(runtime_path)
            except (OSError, IOError):
                readable = False
            if not readable:
                return CanonicalGuardContext(
                    content_id=content_id,
                    canonical_instance_id=canonical_instance_id,
                    canonical_path=str(runtime_path),
                    reason="unreadable",
                )
            return None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
