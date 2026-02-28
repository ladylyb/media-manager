"""Deterministic apply service skeleton (no filesystem mutation)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.core.errors import ApplyStateError, RunNotFoundError
from media_manager.app.core.state_machine import RunState, validate_transition
from media_manager.app.persistence.base import transactional_session
from media_manager.app.persistence.models import FailureEvent, FailurePhase, PlannedAction, Run, RunStateDB


@dataclass(frozen=True)
class ApplySummary:
    applied_count: int
    skipped_count: int
    duplicates_count: int
    noop_count: int
    errors_count: int
    moves_count: int


class ApplyService:
    """Transactional apply-stage scaffold that simulates execution only."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def apply_run(self, run_id: uuid.UUID) -> ApplySummary:
        try:
            with transactional_session(self._session_factory) as session:
                run = self._lock_run(session, run_id)
                self._validate_apply_state(run)

                validate_transition(RunState(run.state.value), RunState.APPLYING)
                run.state = RunStateDB.APPLYING
                run.version += 1
                run.updated_at = func.now()

                actions = session.scalars(
                    select(PlannedAction)
                    .where(PlannedAction.run_id == run_id)
                    .order_by(
                        PlannedAction.action_type.asc(),
                        PlannedAction.source_path.asc(),
                        PlannedAction.target_path.asc(),
                        PlannedAction.id.asc(),
                    )
                ).all()

                applied_count = 0
                skipped_count = 0
                duplicates_count = 0
                noop_count = 0
                moves_count = 0

                for action in actions:
                    self._simulate_execute(action)
                    if action.action_type == "MOVE":
                        moves_count += 1
                        applied_count += 1
                    elif action.action_type == "MARK_DUPLICATE":
                        duplicates_count += 1
                        applied_count += 1
                    elif action.action_type == "NOOP":
                        noop_count += 1
                        applied_count += 1
                    else:
                        skipped_count += 1

                validate_transition(RunState(run.state.value), RunState.COMPLETED)
                run.state = RunStateDB.COMPLETED
                run.version += 1
                run.updated_at = func.now()

                summary = ApplySummary(
                    applied_count=applied_count,
                    skipped_count=skipped_count,
                    duplicates_count=duplicates_count,
                    noop_count=noop_count,
                    errors_count=0,
                    moves_count=moves_count,
                )
                return summary
        except Exception as exc:
            self._record_apply_failure(run_id, str(exc))
            raise

    def _lock_run(self, session: Session, run_id: uuid.UUID) -> Run:
        stmt = select(Run).where(Run.id == run_id).with_for_update()
        run = session.scalar(stmt)
        if run is None:
            raise RunNotFoundError(str(run_id))
        return run

    def _validate_apply_state(self, run: Run) -> None:
        if run.state != RunStateDB.PLANNED:
            raise ApplyStateError(f"Apply is only allowed from PLANNED. Current state: {run.state.value}")

    def _simulate_execute(self, action: PlannedAction) -> None:
        _ = action

    def _record_apply_failure(self, run_id: uuid.UUID, message: str) -> None:
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

            current = RunState(run.state.value)
            try:
                if current == RunState.PLANNED:
                    validate_transition(current, RunState.APPLYING)
                    run.state = RunStateDB.APPLYING
                    run.version += 1
                    run.updated_at = func.now()
                    current = RunState.APPLYING

                if current == RunState.APPLYING:
                    validate_transition(current, RunState.FAILED)
                    run.state = RunStateDB.FAILED
                    run.version += 1
                    run.updated_at = func.now()
            except Exception:
                # Best-effort failure recording: do not mask the original apply exception.
                return
