"""Read-only service layer for Operator Console dashboard endpoints."""

from __future__ import annotations

import hashlib
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, aliased, sessionmaker

from media_manager.app.core.filenames import infer_media_type_from_extension
from media_manager.app.core.hashing import sha256_file
from media_manager.app.core.logging_config import get_logger
from media_manager.app.core.perf_artifacts import BASELINE_DIR, read_performance_artifact_json, load_baseline_json
from media_manager.app.core.perf_comparator import compare_to_baseline
from media_manager.app.persistence.discovery_query import (
    DiscoveryQueryParams,
    DiscoveryQueryService,
)
from media_manager.app.persistence.media_file_queries import (
    get_history_by_path,
    get_reappearances_after_deleted,
    get_rows_by_hash,
    get_rows_by_status,
)
from media_manager.app.persistence.models import (
    ApplyAuditRun,
    CanonicalAssignment,
    CanonicalRecomputeRun,
    FileInstance,
    FileInstanceStatus,
    MediaFile,
    MediaFileStatus,
    OperationRun,
    OperationRunStatus,
    OperationRunType,
    PlannedAction,
    Run,
    Tag,
    TagSource,
)

PERF_RUN_DIR = Path("artifacts/perf/runs")
_WINDOWS_DRIVE_PATH_RE = re.compile(r"^([A-Za-z]):[\\/](.*)$")
logger = get_logger(__name__)


def _env_truthy(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _video_thumbnails_enabled() -> bool:
    return _env_truthy("MEDIA_MANAGER_VIDEO_THUMBNAILS_ENABLED")


def _video_thumbnail_cache_dir() -> Path:
    raw = (os.getenv("MEDIA_MANAGER_VIDEO_THUMBNAIL_CACHE_DIR", "") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path(tempfile.gettempdir()) / "media-manager" / "video-thumbnails"


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
    """Unified operation run history row for operator console list/table rendering."""

    operation_run_id: str
    operation_type: str
    status: str
    started_at: str
    completed_at: str | None
    duration_ms: float | None
    linked_run_id: str | None
    context: dict[str, object]
    error_message: str | None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable mapping."""
        return {
            "operation_run_id": self.operation_run_id,
            "operation_type": self.operation_type,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "linked_run_id": self.linked_run_id,
            "context": dict(self.context),
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class InternalRunHistoryItem:
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


@dataclass(frozen=True)
class CanonicalGalleryItem:
    """Canonical gallery card item returned to Operator Console."""

    id: str
    filename: str
    file_type: str
    media_url: str
    poster_url: str | None = None
    matched_tags: tuple[str, ...] = ()
    top_confidence_score: float | None = None
    sort_tag_name: str | None = None

    def to_dict(self) -> dict[str, str | list[str] | float | None]:
        """Return a JSON-serializable mapping."""
        return {
            "id": self.id,
            "filename": self.filename,
            "file_type": self.file_type,
            "media_url": self.media_url,
            "poster_url": self.poster_url,
            "matched_tags": list(self.matched_tags),
            "top_confidence_score": self.top_confidence_score,
            "sort_tag_name": self.sort_tag_name,
        }


@dataclass(frozen=True)
class CanonicalGalleryPage:
    """Paginated canonical gallery response payload."""

    total_count: int
    page: int
    limit: int
    total_pages: int
    items: tuple[CanonicalGalleryItem, ...]

    def to_dict(self) -> dict[str, int | list[dict[str, str | list[str] | float | None]]]:
        """Return a JSON-serializable mapping."""
        return {
            "total_count": self.total_count,
            "page": self.page,
            "limit": self.limit,
            "total_pages": self.total_pages,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass(frozen=True)
class CanonicalGalleryDetail:
    """Detailed canonical media payload for full-page gallery preview."""

    id: str
    filename: str
    file_type: str
    media_url: str
    absolute_path: str

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-serializable mapping."""
        return {
            "id": self.id,
            "filename": self.filename,
            "file_type": self.file_type,
            "media_url": self.media_url,
            "absolute_path": self.absolute_path,
        }


@dataclass(frozen=True)
class MediaFileLedgerItem:
    """Read-only Phase 13 media_file ledger row for operator diagnostics."""

    id: str
    current_path: str | None
    discovered_path: str | None
    size_bytes: int | None
    hash_sha256: str | None
    status: str
    discovered_at: str
    ingested_at: str | None
    deleted_at: str | None

    def to_dict(self) -> dict[str, str | int | None]:
        """Return a JSON-serializable mapping."""
        return {
            "id": self.id,
            "current_path": self.current_path,
            "discovered_path": self.discovered_path,
            "size_bytes": self.size_bytes,
            "hash_sha256": self.hash_sha256,
            "status": self.status,
            "discovered_at": self.discovered_at,
            "ingested_at": self.ingested_at,
            "deleted_at": self.deleted_at,
        }


@dataclass(frozen=True)
class MediaFileLedgerPage:
    """Deterministic paginated ledger rows for `/api/media-file/*` endpoints."""

    total_count: int
    page: int
    limit: int
    total_pages: int
    items: tuple[MediaFileLedgerItem, ...]

    def to_dict(self) -> dict[str, int | list[dict[str, str | int | None]]]:
        """Return a JSON-serializable mapping."""
        return {
            "total_count": self.total_count,
            "page": self.page,
            "limit": self.limit,
            "total_pages": self.total_pages,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass(frozen=True)
class LedgerDayCount:
    """Day-bucketed count row for ledger analytics trends."""

    day: str
    count: int

    def to_dict(self) -> dict[str, str | int]:
        """Return a JSON-serializable mapping."""
        return {
            "day": self.day,
            "count": self.count,
        }


@dataclass(frozen=True)
class MediaFileLedgerAnalytics:
    """Aggregate analytics payload for Phase 13 ledger-only reporting."""

    totals: dict[str, int]
    by_status: dict[str, int]
    ingested_per_day: tuple[LedgerDayCount, ...]
    deleted_per_day: tuple[LedgerDayCount, ...]
    reappearances_per_day: tuple[LedgerDayCount, ...]
    window: dict[str, str]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable mapping."""
        return {
            "totals": dict(self.totals),
            "by_status": dict(self.by_status),
            "ingested_per_day": [item.to_dict() for item in self.ingested_per_day],
            "deleted_per_day": [item.to_dict() for item in self.deleted_per_day],
            "reappearances_per_day": [item.to_dict() for item in self.reappearances_per_day],
            "window": dict(self.window),
        }


@dataclass(frozen=True)
class DryRunAuditCandidate:
    """Best-effort candidate for historical dry-run side-effect analysis."""

    started_at: str
    ended_at: str
    inferred_run_id: str | None
    inferred_folder_path: str | None
    estimated_ledger_rows_touched: int
    confidence: str
    signals: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "inferred_run_id": self.inferred_run_id,
            "inferred_folder_path": self.inferred_folder_path,
            "estimated_ledger_rows_touched": self.estimated_ledger_rows_touched,
            "confidence": self.confidence,
            "signals": list(self.signals),
        }


@dataclass(frozen=True)
class DryRunSideEffectAudit:
    """Report-only payload for heuristic historical dry-run side effects."""

    coverage: str
    method: str
    window: dict[str, str | None]
    candidates: tuple[DryRunAuditCandidate, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "coverage": self.coverage,
            "method": self.method,
            "window": dict(self.window),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class LedgerHashAuditResult:
    """Read-only ledger hash audit payload for API and GUI health checks."""

    total_files: int
    missing_hash: int
    hash_mismatches: int
    deleted_rows_skipped: int
    sample_missing_hash_paths: tuple[str, ...]
    sample_mismatch_paths: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "total_files": self.total_files,
            "missing_hash": self.missing_hash,
            "hash_mismatches": self.hash_mismatches,
            "deleted_rows_skipped": self.deleted_rows_skipped,
            "sample_missing_hash_paths": list(self.sample_missing_hash_paths),
            "sample_mismatch_paths": list(self.sample_mismatch_paths),
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
        self._discovery_query = DiscoveryQueryService(session_factory)

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

    def get_run_history(
        self,
        limit: int = 50,
        *,
        operation_type: str | None = None,
        status: str | None = None,
    ) -> list[RunHistoryItem]:
        """Return unified operation run history rows."""
        bounded_limit = max(1, int(limit))
        with self._session_factory() as session:
            stmt = select(OperationRun).order_by(OperationRun.started_at.desc(), OperationRun.id.desc()).limit(bounded_limit)
            if operation_type is not None:
                stmt = stmt.where(OperationRun.operation_type == OperationRunType(operation_type.strip().upper()))
            if status is not None:
                stmt = stmt.where(OperationRun.status == OperationRunStatus(status.strip().upper()))
            rows = session.scalars(stmt).all()
        items: list[InternalRunHistoryItem] = []
        for row in rows:
            duration_ms: float | None = None
            if row.completed_at is not None:
                duration_ms = (row.completed_at - row.started_at).total_seconds() * 1000.0
            items.append(
                RunHistoryItem(
                    operation_run_id=str(row.id),
                    operation_type=row.operation_type.value,
                    status=row.status.value,
                    started_at=row.started_at.isoformat(),
                    completed_at=row.completed_at.isoformat() if row.completed_at is not None else None,
                    duration_ms=duration_ms,
                    linked_run_id=str(row.linked_run_id) if row.linked_run_id is not None else None,
                    context=dict(row.context or {}),
                    error_message=row.error_message,
                )
            )
        return items

    def get_internal_run_history(self, limit: int = 50) -> list[InternalRunHistoryItem]:
        """Return legacy planner/apply run history rows with derived counts and status."""
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
                InternalRunHistoryItem(
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

    def get_canonical_gallery(
        self,
        page: int = 1,
        limit: int = 30,
        *,
        tags: tuple[str, ...] = (),
        sort_by: str = "created_at",
        sort_order: str | None = None,
        file_type: str | None = None,
        source: TagSource | None = None,
        min_confidence: float | None = None,
    ) -> CanonicalGalleryPage:
        """Return deterministic paginated canonical gallery media items."""
        normalized_sort_order = sort_order
        if normalized_sort_order is None:
            normalized_sort_order = "asc" if sort_by == "tag_name" else "desc"
        query = DiscoveryQueryParams(
            page=page,
            limit=limit,
            tags=tags,
            sort_by=sort_by,  # type: ignore[arg-type]
            sort_order=normalized_sort_order,  # type: ignore[arg-type]
            file_type=file_type if file_type in {"image", "video"} else None,
            source=source,
            min_confidence=min_confidence,
        )
        page_rows = self._discovery_query.query(query)
        items = tuple(
            CanonicalGalleryItem(
                id=item.id,
                filename=item.filename,
                file_type=item.file_type,
                media_url=item.media_url,
                poster_url=self._poster_url_for_gallery_item(item.id, item.file_type),
                matched_tags=item.matched_tags,
                top_confidence_score=item.top_confidence_score,
                sort_tag_name=item.sort_tag_name,
            )
            for item in page_rows.items
        )
        return CanonicalGalleryPage(
            total_count=page_rows.total_count,
            page=page_rows.page,
            limit=page_rows.limit,
            total_pages=page_rows.total_pages,
            items=items,
        )

    def get_tag_suggestions(self, q: str | None = None, limit: int = 10) -> tuple[str, ...]:
        """Return deterministic normalized tag suggestions for discover autocomplete."""
        bounded_limit = min(50, max(1, int(limit)))
        normalized_query = (q or "").strip().lower()
        with self._session_factory() as session:
            stmt = select(Tag.normalized_name)
            if normalized_query:
                contains = f"%{normalized_query}%"
                prefix = f"{normalized_query}%"
                normalized_name = func.lower(Tag.normalized_name)
                stmt = stmt.where(normalized_name.like(contains)).order_by(
                    case((normalized_name.like(prefix), 0), else_=1),
                    Tag.normalized_name.asc(),
                )
            else:
                stmt = stmt.order_by(Tag.normalized_name.asc())
            stmt = stmt.limit(bounded_limit)
            return tuple(session.scalars(stmt).all())

    def get_media_file_by_hash_page(self, *, hash_prefix: str, page: int = 1, limit: int = 30) -> MediaFileLedgerPage:
        """Return paginated ledger rows by exact SHA-256 hash or literal prefix."""
        with self._session_factory() as session:
            rows = get_rows_by_hash(session, hash_prefix)
        return self._paginate_media_file_rows(rows, page=page, limit=limit)

    def get_media_file_history_page(self, *, path: str, page: int = 1, limit: int = 30) -> MediaFileLedgerPage:
        """Return paginated ledger history rows for current/discovered path matches."""
        with self._session_factory() as session:
            rows = get_history_by_path(session, path)
        return self._paginate_media_file_rows(rows, page=page, limit=limit)

    def get_media_file_by_status_page(
        self,
        *,
        status: MediaFileStatus,
        page: int = 1,
        limit: int = 30,
    ) -> MediaFileLedgerPage:
        """Return paginated ledger rows for a Phase 13 lifecycle status."""
        with self._session_factory() as session:
            rows = get_rows_by_status(session, status)
        return self._paginate_media_file_rows(rows, page=page, limit=limit)

    def get_media_file_reappearances_page(self, *, path: str, page: int = 1, limit: int = 30) -> MediaFileLedgerPage:
        """Return rows discovered after the latest deleted tombstone for the path."""
        with self._session_factory() as session:
            rows = get_reappearances_after_deleted(session, path)
        return self._paginate_media_file_rows(rows, page=page, limit=limit)

    def get_media_file_analytics(self) -> MediaFileLedgerAnalytics:
        """Return all-time ledger analytics for GUI reporting cards and trends."""
        with self._session_factory() as session:
            totals = {
                "files_tracked": int(session.scalar(select(func.count()).select_from(MediaFile)) or 0),
                "duplicate_hash_groups": int(self._duplicate_hash_group_count(session)),
            }
            by_status = self._status_distribution(session)
            ingested_per_day = self._ingested_per_day_series(session)
            deleted_per_day = self._deleted_per_day_series(session)
            reappearances_per_day = self._reappearances_per_day_series(session)

        return MediaFileLedgerAnalytics(
            totals=totals,
            by_status=by_status,
            ingested_per_day=ingested_per_day,
            deleted_per_day=deleted_per_day,
            reappearances_per_day=reappearances_per_day,
            window={"mode": "all_time"},
        )

    def get_dry_run_side_effect_audit(
        self,
        *,
        start: str | None = None,
        end: str | None = None,
        limit: int = 50,
    ) -> DryRunSideEffectAudit:
        """
        Return heuristic candidates for historical dry-run side effects.

        Exact retrospective attribution is not possible with current schema
        because historical dry_run intent is not durably stored on runs.
        """
        start_at = self._parse_optional_iso(start)
        end_at = self._parse_optional_iso(end)
        bounded_limit = min(200, max(1, int(limit)))
        if start_at is not None and end_at is not None and start_at > end_at:
            raise ValueError("start must be <= end.")

        with self._session_factory() as session:
            run_stmt = (
                select(Run)
                .order_by(Run.created_at.desc(), Run.id.desc())
                .limit(bounded_limit * 5)
            )
            if start_at is not None:
                run_stmt = run_stmt.where(Run.created_at >= start_at)
            if end_at is not None:
                run_stmt = run_stmt.where(Run.created_at <= end_at)
            runs = session.scalars(run_stmt).all()
            if not runs:
                return DryRunSideEffectAudit(
                    coverage="BEST_EFFORT",
                    method="Heuristic correlation over run timestamps and recompute/apply evidence.",
                    window={"start": start, "end": end},
                    candidates=(),
                    limitations=self._dry_run_audit_limitations(),
                )

            run_ids = [run.id for run in runs]
            apply_run_ids = set(
                session.scalars(select(ApplyAuditRun.run_id).where(ApplyAuditRun.run_id.in_(run_ids))).all()
            )
            recompute_rows = session.execute(
                select(CanonicalRecomputeRun)
                .where(CanonicalRecomputeRun.mode == "DRY_RUN")
                .order_by(CanonicalRecomputeRun.started_at.asc())
            ).scalars().all()

            candidates: list[DryRunAuditCandidate] = []
            for run in runs:
                if run.id in apply_run_ids:
                    continue
                window_start = run.created_at
                window_end = run.updated_at if run.updated_at >= run.created_at else run.created_at
                matched_recompute = [
                    row
                    for row in recompute_rows
                    if row.started_at >= (window_start - timedelta(minutes=5))
                    and row.started_at <= (window_end + timedelta(minutes=5))
                ]
                if not matched_recompute:
                    continue

                touched = int(
                    session.scalar(
                        select(func.count())
                        .select_from(MediaFile)
                        .where(
                            MediaFile.ingested_at.is_not(None),
                            MediaFile.ingested_at >= window_start,
                            MediaFile.ingested_at <= (window_end + timedelta(minutes=5)),
                        )
                    )
                    or 0
                )
                signals = [
                    "run_without_apply_audit",
                    "nearby_canonical_recompute_dry_run",
                ]
                confidence = "LOW"
                if touched > 0:
                    signals.append("ledger_ingested_at_activity_in_window")
                    confidence = "MEDIUM"
                candidates.append(
                    DryRunAuditCandidate(
                        started_at=window_start.isoformat(),
                        ended_at=window_end.isoformat(),
                        inferred_run_id=str(run.id),
                        inferred_folder_path=None,
                        estimated_ledger_rows_touched=touched,
                        confidence=confidence,
                        signals=tuple(signals),
                    )
                )
                if len(candidates) >= bounded_limit:
                    break

        return DryRunSideEffectAudit(
            coverage="BEST_EFFORT",
            method="Heuristic correlation over run timestamps and recompute/apply evidence.",
            window={"start": start, "end": end},
            candidates=tuple(candidates),
            limitations=self._dry_run_audit_limitations(),
        )

    def get_ledger_hash_audit(
        self,
        *,
        root_path: str | None = None,
        sample_limit: int = 20,
    ) -> LedgerHashAuditResult:
        """Audit media_file hash completeness and drift without mutating ledger rows."""
        normalized_root: str | None = None
        if root_path is not None:
            normalized_root = root_path.strip()
            if not normalized_root:
                raise ValueError("root_path must not be empty when provided.")
            normalized_root = normalized_root.rstrip("/")
        bounded_sample_limit = min(200, max(1, int(sample_limit)))

        missing_samples: list[str] = []
        mismatch_samples: list[str] = []
        missing_hash = 0
        hash_mismatches = 0
        total_files = 0
        deleted_rows_skipped = 0

        with self._session_factory() as session:
            path_key = func.coalesce(MediaFile.current_path, MediaFile.discovered_path).label("path_key")
            stmt = select(MediaFile.status, MediaFile.hash_sha256, path_key)
            if normalized_root is not None:
                stmt = stmt.where(or_(path_key == normalized_root, path_key.like(f"{normalized_root}/%")))
            stmt = stmt.order_by(path_key.asc())
            rows = session.execute(stmt).all()

        for status, stored_hash, scoped_path in rows:
            path_value = str(scoped_path) if scoped_path is not None else ""
            if status == MediaFileStatus.DELETED.value:
                deleted_rows_skipped += 1
                continue
            total_files += 1
            if not stored_hash:
                missing_hash += 1
                if len(missing_samples) < bounded_sample_limit:
                    missing_samples.append(path_value)
                continue

            resolved_path = self._resolve_existing_instance_path(path_value)
            if resolved_path is None:
                logger.warning(
                    "Ledger hash audit skipped unreadable path",
                    extra={
                        "phase": "ledger_audit",
                        "action": "HASH_AUDIT_PATH_UNREADABLE",
                        "filename": path_value,
                        "files_count": 1,
                    },
                )
                continue
            try:
                computed_hash = sha256_file(resolved_path)
            except OSError:
                logger.warning(
                    "Ledger hash audit skipped path due to filesystem read error",
                    extra={
                        "phase": "ledger_audit",
                        "action": "HASH_AUDIT_PATH_READ_ERROR",
                        "filename": path_value,
                        "files_count": 1,
                    },
                )
                continue
            if str(stored_hash).lower() != computed_hash:
                hash_mismatches += 1
                if len(mismatch_samples) < bounded_sample_limit:
                    mismatch_samples.append(path_value)

        logger.info(
            "Ledger hash audit completed",
            extra={
                "phase": "ledger_audit",
                "action": "HASH_AUDIT",
                "files_count": total_files,
                "codes_extracted": (
                    f"missing_hash={missing_hash},hash_mismatches={hash_mismatches},"
                    f"deleted_rows_skipped={deleted_rows_skipped},root_path={normalized_root or 'ALL'}"
                ),
            },
        )
        return LedgerHashAuditResult(
            total_files=total_files,
            missing_hash=missing_hash,
            hash_mismatches=hash_mismatches,
            deleted_rows_skipped=deleted_rows_skipped,
            sample_missing_hash_paths=tuple(missing_samples),
            sample_mismatch_paths=tuple(mismatch_samples),
        )

    def resolve_thumbnail_source(self, file_instance_id: UUID) -> tuple[Path, str] | None:
        """Resolve an active image file path and media type for thumbnail streaming."""
        path = self._resolve_active_instance_path(file_instance_id)
        if path is None:
            return None
        if infer_media_type_from_extension(path) != "IMG":
            return None
        mime, _ = mimetypes.guess_type(path.name)
        return path, (mime or "image/jpeg")

    def resolve_video_thumbnail_source(self, file_instance_id: UUID) -> tuple[Path, str] | None:
        """Resolve or generate a cached video thumbnail for an active video instance."""
        if not _video_thumbnails_enabled():
            return None

        path = self._resolve_active_instance_path(file_instance_id)
        if path is None:
            return None
        if self._path_to_gallery_file_type(path) != "video":
            return None

        thumbnail_path = self._resolve_or_generate_video_thumbnail(path, file_instance_id)
        if thumbnail_path is None:
            return None
        return thumbnail_path, "image/jpeg"

    def resolve_media_source(self, file_instance_id: UUID) -> tuple[Path, str] | None:
        """Resolve an active canonical media path and MIME type for secure streaming."""
        path = self._resolve_active_instance_path(file_instance_id)
        if path is None:
            return None
        if self._path_to_gallery_file_type(path) is None:
            return None
        mime, _ = mimetypes.guess_type(path.name)
        return path, (mime or "application/octet-stream")

    def get_canonical_gallery_detail(self, file_instance_id: UUID) -> CanonicalGalleryDetail | None:
        """Return canonical media detail when `file_instance_id` is an active canonical row."""
        with self._session_factory() as session:
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
                .subquery()
            )
            row = session.execute(
                select(
                    FileInstance.file_instance_id,
                    FileInstance.absolute_path,
                )
                .join(
                    latest_assignments,
                    FileInstance.file_instance_id == latest_assignments.c.canonical_instance_id,
                )
                .where(
                    latest_assignments.c.rn == 1,
                    FileInstance.status == FileInstanceStatus.ACTIVE.value,
                    FileInstance.file_instance_id == file_instance_id,
                )
            ).first()
            if row is None:
                return None
            canonical_instance_id, absolute_path = row

        path = Path(absolute_path)
        file_type = self._path_to_gallery_file_type(path)
        if file_type is None:
            return None

        return CanonicalGalleryDetail(
            id=str(canonical_instance_id),
            filename=path.name,
            file_type=file_type,
            media_url=f"/media/{canonical_instance_id}",
            absolute_path=absolute_path,
        )

    def _poster_url_for_gallery_item(self, file_id: str, file_type: str) -> str | None:
        if file_type != "video" or not _video_thumbnails_enabled():
            return None
        return f"/api/video-thumbnail/{file_id}"

    def _resolve_active_instance_path(self, file_instance_id: UUID) -> Path | None:
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
        try:
            with path.open("rb"):
                pass
        except OSError:
            return None
        return path

    def _resolve_or_generate_video_thumbnail(self, source_path: Path, file_instance_id: UUID) -> Path | None:
        cache_dir = self._ensure_video_thumbnail_cache_dir()
        if cache_dir is None:
            return None

        try:
            source_stat = source_path.stat()
        except OSError:
            return None

        cache_key = self._video_thumbnail_cache_key(file_instance_id, source_path, source_stat)
        cached_path = cache_dir / f"{cache_key}.jpg"
        if cached_path.exists() and cached_path.is_file():
            return cached_path

        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            logger.info(
                "Video thumbnail unavailable because ffmpeg is not installed",
                extra={"file_instance_id": str(file_instance_id), "path": str(source_path)},
            )
            return None

        temp_path = cached_path.with_suffix(".tmp.jpg")
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass

        for offset in ("1", "0"):
            if self._run_ffmpeg_thumbnail(ffmpeg_path, source_path, temp_path, offset):
                try:
                    temp_path.replace(cached_path)
                except OSError:
                    logger.warning(
                        "Video thumbnail generation succeeded but cache write failed",
                        extra={"file_instance_id": str(file_instance_id), "cache_path": str(cached_path)},
                    )
                    return None
                return cached_path

        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return None

    def _ensure_video_thumbnail_cache_dir(self) -> Path | None:
        cache_dir = _video_thumbnail_cache_dir()
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.warning("Video thumbnail cache directory is unavailable", extra={"cache_dir": str(cache_dir)})
            return None
        return cache_dir

    def _video_thumbnail_cache_key(self, file_instance_id: UUID, source_path: Path, source_stat: os.stat_result) -> str:
        raw_key = "|".join(
            (
                str(file_instance_id),
                str(source_path),
                str(source_stat.st_mtime_ns),
                str(source_stat.st_size),
            )
        )
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def _run_ffmpeg_thumbnail(
        self,
        ffmpeg_path: str,
        source_path: Path,
        target_path: Path,
        offset_seconds: str,
    ) -> bool:
        command = [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            offset_seconds,
            "-i",
            str(source_path),
            "-frames:v",
            "1",
            "-vf",
            "scale=640:-1",
            str(target_path),
        ]
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True)
        except OSError:
            logger.warning(
                "Video thumbnail generation failed to start",
                extra={"source_path": str(source_path), "offset_seconds": offset_seconds},
            )
            return False
        if completed.returncode != 0:
            logger.info(
                "Video thumbnail frame extraction failed",
                extra={
                    "source_path": str(source_path),
                    "offset_seconds": offset_seconds,
                    "stderr": (completed.stderr or "").strip(),
                },
            )
            return False
        return target_path.exists() and target_path.is_file()

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

    def _path_to_gallery_file_type(self, path: Path) -> str | None:
        """Return canonical gallery file type for supported media extensions."""
        media_type = infer_media_type_from_extension(path)
        if media_type == "IMG":
            return "image"
        if media_type == "VID":
            return "video"
        return None

    def _parse_optional_iso(self, value: str | None) -> datetime | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed

    def _dry_run_audit_limitations(self) -> tuple[str, ...]:
        return (
            "Historical run rows do not persist a dry_run flag, so audit candidates are inferred heuristically.",
            "Folder path is not durably stored on runs, so inferred_folder_path is null for historical rows.",
            "Estimated ledger activity uses ingested_at window correlation and is not a guaranteed causal mapping.",
        )

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
        value = session.scalar(select(func.count()).select_from(OperationRun))
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

    def _status_distribution(self, session: Session) -> dict[str, int]:
        rows = session.execute(
            select(MediaFile.status, func.count(MediaFile.id))
            .group_by(MediaFile.status)
        ).all()
        distribution = {
            MediaFileStatus.INGESTED.value: 0,
            MediaFileStatus.PROCESSED.value: 0,
            MediaFileStatus.DELETED.value: 0,
        }
        for status, count in rows:
            distribution[str(status)] = int(count)
        return distribution

    def _duplicate_hash_group_count(self, session: Session) -> int:
        path_key = func.coalesce(MediaFile.current_path, MediaFile.discovered_path)
        duplicate_groups = (
            select(MediaFile.hash_sha256)
            .where(MediaFile.hash_sha256.is_not(None))
            .group_by(MediaFile.hash_sha256)
            .having(func.count(func.distinct(path_key)) > 1)
            .subquery()
        )
        return int(session.scalar(select(func.count()).select_from(duplicate_groups)) or 0)

    def _ingested_per_day_series(self, session: Session) -> tuple[LedgerDayCount, ...]:
        day_expr = func.date(MediaFile.discovered_at)
        rows = session.execute(
            select(day_expr.label("day"), func.count(MediaFile.id).label("count"))
            .where(MediaFile.status.in_([MediaFileStatus.INGESTED.value, MediaFileStatus.PROCESSED.value]))
            .group_by(day_expr)
            .order_by(day_expr.asc())
        ).all()
        return self._rows_to_day_series(rows)

    def _deleted_per_day_series(self, session: Session) -> tuple[LedgerDayCount, ...]:
        day_expr = func.date(MediaFile.deleted_at)
        rows = session.execute(
            select(day_expr.label("day"), func.count(MediaFile.id).label("count"))
            .where(
                MediaFile.status == MediaFileStatus.DELETED.value,
                MediaFile.deleted_at.is_not(None),
            )
            .group_by(day_expr)
            .order_by(day_expr.asc())
        ).all()
        return self._rows_to_day_series(rows)

    def _reappearances_per_day_series(self, session: Session) -> tuple[LedgerDayCount, ...]:
        current = aliased(MediaFile)
        prior = aliased(MediaFile)
        day_expr = func.date(current.discovered_at)
        # Reappearance is path-history based in the ledger. We match across both
        # current_path and discovered_path to catch renamed rows that still carry
        # the original discovered path after a prior DELETED tombstone.
        path_matches = or_(
            and_(current.current_path.is_not(None), prior.current_path == current.current_path),
            and_(current.current_path.is_not(None), prior.discovered_path == current.current_path),
            and_(current.discovered_path.is_not(None), prior.current_path == current.discovered_path),
            and_(current.discovered_path.is_not(None), prior.discovered_path == current.discovered_path),
        )
        rows = session.execute(
            select(day_expr.label("day"), func.count(current.id).label("count"))
            .where(
                current.status != MediaFileStatus.DELETED.value,
                select(prior.id)
                .where(
                    prior.status == MediaFileStatus.DELETED.value,
                    prior.deleted_at.is_not(None),
                    prior.deleted_at < current.discovered_at,
                    path_matches,
                )
                .exists(),
            )
            .group_by(day_expr)
            .order_by(day_expr.asc())
        ).all()
        return self._rows_to_day_series(rows)

    def _rows_to_day_series(self, rows: list[tuple[object, int]]) -> tuple[LedgerDayCount, ...]:
        output: list[LedgerDayCount] = []
        for day_value, count in rows:
            if day_value is None:
                continue
            output.append(LedgerDayCount(day=str(day_value), count=int(count)))
        return tuple(output)

    def _paginate_media_file_rows(self, rows: list[MediaFile], *, page: int, limit: int) -> MediaFileLedgerPage:
        bounded_page = max(1, int(page))
        bounded_limit = min(100, max(1, int(limit)))
        total_count = len(rows)
        total_pages = (total_count + bounded_limit - 1) // bounded_limit if total_count > 0 else 0
        offset = (bounded_page - 1) * bounded_limit
        paged_rows = rows[offset: offset + bounded_limit]
        items = tuple(self._to_media_file_ledger_item(row) for row in paged_rows)
        return MediaFileLedgerPage(
            total_count=total_count,
            page=bounded_page,
            limit=bounded_limit,
            total_pages=total_pages,
            items=items,
        )

    def _to_media_file_ledger_item(self, row: MediaFile) -> MediaFileLedgerItem:
        return MediaFileLedgerItem(
            id=str(row.id),
            current_path=row.current_path,
            discovered_path=row.discovered_path,
            size_bytes=row.size_bytes,
            hash_sha256=row.hash_sha256,
            status=row.status,
            discovered_at=row.discovered_at.isoformat(),
            ingested_at=row.ingested_at.isoformat() if row.ingested_at is not None else None,
            deleted_at=row.deleted_at.isoformat() if row.deleted_at is not None else None,
        )

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
