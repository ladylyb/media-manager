"""Deterministic planning service (plan-only, no filesystem mutation)."""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.core.errors import PlanningStateError
from media_manager.app.core.filenames import (
    extract_taken_datetime,
    generate_canonical_filename,
    infer_media_type_from_extension,
)
from media_manager.app.core.hashing import sha256_file
from media_manager.app.core.logging_config import get_logger
from media_manager.app.core.mime import detect_mime
from media_manager.app.core.path_resolver import resolve_duplicate_path
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

logger = get_logger(__name__)


@dataclass(frozen=True)
class PlanningSummary:
    run_id: uuid.UUID
    scanned_count: int
    supported_count: int
    skipped_count: int
    move_actions: int
    noop_actions: int
    duplicate_actions: int

    def to_dict(self) -> dict[str, int | str]:
        return {
            "run_id": str(self.run_id),
            "scanned_count": self.scanned_count,
            "supported_count": self.supported_count,
            "skipped_count": self.skipped_count,
            "move_actions": self.move_actions,
            "noop_actions": self.noop_actions,
            "duplicate_actions": self.duplicate_actions,
        }


class PlanningService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def plan_run(self, run_id: uuid.UUID, input_paths: list[Path]) -> PlanningSummary:
        try:
            with transactional_session(self._session_factory) as session:
                run = self._lock_run(session, run_id)
                self._validate_planning_state(run)
                logger.info("Run started", extra={"run_id": str(run.id), "phase": "plan", "action_type": ""})

                old_state = run.state.value
                validate_transition(RunState(run.state.value), RunState.PLANNED)
                logger.info(
                    "Transitioning run state",
                    extra={
                        "run_id": str(run.id),
                        "phase": "plan",
                        "action_type": "",
                        "from": old_state,
                        "to": RunState.PLANNED.value,
                    },
                )
                run.state = RunStateDB.PLANNED
                run.version += 1
                run.updated_at = func.now()

                scanned_count = 0
                supported_count = 0
                skipped_count = 0
                move_actions = 0
                noop_actions = 0
                duplicate_actions = 0
                reserved_paths: set[str] = set()
                base_root = self._determine_base_root(input_paths)

                for candidate in sorted(input_paths, key=lambda p: p.resolve(strict=False).as_posix()):
                    action = self._plan_single_path(session, run, candidate, base_root, reserved_paths)
                    if action == PlannedActionType.RENAME.value:
                        scanned_count += 1
                        supported_count += 1
                        move_actions += 1
                    elif action == PlannedActionType.SKIP.value:
                        scanned_count += 1
                        supported_count += 1
                        noop_actions += 1
                    elif action == PlannedActionType.COLLISION_RESOLVED.value:
                        scanned_count += 1
                        supported_count += 1
                        duplicate_actions += 1
                    elif action == "SKIPPED_UNSUPPORTED_MIME":
                        skipped_count += 1

                summary = PlanningSummary(
                    run_id=run.id,
                    scanned_count=scanned_count,
                    supported_count=supported_count,
                    skipped_count=skipped_count,
                    move_actions=move_actions,
                    noop_actions=noop_actions,
                    duplicate_actions=duplicate_actions,
                )
                logger.info(
                    "Summary counts",
                    extra={
                        "run_id": str(run.id),
                        "phase": "plan",
                        "action_type": "",
                        "scanned": summary.scanned_count,
                        "supported": summary.supported_count,
                        "skipped": summary.skipped_count,
                        "moves": summary.move_actions,
                        "duplicates": summary.duplicate_actions,
                        "noop": summary.noop_actions,
                        "errors": 0,
                    },
                )
                logger.info(
                    "Run completed",
                    extra={
                        "run_id": str(run.id),
                        "phase": "plan",
                        "action_type": "",
                        "summary": summary.to_dict(),
                    },
                )
                return summary
        except Exception as exc:
            logger.exception("Plan failed", extra={"run_id": str(run_id), "phase": "plan", "action_type": ""})
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

    def _determine_base_root(self, input_paths: list[Path]) -> Path:
        if not input_paths:
            return Path.cwd()
        roots = [str(self._infer_root_from_source(path.resolve(strict=False))) for path in input_paths]
        return Path(os.path.commonpath(roots))

    def _infer_root_from_source(self, source: Path) -> Path:
        lower_parts = [part.lower() for part in source.parts]
        for marker in ("media", "inbox"):
            if marker in lower_parts:
                idx = lower_parts.index(marker)
                if idx > 0:
                    return Path(*source.parts[:idx])
        return source.parent

    def _resolve_destination_dir(
        self,
        *,
        base_root: Path,
        media_type: str,
        taken_datetime,
        is_duplicate: bool,
        source: Path,
        digest: str,
    ) -> Path:
        if is_duplicate:
            duplicate_rel = Path(resolve_duplicate_path(source, digest)).parent
            return base_root / duplicate_rel

        year = taken_datetime.strftime("%Y")
        month = taken_datetime.strftime("%m")
        if media_type == "VID":
            return base_root / "Media" / "Videos" / year / month
        return base_root / "Media" / "Photos" / year / month

    def _is_canonical_variant(self, filename: str, canonical_filename: str) -> bool:
        if filename == canonical_filename:
            return True
        stem = Path(canonical_filename).stem
        suffix = Path(canonical_filename).suffix
        pattern = re.compile(rf"^{re.escape(stem)}_\d+{re.escape(suffix)}$")
        return bool(pattern.fullmatch(filename))

    def _resolve_planning_collision(
        self,
        source: Path,
        destination: Path,
        reserved_paths: set[str],
    ) -> tuple[Path, bool]:
        destination_key = str(destination.resolve(strict=False))
        if source.resolve(strict=False) == destination.resolve(strict=False):
            reserved_paths.add(destination_key)
            return destination, False

        if destination_key not in reserved_paths and not destination.exists():
            reserved_paths.add(destination_key)
            return destination, False

        stem = destination.stem
        suffix = destination.suffix
        idx = 1
        while True:
            candidate = destination.with_name(f"{stem}_{idx}{suffix}")
            candidate_key = str(candidate.resolve(strict=False))
            if source.resolve(strict=False) == candidate.resolve(strict=False):
                reserved_paths.add(candidate_key)
                return candidate, False
            if candidate_key not in reserved_paths and not candidate.exists():
                reserved_paths.add(candidate_key)
                return candidate, True
            idx += 1

    def _get_existing_planned_action(
        self,
        session: Session,
        *,
        run_id: uuid.UUID,
        file_id: uuid.UUID,
        action_type: str,
        source_path: str,
        target_path: str | None,
    ) -> PlannedAction | None:
        stmt = select(PlannedAction).where(
            PlannedAction.run_id == run_id,
            PlannedAction.file_id == file_id,
            PlannedAction.action_type == action_type,
            PlannedAction.source_path == source_path,
        )
        if target_path is None:
            stmt = stmt.where(PlannedAction.target_path.is_(None))
        else:
            stmt = stmt.where(PlannedAction.target_path == target_path)
        return session.scalar(stmt.limit(1))

    def _get_existing_plan_for_file(
        self,
        session: Session,
        *,
        run_id: uuid.UUID,
        file_id: uuid.UUID,
        source_path: str,
    ) -> PlannedAction | None:
        stmt = (
            select(PlannedAction)
            .where(
                PlannedAction.run_id == run_id,
                PlannedAction.file_id == file_id,
                PlannedAction.source_path == source_path,
            )
            .limit(1)
        )
        return session.scalar(stmt)

    def _plan_single_path(
        self,
        session: Session,
        run: Run,
        candidate: Path,
        base_root: Path,
        reserved_paths: set[str],
    ) -> str:
        if not candidate.exists() or not candidate.is_file():
            raise ValueError(f"Planning input path is not a file: {candidate}")
        source_path = str(candidate.resolve(strict=False))

        mime_info = detect_mime(candidate)
        if not mime_info.is_supported:
            return "SKIPPED_UNSUPPORTED_MIME"
        media_type = infer_media_type_from_extension(candidate)
        if media_type is None:
            return "SKIPPED_UNSUPPORTED_MIME"

        digest = sha256_file(candidate)
        stat = candidate.stat()
        size_bytes = int(stat.st_size)
        taken_datetime = extract_taken_datetime(candidate)

        self._upsert_content_object(session, digest, size_bytes)
        file_row = self._upsert_file(
            session,
            source_path=source_path,
            mime_type=mime_info.mime_type,
            size_bytes=size_bytes,
            digest=digest,
        )

        original = self._deterministic_original_for_hash(session, digest)
        if original is not None and file_row.id != original.id:
            file_row.is_duplicate = True
            file_row.original_file_id = original.id
            is_duplicate = True
        else:
            file_row.is_duplicate = False
            file_row.original_file_id = None
            is_duplicate = False

        existing_for_file = self._get_existing_plan_for_file(
            session,
            run_id=run.id,
            file_id=file_row.id,
            source_path=source_path,
        )
        if existing_for_file is not None:
            if existing_for_file.target_path:
                reserved_paths.add(str(Path(existing_for_file.target_path).resolve(strict=False)))
            return existing_for_file.action_type

        canonical_filename = generate_canonical_filename(
            media_type=media_type,
            taken_datetime=taken_datetime,
            extension=candidate.suffix,
            owner="LL",
            context="General",
        )
        destination_dir = self._resolve_destination_dir(
            base_root=base_root,
            media_type=media_type,
            taken_datetime=taken_datetime,
            is_duplicate=is_duplicate,
            source=candidate,
            digest=digest,
        )
        if (
            candidate.resolve(strict=False).parent == destination_dir.resolve(strict=False)
            and self._is_canonical_variant(candidate.name, canonical_filename)
        ):
            planned_target_path = str(candidate.resolve(strict=False))
            action_type = PlannedActionType.SKIP.value
            reserved_paths.add(planned_target_path)
        else:
            desired_destination = destination_dir / canonical_filename
            final_destination, had_collision = self._resolve_planning_collision(
                candidate.resolve(strict=False),
                desired_destination.resolve(strict=False),
                reserved_paths,
            )
            planned_target_path = str(final_destination.resolve(strict=False))
            if candidate.resolve(strict=False) == final_destination.resolve(strict=False):
                action_type = PlannedActionType.SKIP.value
            elif had_collision:
                action_type = PlannedActionType.COLLISION_RESOLVED.value
            else:
                action_type = PlannedActionType.RENAME.value

        existing_plan = self._get_existing_planned_action(
            session,
            run_id=run.id,
            file_id=file_row.id,
            action_type=action_type,
            source_path=source_path,
            target_path=planned_target_path,
        )
        if existing_plan is None:
            plan = PlannedAction(
                run_id=run.id,
                file_id=file_row.id,
                action_type=action_type,
                source_path=source_path,
                target_path=planned_target_path,
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
