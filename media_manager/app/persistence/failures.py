"""Failure event append-only persistence service."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.core.errors import RunNotFoundError
from media_manager.app.persistence.base import transactional_session
from media_manager.app.persistence.models import FailureEvent, FailurePhase, Run


class FailureService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

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
            try:
                session.flush()
            except IntegrityError as exc:
                raise RuntimeError("Failure event append failed due to integrity constraint.") from exc
            return event
