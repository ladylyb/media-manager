"""Read-only service layer for Operator Console dashboard endpoints."""

from __future__ import annotations

import mimetypes
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.core.filenames import infer_media_type_from_extension
from media_manager.app.core.perf_artifacts import BASELINE_DIR, read_performance_artifact_json, load_baseline_json
from media_manager.app.core.perf_comparator import compare_to_baseline
from media_manager.app.persistence.models import (
    CanonicalAssignment,
    FileInstance,
    FileInstanceStatus,
    PlannedAction,
    Run,
)

PERF_RUN_DIR = Path("artifacts/perf/runs")
_WINDOWS_DRIVE_PATH_RE = re.compile(r"^([A-Za-z]):[\\/](.*)$")


@dataclass(frozen=True)
class DashboardSummary:
    """Aggregated dashboard counters for library state visibility."""

    total_files: int
    total_images: int
    total_videos: int
    duplicate_groups: int
    canonical_files: int
    total_runs: int

    def to_dict(self) -> dict[str, int]:
        """Return a JSON-serializable mapping."""
        return {
            "total_files": self.total_files,
            "total_images": self.total_images,
            "total_videos": self.total_videos,
            "duplicate_groups": self.duplicate_groups,
            "canonical_files": self.canonical_files,
            "total_runs": self.total_runs,
        }


@dataclass(frozen=True)
class LatestMetrics:
    """Most recent performance/regression metrics for the operator dashboard."""

    ingest_time_ms: float | None
    plan_time_ms: float | None
    apply_time_ms: float | None
    db_time_ms: float | None
    cache_hit_rate: float | None
    last_regression_status: str

    def to_dict(self) -> dict[str, float | str | None]:
        """Return a JSON-serializable mapping."""
        return {
            "ingest_time_ms": self.ingest_time_ms,
            "plan_time_ms": self.plan_time_ms,
            "apply_time_ms": self.apply_time_ms,
            "db_time_ms": self.db_time_ms,
            "cache_hit_rate": self.cache_hit_rate,
            "last_regression_status": self.last_regression_status,
        }


@dataclass(frozen=True)
class RunHistoryItem:
    """Run history row for operator console list/table rendering."""

    run_id: str
    timestamp: str
    files_processed: int
    duplicates_found: int
    runtime_ms: float | None
    regression_status: str

    def to_dict(self) -> dict[str, str | int | float | None]:
        """Return a JSON-serializable mapping."""
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "files_processed": self.files_processed,
            "duplicates_found": self.duplicates_found,
            "runtime_ms": self.runtime_ms,
            "regression_status": self.regression_status,
        }


@dataclass(frozen=True)
class DuplicateFileItem:
    """File row shown under a duplicate content group."""

    file_instance_id: str
    absolute_path: str
    media_type: str
    is_image: bool
    thumbnail_url: str | None

    def to_dict(self) -> dict[str, str | bool | None]:
        """Return a JSON-serializable mapping."""
        return {
            "file_instance_id": self.file_instance_id,
            "absolute_path": self.absolute_path,
            "media_type": self.media_type,
            "is_image": self.is_image,
            "thumbnail_url": self.thumbnail_url,
        }


@dataclass(frozen=True)
class DuplicateGroupItem:
    """Duplicate content group row for operator console browsing."""

    group_id: str
    files: tuple[DuplicateFileItem, ...]
    canonical_file: DuplicateFileItem | None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable mapping."""
        canonical = None
        if self.canonical_file is not None:
            canonical = {
                "file_instance_id": self.canonical_file.file_instance_id,
                "absolute_path": self.canonical_file.absolute_path,
            }
        return {
            "group_id": self.group_id,
            "files": [item.to_dict() for item in self.files],
            "canonical_file": canonical,
        }


class OperatorConsoleReadService:
    """Read-only service for Operator Console API endpoints."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        perf_run_dir: Path = PERF_RUN_DIR,
        baseline_dir: Path = BASELINE_DIR,
    ) -> None:
        self._session_factory = session_factory
        self._perf_run_dir = perf_run_dir
        self._baseline_dir = baseline_dir

    def get_dashboard_summary(self) -> DashboardSummary:
        """Return aggregated file/run counters for dashboard summary cards."""
        with self._session_factory() as session:
            total_files = self._count_total_files(session)
            total_images, total_videos = self._count_media_types(session)
            duplicate_groups = self._count_duplicate_groups(session)
            canonical_files = self._count_canonical_files(session)
            total_runs = self._count_total_runs(session)

        return DashboardSummary(
            total_files=total_files,
            total_images=total_images,
            total_videos=total_videos,
            duplicate_groups=duplicate_groups,
            canonical_files=canonical_files,
            total_runs=total_runs,
        )

    def get_latest_metrics(self) -> LatestMetrics:
        """Return metrics from the latest persisted perf artifact, if available."""
        artifact = self._load_latest_artifact()
        if artifact is None:
            return LatestMetrics(
                ingest_time_ms=None,
                plan_time_ms=None,
                apply_time_ms=None,
                db_time_ms=None,
                cache_hit_rate=None,
                last_regression_status="UNKNOWN",
            )

        ingest_time_ms = self._stage_duration_ms(artifact, "ingest")
        plan_time_ms = self._stage_duration_ms(artifact, "planner")
        apply_time_ms = self._stage_duration_ms(artifact, "apply")
        db_time_ms = self._total_db_time_ms(artifact)
        cache_hit_rate = self._extract_cache_hit_rate(
            artifact.get("planner") or artifact.get("ingest") or artifact.get("apply")
        )
        regression_status = self._latest_regression_status(artifact)

        return LatestMetrics(
            ingest_time_ms=ingest_time_ms,
            plan_time_ms=plan_time_ms,
            apply_time_ms=apply_time_ms,
            db_time_ms=db_time_ms,
            cache_hit_rate=cache_hit_rate,
            last_regression_status=regression_status,
        )

    def get_run_history(self, limit: int = 50) -> list[RunHistoryItem]:
        """Return latest run history rows with derived counts and status."""
        bounded_limit = max(1, int(limit))
        with self._session_factory() as session:
            runs = session.scalars(
                select(Run).order_by(Run.created_at.desc(), Run.id.desc()).limit(bounded_limit)
            ).all()
            if not runs:
                return []

            run_ids = [run.id for run in runs]
            files_processed_counts = self._planned_action_counts_by_run(session, run_ids)
            duplicate_counts = self._duplicate_action_counts_by_run(session, run_ids)

        artifacts_by_run_id = self._load_artifacts_by_run_id()
        items: list[RunHistoryItem] = []
        for run in runs:
            run_id_str = str(run.id)
            artifact = artifacts_by_run_id.get(run_id_str)
            runtime_ms = self._artifact_runtime_ms(artifact)
            if runtime_ms is None:
                runtime_ms = self._run_duration_ms_fallback(run.created_at, run.updated_at)

            files_processed = files_processed_counts.get(run.id, 0)
            duplicates_found = duplicate_counts.get(run.id, 0)
            regression_status = self._latest_regression_status(artifact) if artifact is not None else "UNKNOWN"

            items.append(
                RunHistoryItem(
                    run_id=run_id_str,
                    timestamp=run.created_at.isoformat(),
                    files_processed=int(files_processed),
                    duplicates_found=int(duplicates_found),
                    runtime_ms=runtime_ms,
                    regression_status=regression_status,
                )
            )
        return items

    def get_duplicate_groups(self, limit: int | None = None) -> list[DuplicateGroupItem]:
        """Return duplicate groups with active file instances and canonical mapping."""
        with self._session_factory() as session:
            duplicate_content_ids = self._duplicate_content_ids(session, limit)
            if not duplicate_content_ids:
                return []

            latest_canonical_by_content = self._latest_canonical_instance_by_content_id(
                session, duplicate_content_ids
            )

            instance_rows = session.execute(
                select(
                    FileInstance.content_id,
                    FileInstance.file_instance_id,
                    FileInstance.absolute_path,
                )
                .where(
                    FileInstance.status == FileInstanceStatus.ACTIVE.value,
                    FileInstance.content_id.in_(duplicate_content_ids),
                )
                .order_by(
                    FileInstance.content_id.asc(),
                    FileInstance.first_seen_at.asc(),
                    FileInstance.absolute_path.asc(),
                    FileInstance.file_instance_id.asc(),
                )
            ).all()

        grouped: dict[UUID, list[DuplicateFileItem]] = {}
        by_group_by_instance: dict[UUID, dict[str, DuplicateFileItem]] = {}
        for content_id, file_instance_id, absolute_path in instance_rows:
            instance_id_str = str(file_instance_id)
            media_type = infer_media_type_from_extension(Path(absolute_path)) or "OTHER"
            is_image = media_type == "IMG"
            file_item = DuplicateFileItem(
                file_instance_id=instance_id_str,
                absolute_path=absolute_path,
                media_type=media_type,
                is_image=is_image,
                thumbnail_url=f"/api/thumbnail/{instance_id_str}" if is_image else None,
            )
            grouped.setdefault(content_id, []).append(file_item)
            by_group_by_instance.setdefault(content_id, {})[instance_id_str] = file_item

        output: list[DuplicateGroupItem] = []
        for content_id in sorted(grouped.keys(), key=str):
            files = tuple(grouped[content_id])
            canonical_file: DuplicateFileItem | None = None
            canonical_instance_id = latest_canonical_by_content.get(content_id)
            if canonical_instance_id is not None:
                canonical_file = by_group_by_instance.get(content_id, {}).get(str(canonical_instance_id))
            output.append(
                DuplicateGroupItem(
                    group_id=str(content_id),
                    files=files,
                    canonical_file=canonical_file,
                )
            )
        return output

    def resolve_thumbnail_source(self, file_instance_id: UUID) -> tuple[Path, str] | None:
        """Resolve an active image file path and media type for thumbnail streaming."""
        with self._session_factory() as session:
            instance = session.scalar(
                select(FileInstance).where(
                    FileInstance.file_instance_id == file_instance_id,
                    FileInstance.status == FileInstanceStatus.ACTIVE.value,
                )
            )
            if instance is None:
                return None

        path = self._resolve_existing_instance_path(instance.absolute_path)
        if path is None:
            return None
        if infer_media_type_from_extension(path) != "IMG":
            return None
        try:
            with path.open("rb"):
                pass
        except OSError:
            return None
        mime, _ = mimetypes.guess_type(path.name)
        return path, (mime or "image/jpeg")

    def _resolve_existing_instance_path(self, raw_path: str) -> Path | None:
        """Resolve a durable file path with optional Windows->WSL fallback."""
        direct_path = Path(raw_path)
        if direct_path.exists() and direct_path.is_file():
            return direct_path

        mapped = self._map_windows_path_to_wsl(raw_path)
        if mapped is not None and mapped.exists() and mapped.is_file():
            return mapped
        return None

    def _map_windows_path_to_wsl(self, raw_path: str) -> Path | None:
        """Map `C:\\foo\\bar` style paths to `/mnt/c/foo/bar` for WSL hosts."""
        matched = _WINDOWS_DRIVE_PATH_RE.match(raw_path)
        if matched is None:
            return None
        drive = matched.group(1).lower()
        tail = matched.group(2).replace("\\", "/")
        return Path("/mnt") / drive / tail

    def _count_total_files(self, session: Session) -> int:
        value = session.scalar(
            select(func.count())
            .select_from(FileInstance)
            .where(FileInstance.status == FileInstanceStatus.ACTIVE.value)
        )
        return int(value or 0)

    def _count_media_types(self, session: Session) -> tuple[int, int]:
        paths = session.scalars(
            select(FileInstance.absolute_path).where(FileInstance.status == FileInstanceStatus.ACTIVE.value)
        ).all()
        images = 0
        videos = 0
        for raw_path in paths:
            media_type = infer_media_type_from_extension(Path(raw_path))
            if media_type == "IMG":
                images += 1
            elif media_type == "VID":
                videos += 1
        return images, videos

    def _count_duplicate_groups(self, session: Session) -> int:
        groups = (
            select(FileInstance.content_id)
            .where(FileInstance.status == FileInstanceStatus.ACTIVE.value)
            .group_by(FileInstance.content_id)
            .having(func.count(FileInstance.file_instance_id) > 1)
            .subquery()
        )
        value = session.scalar(select(func.count()).select_from(groups))
        return int(value or 0)

    def _count_canonical_files(self, session: Session) -> int:
        value = session.scalar(select(func.count(func.distinct(CanonicalAssignment.content_id))))
        return int(value or 0)

    def _count_total_runs(self, session: Session) -> int:
        value = session.scalar(select(func.count()).select_from(Run))
        return int(value or 0)

    def _planned_action_counts_by_run(self, session: Session, run_ids: list[UUID]) -> dict[UUID, int]:
        rows = session.execute(
            select(PlannedAction.run_id, func.count(PlannedAction.id))
            .where(PlannedAction.run_id.in_(run_ids))
            .group_by(PlannedAction.run_id)
        ).all()
        return {run_id: int(count) for run_id, count in rows}

    def _duplicate_action_counts_by_run(self, session: Session, run_ids: list[UUID]) -> dict[UUID, int]:
        rows = session.execute(
            select(PlannedAction.run_id, func.count(PlannedAction.id))
            .where(
                PlannedAction.run_id.in_(run_ids),
                PlannedAction.action_type.in_(("COLLISION_RESOLVED", "MARK_DUPLICATE")),
            )
            .group_by(PlannedAction.run_id)
        ).all()
        return {run_id: int(count) for run_id, count in rows}

    def _duplicate_content_ids(self, session: Session, limit: int | None) -> list[UUID]:
        stmt = (
            select(FileInstance.content_id)
            .where(FileInstance.status == FileInstanceStatus.ACTIVE.value)
            .group_by(FileInstance.content_id)
            .having(func.count(FileInstance.file_instance_id) > 1)
            .order_by(FileInstance.content_id.asc())
        )
        if limit is not None:
            stmt = stmt.limit(max(1, int(limit)))
        return list(session.scalars(stmt).all())

    def _latest_canonical_instance_by_content_id(
        self,
        session: Session,
        content_ids: list[UUID],
    ) -> dict[UUID, UUID]:
        if not content_ids:
            return {}
        latest_assignments = (
            select(
                CanonicalAssignment.content_id.label("content_id"),
                CanonicalAssignment.canonical_instance_id.label("canonical_instance_id"),
                func.row_number()
                .over(
                    partition_by=CanonicalAssignment.content_id,
                    order_by=(
                        CanonicalAssignment.assigned_at.desc(),
                        CanonicalAssignment.assignment_id.desc(),
                    ),
                )
                .label("rn"),
            )
            .where(CanonicalAssignment.content_id.in_(content_ids))
            .subquery()
        )
        rows = session.execute(
            select(latest_assignments.c.content_id, latest_assignments.c.canonical_instance_id).where(
                latest_assignments.c.rn == 1
            )
        ).all()
        return {content_id: canonical_instance_id for content_id, canonical_instance_id in rows}

    def _load_latest_artifact(self) -> dict[str, Any] | None:
        if not self._perf_run_dir.exists():
            return None
        candidates = sorted(
            self._perf_run_dir.glob("perf_artifact_*.json"),
            key=lambda p: (p.stat().st_mtime_ns, p.name),
            reverse=True,
        )
        for candidate in candidates:
            try:
                payload = read_performance_artifact_json(candidate)
            except Exception:
                continue
            if isinstance(payload, dict):
                return payload
        return None

    def _load_artifacts_by_run_id(self) -> dict[str, dict[str, Any]]:
        artifacts_by_run_id: dict[str, dict[str, Any]] = {}
        if not self._perf_run_dir.exists():
            return artifacts_by_run_id

        candidates = sorted(self._perf_run_dir.glob("perf_artifact_*.json"), key=lambda p: (p.stat().st_mtime_ns, p.name))
        for candidate in candidates:
            try:
                payload = read_performance_artifact_json(candidate)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            run_id = payload.get("run_id")
            if isinstance(run_id, str) and run_id:
                artifacts_by_run_id[run_id] = payload
        return artifacts_by_run_id

    def _stage_duration_ms(self, artifact: dict[str, Any], stage_name: str) -> float | None:
        stage_payload = artifact.get(stage_name)
        if not isinstance(stage_payload, dict):
            return None
        duration = stage_payload.get("duration_ms")
        if isinstance(duration, bool):
            return None
        if isinstance(duration, (int, float)):
            return float(duration)
        return None

    def _artifact_runtime_ms(self, artifact: dict[str, Any] | None) -> float | None:
        if artifact is None:
            return None
        stages = (
            self._stage_duration_ms(artifact, "ingest"),
            self._stage_duration_ms(artifact, "planner"),
            self._stage_duration_ms(artifact, "apply"),
        )
        numeric = [value for value in stages if value is not None]
        if not numeric:
            return None
        return float(sum(numeric))

    def _run_duration_ms_fallback(self, created_at: datetime, updated_at: datetime) -> float:
        delta_ms = (updated_at - created_at).total_seconds() * 1000.0
        return 0.0 if delta_ms < 0 else float(delta_ms)

    def _extract_db_time_ms(self, stage_payload: Any) -> float | None:
        if not isinstance(stage_payload, dict):
            return None
        direct = stage_payload.get("db_query_ms_total")
        if isinstance(direct, (int, float)) and not isinstance(direct, bool):
            return float(direct)
        counters = stage_payload.get("counters")
        if isinstance(counters, dict):
            nested = counters.get("db_query_ms_total")
            if isinstance(nested, (int, float)) and not isinstance(nested, bool):
                return float(nested)
        return None

    def _total_db_time_ms(self, artifact: dict[str, Any]) -> float | None:
        values = [
            self._extract_db_time_ms(artifact.get("ingest")),
            self._extract_db_time_ms(artifact.get("planner")),
            self._extract_db_time_ms(artifact.get("apply")),
        ]
        numeric = [value for value in values if value is not None]
        if not numeric:
            return None
        return float(sum(numeric))

    def _extract_cache_hit_rate(self, stage_payload: Any) -> float | None:
        if not isinstance(stage_payload, dict):
            return None
        direct = stage_payload.get("hit_rate")
        value: float | None = None
        if isinstance(direct, (int, float)) and not isinstance(direct, bool):
            value = float(direct)
        else:
            counters = stage_payload.get("counters")
            if isinstance(counters, dict):
                nested = counters.get("hit_rate")
                if isinstance(nested, (int, float)) and not isinstance(nested, bool):
                    value = float(nested)
        if value is None:
            return None
        return value * 100.0 if value <= 1.0 else value

    def _latest_regression_status(self, artifact: dict[str, Any]) -> str:
        dataset_id = artifact.get("dataset_id")
        env_class = artifact.get("env_class")
        if not isinstance(dataset_id, str) or not dataset_id:
            return "UNKNOWN"
        if not isinstance(env_class, str) or not env_class:
            return "UNKNOWN"

        try:
            baseline = load_baseline_json(
                dataset_id,
                env_class,
                baseline_dir=self._baseline_dir,
                expected_metrics_version=None,
            )
            result = compare_to_baseline(artifact, baseline)
            summary = result.get("summary")
            if isinstance(summary, dict):
                status = summary.get("overall_pass_fail")
                if status in {"PASS", "FAIL"}:
                    return status
        except Exception:
            return "UNKNOWN"
        return "UNKNOWN"
