"""Deterministic planning service (DB-first, no hashing in planner)."""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.core.config import resolve_required_metadata_codes
from media_manager.app.core.errors import MissingRequiredMetadataError, PlanningStateError
from media_manager.app.core.filenames import generate_canonical_filename, infer_media_type_from_extension
from media_manager.app.core.logging_config import get_logger
from media_manager.app.core.metadata_cache import MetadataCache
from media_manager.app.core.state_machine import RunState, validate_transition
from media_manager.app.persistence.base import transactional_session
from media_manager.app.persistence.ingest import ingest_paths_in_session
from media_manager.app.persistence.models import (
    FailureEvent,
    FailurePhase,
    FileContent,
    FileInstance,
    FileInstanceStatus,
    MediaMetadata,
    MetadataCode,
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
        self._metadata_cache = MetadataCache()
        self._metadata_lookup_db_time_s = 0.0
        self._metadata_lookup_cache_time_s = 0.0

    def plan_run(
        self,
        run_id: uuid.UUID,
        input_paths: list[Path] | None = None,
        *,
        ingest_if_needed: bool = True,
        required_metadata_codes: set[str] | None = None,
        strict_missing_metadata: bool = False,
    ) -> PlanningSummary:
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

                self._metadata_cache.clear()
                self._metadata_lookup_db_time_s = 0.0
                self._metadata_lookup_cache_time_s = 0.0
                batch_size = self._get_metadata_batch_size()

                reserved_paths: set[str] = set()
                scanned_count = 0
                supported_count = 0
                skipped_count = 0
                move_actions = 0
                noop_actions = 0
                duplicate_actions = 0
                canonical_instances_processed = 0
                skipped_inactive_instances = 0
                skipped_missing_metadata_count = 0
                total_required_codes_missing = 0
                resolved_required_codes = (
                    {code.upper() for code in required_metadata_codes}
                    if required_metadata_codes is not None
                    else resolve_required_metadata_codes()
                )

                rows = self._load_candidate_instances(session, input_paths)
                if input_paths and ingest_if_needed:
                    ingest_paths_in_session(session, sorted(input_paths, key=lambda p: p.resolve(strict=False).as_posix()))
                    self._ensure_canonical_instances(session)
                    rows = self._load_candidate_instances(session, input_paths)
                base_root = self._determine_base_root([Path(row.absolute_path) for row in rows])

                for instance in rows:
                    if instance.status != FileInstanceStatus.ACTIVE.value:
                        skipped_inactive_instances += 1
                        skipped_count += 1
                        continue
                    canonical_instances_processed += 1
                    action, missing_required_count = self._plan_single_instance(
                        session,
                        run,
                        instance,
                        base_root,
                        reserved_paths,
                        resolved_required_codes,
                        strict_missing_metadata,
                    )
                    total_required_codes_missing += missing_required_count
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
                    elif action == "SKIPPED_MISSING_METADATA":
                        skipped_count += 1
                        skipped_missing_metadata_count += 1
                    else:
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
                        "skipped_missing_metadata_count": skipped_missing_metadata_count,
                        "total_required_codes_missing": total_required_codes_missing,
                    },
                )
                cache_stats = self._metadata_cache.stats()
                logger.info(
                    "Perf metric",
                    extra={
                        "run_id": str(run.id),
                        "phase": "plan",
                        "action": "PERF",
                        "duration_s": f"{self._metadata_lookup_db_time_s + self._metadata_lookup_cache_time_s:.6f}",
                        "files_count": supported_count,
                        "batch_size": batch_size,
                        "cache_hits": cache_stats.hits,
                        "cache_misses": cache_stats.misses,
                        "codes_extracted": (
                            f"lookup_db_s={self._metadata_lookup_db_time_s:.6f},"
                            f"lookup_cache_s={self._metadata_lookup_cache_time_s:.6f},"
                            f"hit_rate={cache_stats.hit_rate:.4f},"
                            f"canonical_instances_processed={canonical_instances_processed},"
                            f"skipped_inactive_instances={skipped_inactive_instances},"
                            f"skipped_missing_metadata_count={skipped_missing_metadata_count},"
                            f"total_required_codes_missing={total_required_codes_missing}"
                        ),
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

    def _get_metadata_batch_size(self) -> int:
        raw = os.getenv("METADATA_UPSERT_BATCH_SIZE", "1000")
        try:
            value = int(raw)
        except ValueError:
            return 1000
        return min(max(value, 1), 50_000)

    def _lock_run(self, session: Session, run_id: uuid.UUID) -> Run:
        stmt = select(Run).where(Run.id == run_id).with_for_update()
        run = session.scalar(stmt)
        if run is None:
            raise PlanningStateError(f"Run not found: {run_id}")
        return run

    def _validate_planning_state(self, run: Run) -> None:
        if run.state != RunStateDB.CREATED:
            raise PlanningStateError(f"Planning is only allowed from CREATED. Current state: {run.state.value}")

    def _load_candidate_instances(self, session: Session, input_paths: list[Path] | None) -> list[FileInstance]:
        stmt = (
            select(FileInstance)
            .join(FileContent, FileContent.canonical_file_instance_id == FileInstance.file_instance_id)
            .order_by(FileInstance.absolute_path.asc(), FileInstance.file_instance_id.asc())
        )
        if input_paths:
            normalized = sorted({str(path.resolve(strict=False)) for path in input_paths})
            if not normalized:
                return []
            stmt = stmt.where(FileInstance.absolute_path.in_(normalized))
        return session.scalars(stmt).all()

    def _ensure_canonical_instances(self, session: Session) -> None:
        session.execute(
            text(
                """
                WITH canonical AS (
                    SELECT DISTINCT ON (fi.content_id)
                        fi.content_id,
                        fi.file_instance_id
                    FROM file_instances fi
                    ORDER BY fi.content_id, fi.first_seen_at ASC, fi.file_instance_id ASC
                )
                UPDATE file_contents fc
                SET canonical_file_instance_id = canonical.file_instance_id
                FROM canonical
                WHERE fc.content_id = canonical.content_id
                  AND fc.canonical_file_instance_id IS NULL
                """
            )
        )

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

    def _load_metadata_by_content_id(self, session: Session, content_id: uuid.UUID) -> dict[str, str]:
        cache_key = str(content_id)
        t_cache = perf_counter()
        cached = self._metadata_cache.get(cache_key)
        if cached is not None:
            self._metadata_lookup_cache_time_s += perf_counter() - t_cache
            return cached
        self._metadata_lookup_cache_time_s += perf_counter() - t_cache

        t_db = perf_counter()
        rows = session.execute(
            select(MetadataCode.code_type, MediaMetadata.decode_value)
            .join(MediaMetadata, MediaMetadata.code_id == MetadataCode.id)
            .where(MediaMetadata.content_id == content_id)
        ).all()
        metadata = {code_type: decode_value for code_type, decode_value in rows}
        self._metadata_lookup_db_time_s += perf_counter() - t_db
        self._metadata_cache.set(cache_key, metadata)
        return metadata

    def _resolve_destination_dir(
        self,
        *,
        base_root: Path,
        media_type: str,
        taken_datetime: datetime,
    ) -> Path:
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

    def _plan_single_instance(
        self,
        session: Session,
        run: Run,
        instance: FileInstance,
        base_root: Path,
        reserved_paths: set[str],
        required_metadata_codes: set[str],
        strict_missing_metadata: bool,
    ) -> tuple[str, int]:
        source = Path(instance.absolute_path)
        source_path = str(source.resolve(strict=False))
        existing_for_file = self._get_existing_plan_for_file(
            session, run_id=run.id, file_id=instance.file_instance_id, source_path=source_path
        )
        if existing_for_file is not None:
            if existing_for_file.target_path:
                reserved_paths.add(str(Path(existing_for_file.target_path).resolve(strict=False)))
            return existing_for_file.action_type, 0

        metadata_map = self._load_metadata_by_content_id(session, instance.content_id)
        present_codes = {code.upper() for code in metadata_map.keys()}
        missing_required = sorted(required_metadata_codes - present_codes)
        if missing_required:
            if strict_missing_metadata:
                raise MissingRequiredMetadataError(
                    content_id=str(instance.content_id),
                    file_instance_id=str(instance.file_instance_id),
                    missing_codes=missing_required,
                )
            logger.warning(
                "Missing required metadata",
                extra={
                    "run_id": str(run.id),
                    "phase": "plan",
                    "action": "SKIPPED",
                    "content_id": str(instance.content_id),
                    "file_instance_id": str(instance.file_instance_id),
                    "missing_codes": missing_required,
                    "strict_missing_metadata": strict_missing_metadata,
                    "codes_extracted": ",".join(sorted(metadata_map.keys())),
                },
            )
            return "SKIPPED_MISSING_METADATA", len(missing_required)

        owner = metadata_map.get("OWNER")
        context = metadata_map.get("CONTEXT")
        taken_dt_raw = metadata_map.get("TAKEN_DT")
        if not owner or not context or not taken_dt_raw:
            return "SKIPPED_MISSING_METADATA", 0

        media_type = infer_media_type_from_extension(source)
        if media_type is None:
            return "SKIPPED_UNSUPPORTED_MIME", 0

        taken_datetime = datetime.fromisoformat(taken_dt_raw)
        canonical_filename = generate_canonical_filename(
            media_type=media_type,
            taken_datetime=taken_datetime,
            extension=source.suffix,
            owner=owner,
            context=context,
        )
        destination_dir = self._resolve_destination_dir(
            base_root=base_root,
            media_type=media_type,
            taken_datetime=taken_datetime,
        )
        if (
            source.resolve(strict=False).parent == destination_dir.resolve(strict=False)
            and self._is_canonical_variant(source.name, canonical_filename)
        ):
            planned_target_path = str(source.resolve(strict=False))
            action_type = PlannedActionType.SKIP.value
            reserved_paths.add(planned_target_path)
        else:
            desired_destination = destination_dir / canonical_filename
            final_destination, had_collision = self._resolve_planning_collision(
                source.resolve(strict=False),
                desired_destination.resolve(strict=False),
                reserved_paths,
            )
            planned_target_path = str(final_destination.resolve(strict=False))
            if source.resolve(strict=False) == final_destination.resolve(strict=False):
                action_type = PlannedActionType.SKIP.value
            elif had_collision:
                action_type = PlannedActionType.COLLISION_RESOLVED.value
            else:
                action_type = PlannedActionType.RENAME.value

        existing_plan = self._get_existing_planned_action(
            session,
            run_id=run.id,
            file_id=instance.file_instance_id,
            action_type=action_type,
            source_path=source_path,
            target_path=planned_target_path,
        )
        if existing_plan is None:
            plan = PlannedAction(
                run_id=run.id,
                file_id=instance.file_instance_id,
                action_type=action_type,
                source_path=source_path,
                target_path=planned_target_path,
            )
            session.add(plan)
            session.flush()
        return action_type, 0

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
