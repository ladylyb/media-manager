"""Deterministic planning service (plan-only, no filesystem mutation)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.core.date_extraction import extract_best_date
from media_manager.app.core.errors import PlanningStateError
from media_manager.app.core.hashing import sha256_file
from media_manager.app.core.mime import detect_mime
from media_manager.app.core.path_resolver import resolve_canonical_path, resolve_duplicate_path
from media_manager.app.core.state_machine import RunState, validate_transition
from media_manager.app.persistence.base import transactional_session
from media_manager.app.persistence.models import (
    ContentObject,
    FailureEvent,
    FailurePhase,
    File,
    PlannedAction,
    PlannedActionType,
    Run,
    RunStateDB,
)


@dataclass(frozen=True)
class PlanningSummary:
    run_id: uuid.UUID
    scanned: int
    move_actions: int
    noop_actions: int
    duplicate_actions: int


class PlanningService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def plan_run(self, run_id: uuid.UUID, input_paths: list[Path]) -> PlanningSummary:
        try:
            with transactional_session(self._session_factory) as session:
                run = self._lock_run(session, run_id)
                self._validate_planning_state(run)

                validate_transition(RunState(run.state.value), RunState.PLANNED)
                run.state = RunStateDB.PLANNED
                run.version += 1
                run.updated_at = func.now()

                scanned = 0
                move_actions = 0
                noop_actions = 0
                duplicate_actions = 0

                for candidate in sorted(input_paths, key=lambda p: str(p)):
                    scanned += 1
                    action = self._plan_single_path(session, run, candidate)
                    if action == PlannedActionType.MOVE.value:
                        move_actions += 1
                    elif action == PlannedActionType.NOOP.value:
                        noop_actions += 1
                    elif action == PlannedActionType.MARK_DUPLICATE.value:
                        duplicate_actions += 1

                return PlanningSummary(
                    run_id=run.id,
                    scanned=scanned,
                    move_actions=move_actions,
                    noop_actions=noop_actions,
                    duplicate_actions=duplicate_actions,
                )
        except Exception as exc:
            self._record_planning_failure(run_id, "PLANNING_FAILED", str(exc))
            raise

    def _lock_run(self, session: Session, run_id: uuid.UUID) -> Run:
        stmt = select(Run).where(Run.id == run_id).with_for_update()
        run = session.scalar(stmt)
        if run is None:
            raise PlanningStateError(f"Run not found: {run_id}")
        return run

    def _validate_planning_state(self, run: Run) -> None:
        if run.state != RunStateDB.CREATED:
            raise PlanningStateError(
                f"Planning is only allowed from CREATED. Current state: {run.state.value}"
            )

    def _upsert_content_object(self, session: Session, digest: str, size_bytes: int) -> None:
        stmt = insert(ContentObject).values(hash=digest, size_bytes=size_bytes)
        stmt = stmt.on_conflict_do_update(
            index_elements=[ContentObject.hash],
            set_={"size_bytes": size_bytes},
        )
        session.execute(stmt)

    def _upsert_file(
        self,
        session: Session,
        *,
        source_path: str,
        mime_type: str,
        size_bytes: int,
        digest: str,
    ) -> File:
        existing = session.scalar(select(File).where(File.path == source_path).with_for_update())
        if existing is not None:
            existing.mime_type = mime_type
            existing.size_bytes = size_bytes
            existing.hash = digest
            existing.is_duplicate = False
            existing.original_file_id = None
            session.flush()
            return existing

        record = File(
            path=source_path,
            mime_type=mime_type,
            size_bytes=size_bytes,
            hash=digest,
            is_duplicate=False,
            original_file_id=None,
        )
        session.add(record)
        session.flush()
        return record

    def _deterministic_original_for_hash(self, session: Session, digest: str) -> File | None:
        stmt = (
            select(File)
            .where(File.hash == digest)
            .order_by(File.created_at.asc(), File.id.asc())
            .limit(1)
        )
        return session.scalar(stmt)

    def _source_matches_canonical(self, source: Path, target: str) -> bool:
        source_posix = source.as_posix()
        return source_posix == target or source_posix.endswith(f"/{target}")

    def _plan_single_path(self, session: Session, run: Run, candidate: Path) -> str:
        if not candidate.exists() or not candidate.is_file():
            raise ValueError(f"Planning input path is not a file: {candidate}")

        digest = sha256_file(candidate)
        stat = candidate.stat()
        size_bytes = int(stat.st_size)

        mime_info = detect_mime(candidate)
        date_info = extract_best_date(
            path=candidate,
            mime_type=mime_info.mime_type,
            stat_meta={"mtime": stat.st_mtime, "ctime": stat.st_ctime},
            filename=candidate.name,
        )

        self._upsert_content_object(session, digest, size_bytes)
        file_row = self._upsert_file(
            session,
            source_path=str(candidate),
            mime_type=mime_info.mime_type,
            size_bytes=size_bytes,
            digest=digest,
        )

        original = self._deterministic_original_for_hash(session, digest)
        if original is not None and file_row.id != original.id:
            file_row.is_duplicate = True
            file_row.original_file_id = original.id
            target = resolve_duplicate_path(candidate, digest)
            action_type = PlannedActionType.MARK_DUPLICATE.value
        else:
            file_row.is_duplicate = False
            file_row.original_file_id = None
            target = resolve_canonical_path(candidate, mime_info.media_kind, date_info, digest)
            action_type = (
                PlannedActionType.NOOP.value
                if self._source_matches_canonical(candidate, target)
                else PlannedActionType.MOVE.value
            )

        plan = PlannedAction(
            run_id=run.id,
            file_id=file_row.id,
            action_type=action_type,
            source_path=str(candidate),
            target_path=target if action_type != PlannedActionType.NOOP.value else None,
        )
        session.add(plan)
        session.flush()
        return action_type

    def _record_planning_failure(self, run_id: uuid.UUID, code: str, message: str) -> None:
        with transactional_session(self._session_factory) as session:
            run = session.scalar(select(Run).where(Run.id == run_id).with_for_update())
            if run is None:
                return

            session.add(
                FailureEvent(
                    run_id=run_id,
                    phase=FailurePhase.PLANNING,
                    error_code=code,
                    error_message=message,
                )
            )

            current = RunState(run.state.value)
            try:
                validate_transition(current, RunState.FAILED)
            except Exception:
                return

            run.state = RunStateDB.FAILED
            run.version += 1
            run.updated_at = func.now()
