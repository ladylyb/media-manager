"""Run lifecycle persistence service.

Crash-safety model:
- All transitions run in explicit transaction boundaries.
- On exception, transaction rollback ensures no partial state update persists.
- Resume is only explicit via FAILED -> APPLYING transition.
- No implicit retries are performed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.core.naming import DEFAULT_CONTEXT, DEFAULT_OWNER, normalize_naming_strategy
from media_manager.app.core.errors import (
    InvalidRunTransitionError,
    RunNotFoundError,
    TransitionConflictError,
)
from media_manager.app.core.state_machine import RunState, validate_transition
from media_manager.app.persistence.base import transactional_session
from media_manager.app.persistence.models import FailureEvent, FailurePhase, NamingStrategyDB, Run, RunStateDB


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class RunSnapshot:
    id: uuid.UUID
    state: RunState
    created_at: datetime
    updated_at: datetime
    version: int
    owner: str
    context: str
    naming_strategy: str
    owner_context_override_confirmed: bool


def _to_snapshot(run: Run) -> RunSnapshot:
    return RunSnapshot(
        id=run.id,
        state=RunState(run.state.value),
        created_at=run.created_at,
        updated_at=run.updated_at,
        version=run.version,
        owner=run.owner,
        context=run.context,
        naming_strategy=run.naming_strategy.value,
        owner_context_override_confirmed=run.owner_context_override_confirmed,
    )


class RunService:
    """Deterministic run lifecycle service with explicit transaction boundaries."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create_run(
        self,
        *,
        owner: str = DEFAULT_OWNER,
        context: str = DEFAULT_CONTEXT,
        naming_strategy: str = NamingStrategyDB.SHARED_CANONICAL_NAME.value,
        owner_context_override_confirmed: bool = False,
    ) -> RunSnapshot:
        with transactional_session(self._session_factory) as session:
            run = Run(
                state=RunStateDB.CREATED,
                created_at=_now_utc(),
                updated_at=_now_utc(),
                version=1,
                owner=owner.strip() or DEFAULT_OWNER,
                context=context.strip() or DEFAULT_CONTEXT,
                naming_strategy=NamingStrategyDB(normalize_naming_strategy(naming_strategy)),
                owner_context_override_confirmed=bool(owner_context_override_confirmed),
            )
            session.add(run)
            session.flush()
            return _to_snapshot(run)

    def transition_run(self, run_id: uuid.UUID, next_state: RunState) -> RunSnapshot:
        with transactional_session(self._session_factory) as session:
            run = self._get_run_for_update(session, run_id)
            current = RunState(run.state.value)
            validate_transition(current, next_state)

            run.state = RunStateDB(next_state.value)
            run.updated_at = _now_utc()
            run.version += 1

            try:
                session.flush()
            except IntegrityError as exc:
                raise TransitionConflictError(
                    "Transition rejected by persistence constraints (e.g., APPLYING uniqueness)."
                ) from exc
            except InvalidRunTransitionError:
                raise

            return _to_snapshot(run)

    def append_failure(
        self,
        run_id: uuid.UUID,
        phase: FailurePhase,
        error_code: str,
        error_message: str,
    ) -> FailureEvent:
        with transactional_session(self._session_factory) as session:
            run_exists = session.scalar(select(Run.id).where(Run.id == run_id))
            if run_exists is None:
                raise RunNotFoundError(str(run_id))

            event = FailureEvent(
                run_id=run_id,
                phase=phase,
                error_code=error_code,
                error_message=error_message,
            )
            session.add(event)
            session.flush()
            return event

    def _get_run_for_update(self, session: Session, run_id: uuid.UUID) -> Run:
        stmt = select(Run).where(Run.id == run_id).with_for_update()
        run = session.scalar(stmt)
        if run is None:
            raise RunNotFoundError(str(run_id))
        return run
