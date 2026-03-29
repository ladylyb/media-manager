"""Read/query facade for API controllers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import os
from typing import Any

from sqlalchemy import func, select

from media_manager.app.persistence.models import (
    CanonicalTag,
    FailureEvent,
    MediaFileStatus,
    OperationRun,
    OperationRunStatus,
    OperationRunType,
    Tag,
    TagSource,
)
from media_manager.app.persistence.operator_console import OperatorConsoleReadService
from media_manager.app.service_layer.cache import ServiceCache
from media_manager.app.service_layer.versioning import compute_phase_metadata


@dataclass
class ReadServices:
    """Shared read/query service entrypoint with short-lived caching."""

    session_factory: object
    cache: ServiceCache

    def __post_init__(self) -> None:
        self._read_service = OperatorConsoleReadService(self.session_factory)

    def status(self) -> dict[str, object]:
        cached = self.cache.get("status")
        if isinstance(cached, dict):
            return dict(cached)
        summary = self._read_service.get_dashboard_summary().to_dict()
        phase = compute_phase_metadata(self.session_factory)
        payload = {
            **phase.to_dict(),
            "available_features": [
                "run",
                "policy",
                "tag_enrichment",
                "dashboard_summary",
                "runs",
                "operation_runs",
                "internal_runs",
                "home",
                "latest_metrics",
                "canonical",
                "duplicates",
                "integrity",
                "ledger",
                "admin_observability",
                "admin_benchmarks",
            ],
            "phase_status": [
                {
                    "phase": phase.active_phase,
                    "status": "ACTIVE",
                    "last_run_id": None,
                    "updated_at": None,
                    "details": {"dashboard_summary": summary},
                }
            ],
        }
        self.cache.set("status", payload, ttl_s=5)
        return dict(payload)

    def home(self) -> dict[str, object]:
        cache_key = "home"
        cached = self.cache.get(cache_key)
        if isinstance(cached, dict):
            return dict(cached)

        summary = self._read_service.get_dashboard_summary().to_dict()
        latest_metrics = self._read_service.get_latest_metrics().to_dict()
        phase = compute_phase_metadata(self.session_factory)
        recent_images_page = self._read_service.get_canonical_gallery(
            page=1,
            limit=4,
            sort_by="created_at",
            file_type="image",
        )
        recent_videos_page = self._read_service.get_canonical_gallery(
            page=1,
            limit=4,
            sort_by="created_at",
            file_type="video",
        )
        recent_activity = [item.to_dict() for item in self._read_service.get_run_history(limit=4)]

        with self.session_factory() as session:
            failed_runs = int(
                session.scalar(
                    select(func.count()).select_from(OperationRun).where(OperationRun.status == OperationRunStatus.FAILED)
                )
                or 0
            )
            active_runs = int(
                session.scalar(
                    select(func.count()).select_from(OperationRun).where(OperationRun.status == OperationRunStatus.STARTED)
                )
                or 0
            )
            tagged_canonical_assets = int(
                session.scalar(select(func.count(func.distinct(CanonicalTag.canonical_id))).select_from(CanonicalTag))
                or 0
            )

            tag_asset_count = func.count(func.distinct(CanonicalTag.canonical_id))
            top_tag_rows = session.execute(
                select(
                    Tag.name,
                    tag_asset_count.label("asset_count"),
                )
                .join(CanonicalTag, CanonicalTag.tag_id == Tag.id)
                .group_by(Tag.id, Tag.name)
                .order_by(tag_asset_count.desc(), Tag.name.asc())
                .limit(6)
            ).all()

        canonical_assets = int(summary.get("canonical_files", 0) or 0)
        untagged_assets = max(canonical_assets - tagged_canonical_assets, 0)
        last_run_status = recent_activity[0]["status"] if recent_activity else "UNKNOWN"
        last_run_type = recent_activity[0]["operation_type"] if recent_activity else None

        payload = {
            "library_summary": {
                "total_assets": int(summary.get("total_files", 0) or 0),
                "images": int(summary.get("total_images", 0) or 0),
                "videos": int(summary.get("total_videos", 0) or 0),
                "duplicate_groups": int(summary.get("duplicate_groups", 0) or 0),
                "canonical_assets": canonical_assets,
                "recent_import_count": len(recent_activity),
            },
            "recent_media": [
                *[item.to_dict() for item in recent_images_page.items],
                *[item.to_dict() for item in recent_videos_page.items],
            ],
            "recent_images": [item.to_dict() for item in recent_images_page.items],
            "recent_videos": [item.to_dict() for item in recent_videos_page.items],
            "attention_summary": {
                "duplicate_groups": int(summary.get("duplicate_groups", 0) or 0),
                "failed_runs": failed_runs,
                "active_runs": active_runs,
                "untagged_assets": untagged_assets,
                "unresolved_items": failed_runs + active_runs + untagged_assets,
            },
            "recent_activity": recent_activity,
            "collections": [
                {
                    "label": str(name),
                    "kind": "tag",
                    "asset_count": int(asset_count or 0),
                }
                for name, asset_count in top_tag_rows
            ],
            "status_strip": {
                "workflow_label": "Guided workflow available",
                "active_phase": phase.active_phase,
                "last_run_status": last_run_status,
                "last_run_type": last_run_type,
                "regression_status": str(latest_metrics.get("last_regression_status", "UNKNOWN") or "UNKNOWN"),
            },
            "guided_entry": {
                "label": "Open Organize",
                "route": "/pipeline-wizard",
                "helper": "Guided ingest, planning, apply, and review",
            },
        }
        self.cache.set(cache_key, payload, ttl_s=5)
        return payload

    def dashboard_summary(self) -> dict[str, object]:
        cached = self.cache.get("dashboard_summary")
        if isinstance(cached, dict):
            return dict(cached)
        payload = self._read_service.get_dashboard_summary().to_dict()
        self.cache.set("dashboard_summary", payload, ttl_s=2)
        return payload

    def latest_metrics(self) -> dict[str, object]:
        cached = self.cache.get("latest_metrics")
        if isinstance(cached, dict):
            return dict(cached)
        payload = self._read_service.get_latest_metrics().to_dict()
        self.cache.set("latest_metrics", payload, ttl_s=2)
        return payload

    def runs(
        self,
        *,
        limit: int,
        operation_type: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, object]]:
        return [
            item.to_dict()
            for item in self._read_service.get_run_history(
                limit=limit,
                operation_type=operation_type,
                status=status,
            )
        ]

    def operation_runs(
        self,
        *,
        limit: int,
        operation_type: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, object]]:
        return self.runs(limit=limit, operation_type=operation_type, status=status)

    def internal_runs(self, *, limit: int) -> list[dict[str, object]]:
        return [item.to_dict() for item in self._read_service.get_internal_run_history(limit=limit)]

    def duplicates(self) -> dict[str, object]:
        return {"groups": [group.to_dict() for group in self._read_service.get_duplicate_groups()]}

    def integrity_dashboard(self) -> dict[str, object]:
        return self._read_service.get_integrity_dashboard_summary().to_dict()

    def integrity_issues(
        self,
        *,
        status: str | None,
        min_confidence: float | None,
        page: int,
        limit: int,
    ) -> dict[str, object]:
        return self._read_service.get_integrity_issue_page(
            status=status,
            min_confidence=min_confidence,
            page=page,
            limit=limit,
        ).to_dict()

    def integrity_file_detail(self, *, check_id: str) -> dict[str, object] | None:
        from uuid import UUID

        detail = self._read_service.get_integrity_file_detail(UUID(check_id))
        return None if detail is None else detail.to_dict()

    def integrity_quarantine_items(self, *, page: int, limit: int) -> dict[str, object]:
        return self._read_service.get_integrity_quarantine_page(page=page, limit=limit).to_dict()

    def duplicate_bin_items(self, *, page: int, limit: int) -> dict[str, object]:
        """Bin-centered read entrypoint over the reclaim-backed archive page compatibility model."""
        return self._read_service.get_duplicate_reclaim_archive_page(page=page, limit=limit).to_dict()

    def duplicate_reclaim_items(self, *, page: int, limit: int) -> dict[str, object]:
        """Compatibility wrapper: service naming is bin-centered, but read payloads remain reclaim-based for now."""
        return self.duplicate_bin_items(page=page, limit=limit)

    def retention_recycle_items(self, *, page: int, limit: int) -> dict[str, object]:
        return self._read_service.get_retention_recycle_page(page=page, limit=limit).to_dict()

    def canonical(
        self,
        *,
        page: int,
        limit: int,
        tags: tuple[str, ...],
        sort_by: str,
        sort_order: str | None,
        source: str | None,
        min_confidence: float | None,
    ) -> dict[str, object]:
        source_value = TagSource(source.strip().lower()) if source else None
        return self._read_service.get_canonical_gallery(
            page=page,
            limit=limit,
            tags=tags,
            sort_by=sort_by,
            sort_order=sort_order,
            source=source_value,
            min_confidence=min_confidence,
        ).to_dict()

    def canonical_tags(self, *, q: str | None, limit: int) -> dict[str, object]:
        return {"items": list(self._read_service.get_tag_suggestions(q=q, limit=limit))}

    def media_file_by_hash(self, *, hash_prefix: str, page: int, limit: int) -> dict[str, object]:
        return self._read_service.get_media_file_by_hash_page(hash_prefix=hash_prefix, page=page, limit=limit).to_dict()

    def media_file_history(self, *, path: str, page: int, limit: int) -> dict[str, object]:
        return self._read_service.get_media_file_history_page(path=path, page=page, limit=limit).to_dict()

    def media_file_by_status(self, *, status: str, page: int, limit: int) -> dict[str, object]:
        status_value = MediaFileStatus(status.strip().upper())
        return self._read_service.get_media_file_by_status_page(status=status_value, page=page, limit=limit).to_dict()

    def media_file_reappearances(self, *, path: str, page: int, limit: int) -> dict[str, object]:
        return self._read_service.get_media_file_reappearances_page(path=path, page=page, limit=limit).to_dict()

    def media_file_analytics(self) -> dict[str, object]:
        return self._read_service.get_media_file_analytics().to_dict()

    def ledger_hash_audit(self, *, root_path: str | None, sample_limit: int) -> dict[str, object]:
        return self._read_service.get_ledger_hash_audit(root_path=root_path, sample_limit=sample_limit).to_dict()

    def media_file_dry_run_audit(self, *, start: str | None, end: str | None, limit: int) -> dict[str, object]:
        return self._read_service.get_dry_run_side_effect_audit(start=start, end=end, limit=limit).to_dict()

    def admin_observability_summary(self) -> dict[str, object]:
        cache_key = "admin_observability_summary"
        cached = self.cache.get(cache_key)
        if isinstance(cached, dict):
            return dict(cached)

        now = datetime.now(tz=UTC)
        window_start = now - timedelta(hours=24)
        metrics = self.latest_metrics()
        with self.session_factory() as session:
            recent_runs = session.scalars(
                select(OperationRun).where(OperationRun.started_at >= window_start).order_by(OperationRun.started_at.desc())
            ).all()
            recent_failures = int(
                session.scalar(select(func.count()).select_from(FailureEvent).where(FailureEvent.created_at >= window_start))
                or 0
            )

        runs_by_status: dict[str, int] = {}
        runs_by_type: dict[str, int] = {}
        last_success_by_type: dict[str, str | None] = {
            operation_type.value: None for operation_type in OperationRunType
        }
        completed_runs = sorted(
            (row for row in recent_runs if row.status == OperationRunStatus.COMPLETED),
            key=lambda row: row.completed_at or row.started_at,
            reverse=True,
        )
        for row in recent_runs:
            runs_by_status[row.status.value] = runs_by_status.get(row.status.value, 0) + 1
            runs_by_type[row.operation_type.value] = runs_by_type.get(row.operation_type.value, 0) + 1
        for row in completed_runs:
            if last_success_by_type[row.operation_type.value] is None:
                completed_at = row.completed_at or row.started_at
                last_success_by_type[row.operation_type.value] = completed_at.isoformat()

        payload = {
            "metrics_enabled": (os.getenv("MEDIA_MANAGER_METRICS_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}),
            "prometheus_url": (os.getenv("MEDIA_MANAGER_PROMETHEUS_URL", "") or "").strip() or None,
            "grafana_url": (os.getenv("MEDIA_MANAGER_GRAFANA_URL", "") or "").strip() or None,
            "generated_at": now.isoformat(),
            "window_hours": 24,
            "recent_failure_count": recent_failures,
            "recent_runs_by_status": runs_by_status,
            "recent_runs_by_type": runs_by_type,
            "last_success_by_type": last_success_by_type,
            "latest_metrics": metrics,
        }
        self.cache.set(cache_key, payload, ttl_s=5)
        return payload

    def admin_observability_failures(self, *, limit: int) -> dict[str, object]:
        bounded_limit = max(1, min(100, int(limit)))
        with self.session_factory() as session:
            failure_rows = session.scalars(
                select(FailureEvent).order_by(FailureEvent.created_at.desc(), FailureEvent.id.desc()).limit(bounded_limit)
            ).all()
            failed_runs = session.scalars(
                select(OperationRun)
                .where(OperationRun.status == OperationRunStatus.FAILED)
                .order_by(OperationRun.started_at.desc(), OperationRun.id.desc())
                .limit(bounded_limit)
            ).all()

        return {
            "failure_events": [
                {
                    "id": str(row.id),
                    "run_id": str(row.run_id),
                    "phase": row.phase.value,
                    "error_code": row.error_code,
                    "error_message": row.error_message,
                    "created_at": row.created_at.isoformat(),
                }
                for row in failure_rows
            ],
            "failed_operation_runs": [
                {
                    "operation_run_id": str(row.id),
                    "operation_type": row.operation_type.value,
                    "status": row.status.value,
                    "started_at": row.started_at.isoformat(),
                    "completed_at": row.completed_at.isoformat() if row.completed_at is not None else None,
                    "error_message": row.error_message,
                    "context": dict(row.context or {}),
                }
                for row in failed_runs
            ],
        }

    def admin_observability_metrics_series(self, *, hours: int) -> dict[str, object]:
        bounded_hours = max(1, min(168, int(hours)))
        now = datetime.now(tz=UTC)
        window_start = now - timedelta(hours=bounded_hours)
        with self.session_factory() as session:
            rows = session.scalars(
                select(OperationRun).where(OperationRun.started_at >= window_start).order_by(OperationRun.started_at.asc())
            ).all()

        buckets: dict[str, dict[str, Any]] = {}
        for row in rows:
            bucket = row.started_at.astimezone(UTC).replace(minute=0, second=0, microsecond=0).isoformat()
            entry = buckets.setdefault(
                bucket,
                {
                    "bucket_start": bucket,
                    "operation_count": 0,
                    "failure_count": 0,
                    "duration_ms_avg": 0.0,
                    "duration_ms_samples": [],
                },
            )
            entry["operation_count"] += 1
            if row.status == OperationRunStatus.FAILED:
                entry["failure_count"] += 1
            if row.completed_at is not None:
                entry["duration_ms_samples"].append((row.completed_at - row.started_at).total_seconds() * 1000.0)

        points: list[dict[str, object]] = []
        for bucket in sorted(buckets.keys()):
            entry = buckets[bucket]
            samples = entry.pop("duration_ms_samples")
            entry["duration_ms_avg"] = round(sum(samples) / len(samples), 3) if samples else 0.0
            points.append(entry)

        return {
            "series": {
                "operation_volume": [{"timestamp": point["bucket_start"], "value": point["operation_count"]} for point in points],
                "failure_volume": [{"timestamp": point["bucket_start"], "value": point["failure_count"]} for point in points],
                "latency_ms_avg": [{"timestamp": point["bucket_start"], "value": point["duration_ms_avg"]} for point in points],
            },
            "hours": bounded_hours,
        }
