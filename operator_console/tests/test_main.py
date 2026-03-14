"""Smoke tests for the Operator Console FastAPI application."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient

from media_manager.app.service_layer.errors import ServiceLayerException
import operator_console.main as main_module
from operator_console.main import (
    app,
    get_admin_services,
    get_operation_services,
    get_operator_console_service,
    get_read_services,
)

def test_canonical_api_route_inventory_and_v1_removal() -> None:
    route_paths = {route.path for route in app.routes}

    expected_canonical_paths = {
        "/api/status",
        "/api/dashboard-summary",
        "/api/latest-metrics",
        "/api/runs",
        "/api/operation-runs",
        "/api/internal-runs",
        "/api/operations/catalog",
        "/api/policy",
        "/api/ingest",
        "/api/plan",
        "/api/apply",
        "/api/canonical/recompute",
        "/api/run",
        "/api/tag-enrichment",
        "/api/media-file/validate",
        "/api/admin/hash-audit",
        "/api/admin/db-reset",
    }

    assert expected_canonical_paths.issubset(route_paths)
    assert "/api/v1/ledger/hash-audit" not in route_paths
    assert not any(path.startswith("/api/v2") for path in route_paths)


class _FakeService:
    """Simple fake read service for endpoint dependency overrides."""

    def __init__(self) -> None:
        self.last_gallery_call: dict[str, Any] | None = None
        self.last_tag_suggestions_call: dict[str, Any] | None = None
        self.last_media_file_call: dict[str, Any] | None = None

    def get_dashboard_summary(self) -> "_FakePayload":
        return _FakePayload(
            {
                "total_files": 10,
                "total_images": 6,
                "total_videos": 4,
                "duplicate_groups": 2,
                "canonical_files": 8,
                "total_runs": 3,
            }
        )

    def get_latest_metrics(self) -> "_FakePayload":
        return _FakePayload(
            {
                "ingest_time_ms": 12.5,
                "plan_time_ms": 6.0,
                "apply_time_ms": 4.5,
                "db_time_ms": 9.2,
                "cache_hit_rate": 92.0,
                "last_regression_status": "PASS",
            }
        )

    def get_run_history(self, limit: int = 50) -> list["_FakePayload"]:
        _ = limit
        return [
            _FakePayload(
                {
                    "operation_run_id": "aaaaaaaa-1111-1111-1111-111111111111",
                    "operation_type": "INGEST",
                    "status": "COMPLETED",
                    "started_at": "2026-03-01T09:30:00+00:00",
                    "completed_at": "2026-03-01T09:31:00+00:00",
                    "duration_ms": 60000.0,
                    "linked_run_id": None,
                    "context": {"folder_path": "/dataset"},
                    "error_message": None,
                }
            )
        ]

    def get_internal_run_history(self, limit: int = 50) -> list["_FakePayload"]:
        _ = limit
        return [
            _FakePayload(
                {
                    "run_id": "11111111-1111-1111-1111-111111111111",
                    "timestamp": "2026-03-01T09:30:00+00:00",
                    "files_processed": 24,
                    "duplicates_found": 2,
                    "runtime_ms": 1250.4,
                    "regression_status": "PASS",
                }
            ),
            _FakePayload(
                {
                    "run_id": "22222222-2222-2222-2222-222222222222",
                    "timestamp": "2026-03-01T08:15:00+00:00",
                    "files_processed": 18,
                    "duplicates_found": 1,
                    "runtime_ms": 980.0,
                    "regression_status": "FAIL",
                }
            ),
        ]

    def get_duplicate_groups(self, limit: int | None = None) -> list["_FakePayload"]:
        _ = limit
        return [
            _FakePayload(
                {
                    "group_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "files": [
                        {
                            "file_instance_id": "aaaaaaaa-0000-0000-0000-000000000001",
                            "absolute_path": "/dataset/a.jpg",
                            "media_type": "IMG",
                            "is_image": True,
                            "thumbnail_url": "/api/thumbnail/aaaaaaaa-0000-0000-0000-000000000001",
                        },
                        {
                            "file_instance_id": "aaaaaaaa-0000-0000-0000-000000000002",
                            "absolute_path": "/dataset/b.jpg",
                            "media_type": "IMG",
                            "is_image": True,
                            "thumbnail_url": "/api/thumbnail/aaaaaaaa-0000-0000-0000-000000000002",
                        },
                    ],
                    "canonical_file": {
                        "file_instance_id": "aaaaaaaa-0000-0000-0000-000000000001",
                        "absolute_path": "/dataset/a.jpg",
                    },
                }
            )
        ]

    def get_canonical_gallery(
        self,
        page: int = 1,
        limit: int = 30,
        *,
        tags: tuple[str, ...] = (),
        sort_by: str = "created_at",
        sort_order: str = "desc",
        source=None,
        min_confidence: float | None = None,
    ) -> _FakePayload:
        self.last_gallery_call = {
            "page": page,
            "limit": limit,
            "tags": tags,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "source": source,
            "min_confidence": min_confidence,
        }
        _ = tags, sort_by, sort_order, source, min_confidence
        if page > 10:
            return _FakePayload(
                {
                    "total_count": 2,
                    "page": page,
                    "limit": 30,
                    "total_pages": 1,
                    "items": [],
                }
            )
        return _FakePayload(
            {
                "total_count": 2,
                "page": page,
                "limit": 30,
                "total_pages": 1,
                "items": [
                    {
                        "id": "33333333-0000-0000-0000-000000000001",
                        "filename": "canon-a.jpg",
                        "file_type": "image",
                        "media_url": "/media/33333333-0000-0000-0000-000000000001",
                        "matched_tags": ["city", "travel"],
                        "top_confidence_score": 0.92,
                        "sort_tag_name": "city",
                    },
                    {
                        "id": "33333333-0000-0000-0000-000000000002",
                        "filename": "canon-b.mov",
                        "file_type": "video",
                        "media_url": "/media/33333333-0000-0000-0000-000000000002",
                        "matched_tags": [],
                        "top_confidence_score": None,
                        "sort_tag_name": None,
                    },
                ],
            }
        )

    def get_tag_suggestions(self, q: str | None = None, limit: int = 10) -> tuple[str, ...]:
        self.last_tag_suggestions_call = {"q": q, "limit": limit}
        base = ("city", "city night", "travel", "wildlife")
        return tuple(base[: max(1, min(50, int(limit)))])

    def _ledger_payload(self, *, page: int, limit: int) -> _FakePayload:
        return _FakePayload(
            {
                "total_count": 1,
                "page": page,
                "limit": limit,
                "total_pages": 1,
                "items": [
                    {
                        "id": "55555555-0000-0000-0000-000000000001",
                        "current_path": "/ledger/a.jpg",
                        "discovered_path": "/ledger/a.jpg",
                        "size_bytes": 1024,
                        "hash_sha256": "a" * 64,
                        "status": "INGESTED",
                        "discovered_at": "2026-03-01T10:00:00+00:00",
                        "ingested_at": "2026-03-01T10:00:01+00:00",
                        "deleted_at": None,
                    }
                ],
            }
        )

    def get_media_file_by_hash_page(self, *, hash_prefix: str, page: int = 1, limit: int = 30) -> _FakePayload:
        self.last_media_file_call = {"mode": "hash", "hash_prefix": hash_prefix, "page": page, "limit": limit}
        return self._ledger_payload(page=page, limit=limit)

    def get_media_file_history_page(self, *, path: str, page: int = 1, limit: int = 30) -> _FakePayload:
        self.last_media_file_call = {"mode": "history", "path": path, "page": page, "limit": limit}
        return self._ledger_payload(page=page, limit=limit)

    def get_media_file_by_status_page(self, *, status, page: int = 1, limit: int = 30) -> _FakePayload:
        self.last_media_file_call = {"mode": "status", "status": getattr(status, "value", str(status)), "page": page, "limit": limit}
        return self._ledger_payload(page=page, limit=limit)

    def get_media_file_reappearances_page(self, *, path: str, page: int = 1, limit: int = 30) -> _FakePayload:
        self.last_media_file_call = {"mode": "reappearances", "path": path, "page": page, "limit": limit}
        return self._ledger_payload(page=page, limit=limit)

    def get_media_file_analytics(self) -> _FakePayload:
        return _FakePayload(
            {
                "totals": {"files_tracked": 11, "duplicate_hash_groups": 2},
                "by_status": {"INGESTED": 6, "PROCESSED": 3, "DELETED": 2},
                "ingested_per_day": [{"day": "2026-03-01", "count": 4}],
                "deleted_per_day": [{"day": "2026-03-01", "count": 1}],
                "reappearances_per_day": [{"day": "2026-03-02", "count": 2}],
                "window": {"mode": "all_time"},
            }
        )

    def get_dry_run_side_effect_audit(
        self,
        *,
        start: str | None = None,
        end: str | None = None,
        limit: int = 50,
    ) -> _FakePayload:
        _ = start, end, limit
        return _FakePayload(
            {
                "coverage": "BEST_EFFORT",
                "method": "Heuristic correlation over run timestamps and recompute/apply evidence.",
                "window": {"start": start, "end": end},
                "candidates": [
                    {
                        "started_at": "2026-03-01T10:00:00+00:00",
                        "ended_at": "2026-03-01T10:02:00+00:00",
                        "inferred_run_id": "33333333-3333-3333-3333-333333333333",
                        "inferred_folder_path": None,
                        "estimated_ledger_rows_touched": 12,
                        "confidence": "MEDIUM",
                        "signals": ["run_without_apply_audit", "nearby_canonical_recompute_dry_run"],
                    }
                ],
                "limitations": ["Historical run rows do not persist a dry_run flag."],
            }
        )

    def get_ledger_hash_audit(
        self,
        *,
        root_path: str | None = None,
        sample_limit: int = 20,
    ) -> _FakePayload:
        self.last_media_file_call = {
            "mode": "hash_audit",
            "root_path": root_path,
            "sample_limit": sample_limit,
        }
        return _FakePayload(
            {
                "total_files": 10,
                "missing_hash": 2,
                "hash_mismatches": 1,
                "deleted_rows_skipped": 3,
                "sample_missing_hash_paths": ["/ledger/missing-1.jpg", "/ledger/missing-2.jpg"],
                "sample_mismatch_paths": ["/ledger/mismatch-1.jpg"],
            }
        )

    def resolve_thumbnail_source(self, file_instance_id: UUID) -> tuple[Path, str] | None:
        if str(file_instance_id) == "aaaaaaaa-0000-0000-0000-000000000001":
            return Path(__file__), "image/jpeg"
        return None

    def resolve_media_source(self, file_instance_id: UUID) -> tuple[Path, str] | None:
        if str(file_instance_id) in {
            "33333333-0000-0000-0000-000000000001",
            "33333333-0000-0000-0000-000000000002",
        }:
            return Path(__file__), "video/mp4"
        return None

    def get_canonical_gallery_detail(self, file_instance_id: UUID) -> _FakePayload | None:
        if str(file_instance_id) == "33333333-0000-0000-0000-000000000001":
            return _FakePayload(
                {
                    "id": "33333333-0000-0000-0000-000000000001",
                    "filename": "canon-a.jpg",
                    "file_type": "image",
                    "media_url": "/media/33333333-0000-0000-0000-000000000001",
                    "absolute_path": "/dataset/canon-a.jpg",
                }
            )
        return None


class _FakePayload:
    """Fake dataclass-like payload exposing a `to_dict` contract."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def to_dict(self) -> dict[str, Any]:
        return dict(self._payload)


class _FakePolicyService:
    """Simple fake service for policy API/page tests."""

    def __init__(self) -> None:
        self._version = 7

    def get_settings(self) -> _FakePayload:
        return _FakePayload(
            {
                "canonical_priority": {
                    "selected_policy": "PREFER_ROOT",
                    "preferred_roots": ["/archive", "/media"],
                },
                "tie_breaker_rules": {
                    "effective_order": [
                        "preferred_root_match DESC",
                        "first_seen_at ASC",
                        "file_instance_id ASC",
                    ],
                    "policy_name": "PREFER_ROOT",
                    "policy_version": "v1",
                },
                "recanonicalization": {"enabled": True},
                "metadata": {
                    "updated_at": "2026-03-01T10:00:00+00:00",
                    "version": self._version,
                },
            }
        )

    def update_settings(self, command) -> _FakePayload:
        if command.version != self._version:
            raise ServiceLayerException(
                code="POLICY_VERSION_CONFLICT",
                message="Policy settings version conflict: expected 7, got stale.",
                http_status=409,
            )
        self._version += 1
        return _FakePayload(
            {
                "canonical_priority": {
                    "selected_policy": command.selected_policy,
                    "preferred_roots": list(command.preferred_roots),
                },
                "tie_breaker_rules": {
                    "effective_order": [
                        "preferred_root_match DESC",
                        "first_seen_at ASC",
                        "file_instance_id ASC",
                    ],
                    "policy_name": command.selected_policy,
                    "policy_version": "v1",
                },
                "recanonicalization": {"enabled": command.recanonicalization_enabled},
                "metadata": {
                    "updated_at": "2026-03-01T10:30:00+00:00",
                    "version": self._version,
                },
            }
        )


class _FakeRunTriggerResult:
    """Simple fake trigger result that matches API contract shape."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def to_dict(self) -> dict[str, Any]:
        return dict(self._payload)


class _FakeRunTriggerService:
    """Simple fake run-trigger service for API tests."""

    def trigger_run(self, command) -> _FakeRunTriggerResult:
        if command.folder_path == "/missing":
            raise ValueError("Folder path does not exist: /missing")
        if command.dry_run:
            return _FakeRunTriggerResult(
                {
                    "mode": "VALIDATION_ONLY",
                    "validation_report": {
                        "mode": "VALIDATION_ONLY",
                        "root_path": command.folder_path,
                        "generated_at": "2026-03-03T00:00:00+00:00",
                        "scan": {"files_scanned": 12, "files_missing_during_scan": 0},
                        "delta": {
                            "would_insert": 6,
                            "would_update": 4,
                            "would_mark_deleted": 2,
                            "hash_mismatch_observed": 1,
                            "would_reappear_after_delete": 0,
                        },
                        "samples": {
                            "would_insert": [],
                            "would_update": [],
                            "would_mark_deleted": [],
                            "hash_mismatch_observed": [],
                        },
                        "warnings": [],
                    },
                }
            )
        return _FakeRunTriggerResult(
            {
                "mode": "EXECUTION",
                "run_id": "33333333-3333-3333-3333-333333333333",
                "summary_metrics": {
                    "ingest": {
                        "files_scanned": 12,
                        "new_contents": 6,
                        "new_instances": 8,
                        "duplicates_detected": 4,
                        "metadata_extracted": 10,
                    },
                    "plan": {
                        "scanned_count": 8,
                        "move_actions": 3,
                        "duplicate_actions": 2,
                        "noop_actions": 2,
                        "skipped_count": 1,
                    },
                    "apply": None if command.dry_run else {"applied_count": 5, "moves_count": 3, "duplicates_count": 2, "noop_count": 0, "errors_count": 0, "skipped_count": 0},
                    "dry_run": command.dry_run,
                    "policy_name": command.policy_name.upper(),
                },
                "duplicates_found": 2,
                "canonical_changes": 1,
            }
        )


class _FakeIngestService:
    def validate_path(self, folder) -> _FakePayload:
        if str(folder) == "/missing":
            raise ValueError("Folder path does not exist: /missing")
        return _FakePayload(
            {
                "mode": "VALIDATION_ONLY",
                "root_path": str(folder),
                "generated_at": "2026-03-03T00:00:00+00:00",
                "scan": {"files_scanned": 3, "files_missing_during_scan": 0},
                "delta": {
                    "would_insert": 1,
                    "would_update": 1,
                    "would_mark_deleted": 0,
                    "hash_mismatch_observed": 0,
                    "would_reappear_after_delete": 0,
                },
                "samples": {
                    "would_insert": [],
                    "would_update": [],
                    "would_mark_deleted": [],
                    "hash_mismatch_observed": [],
                },
                "warnings": [],
            }
        )


class _FakeReadServices:
    def __init__(self) -> None:
        self.last_gallery_call: dict[str, Any] | None = None
        self.last_tag_suggestions_call: dict[str, Any] | None = None
        self.last_media_file_call: dict[str, Any] | None = None

    def status(self) -> dict[str, object]:
        return {"active_phase": "phase13"}

    def dashboard_summary(self) -> dict[str, object]:
        return {
            "total_files": 10,
            "total_images": 6,
            "total_videos": 4,
            "duplicate_groups": 2,
            "canonical_files": 8,
            "total_runs": 3,
        }

    def latest_metrics(self) -> dict[str, object]:
        return {
            "ingest_time_ms": 12.5,
            "plan_time_ms": 6.0,
            "apply_time_ms": 4.5,
            "db_time_ms": 9.2,
            "cache_hit_rate": 92.0,
            "last_regression_status": "PASS",
        }

    def runs(self, *, limit: int, operation_type: str | None = None, status: str | None = None) -> list[dict[str, object]]:
        _ = limit, operation_type, status
        return [{"operation_run_id": "abc", "operation_type": "INGEST", "status": "COMPLETED"}]

    def operation_runs(
        self, *, limit: int, operation_type: str | None = None, status: str | None = None
    ) -> list[dict[str, object]]:
        return self.runs(limit=limit, operation_type=operation_type, status=status)

    def internal_runs(self, *, limit: int) -> list[dict[str, object]]:
        _ = limit
        return [
            {
                "run_id": "11111111-1111-1111-1111-111111111111",
                "timestamp": "2026-03-01T09:30:00+00:00",
                "files_processed": 24,
                "duplicates_found": 2,
                "runtime_ms": 1250.4,
                "regression_status": "PASS",
            },
            {
                "run_id": "22222222-2222-2222-2222-222222222222",
                "timestamp": "2026-03-01T08:15:00+00:00",
                "files_processed": 18,
                "duplicates_found": 1,
                "runtime_ms": 980.0,
                "regression_status": "FAIL",
            },
        ]

    def canonical(self, **kwargs) -> dict[str, object]:  # type: ignore[no-untyped-def]
        self.last_gallery_call = dict(kwargs)
        if kwargs.get("page", 1) > 10:
            return {"total_count": 2, "page": kwargs.get("page", 1), "limit": 30, "total_pages": 1, "items": []}
        return {
            "total_count": 2,
            "page": kwargs.get("page", 1),
            "limit": kwargs.get("limit", 30),
            "total_pages": 1,
            "items": [
                {
                    "id": "33333333-0000-0000-0000-000000000001",
                    "filename": "canon-a.jpg",
                    "file_type": "image",
                    "media_url": "/media/33333333-0000-0000-0000-000000000001",
                    "matched_tags": ["city", "travel"],
                    "top_confidence_score": 0.92,
                    "sort_tag_name": "city",
                },
                {
                    "id": "33333333-0000-0000-0000-000000000002",
                    "filename": "canon-b.mov",
                    "file_type": "video",
                    "media_url": "/media/33333333-0000-0000-0000-000000000002",
                    "matched_tags": [],
                    "top_confidence_score": None,
                    "sort_tag_name": None,
                },
            ],
        }

    def canonical_tags(self, *, q: str | None, limit: int) -> dict[str, object]:
        self.last_tag_suggestions_call = {"q": q, "limit": limit}
        base = ("city", "city night", "travel", "wildlife")
        return {"items": list(base[: max(1, min(50, int(limit)))])}

    def duplicates(self) -> dict[str, object]:
        return {
            "groups": [
                {
                    "group_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "files": [
                        {
                            "file_instance_id": "aaaaaaaa-0000-0000-0000-000000000001",
                            "absolute_path": "/dataset/a.jpg",
                            "media_type": "IMG",
                            "is_image": True,
                            "thumbnail_url": "/api/thumbnail/aaaaaaaa-0000-0000-0000-000000000001",
                        },
                        {
                            "file_instance_id": "aaaaaaaa-0000-0000-0000-000000000002",
                            "absolute_path": "/dataset/b.jpg",
                            "media_type": "IMG",
                            "is_image": True,
                            "thumbnail_url": "/api/thumbnail/aaaaaaaa-0000-0000-0000-000000000002",
                        },
                    ],
                    "canonical_file": {
                        "file_instance_id": "aaaaaaaa-0000-0000-0000-000000000001",
                        "absolute_path": "/dataset/a.jpg",
                    },
                }
            ]
        }

    def media_file_by_hash(self, *, hash_prefix: str, page: int, limit: int) -> dict[str, object]:
        self.last_media_file_call = {"mode": "hash", "hash_prefix": hash_prefix, "page": page, "limit": limit}
        return self._ledger_payload(page=page, limit=limit)

    def media_file_history(self, *, path: str, page: int, limit: int) -> dict[str, object]:
        self.last_media_file_call = {"mode": "history", "path": path, "page": page, "limit": limit}
        return self._ledger_payload(page=page, limit=limit)

    def media_file_by_status(self, *, status: str, page: int, limit: int) -> dict[str, object]:
        if status.upper() not in {"INGESTED", "PROCESSED", "DELETED"}:
            raise ValueError("status must be one of: INGESTED, PROCESSED, DELETED.")
        self.last_media_file_call = {"mode": "status", "status": status.upper(), "page": page, "limit": limit}
        return self._ledger_payload(page=page, limit=limit)

    def media_file_reappearances(self, *, path: str, page: int, limit: int) -> dict[str, object]:
        self.last_media_file_call = {"mode": "reappearances", "path": path, "page": page, "limit": limit}
        return self._ledger_payload(page=page, limit=limit)

    def media_file_analytics(self) -> dict[str, object]:
        return {
            "totals": {"files_tracked": 11, "duplicate_hash_groups": 2},
            "by_status": {"INGESTED": 6, "PROCESSED": 3, "DELETED": 2},
            "ingested_per_day": [{"day": "2026-03-01", "count": 4}],
            "deleted_per_day": [{"day": "2026-03-01", "count": 1}],
            "reappearances_per_day": [{"day": "2026-03-02", "count": 2}],
            "window": {"mode": "all_time"},
        }

    def ledger_hash_audit(self, *, root_path: str | None, sample_limit: int) -> dict[str, object]:
        self.last_media_file_call = {"mode": "hash_audit", "root_path": root_path, "sample_limit": sample_limit}
        return {
            "total_files": 10,
            "missing_hash": 2,
            "hash_mismatches": 1,
            "deleted_rows_skipped": 0,
            "sample_missing_hash_paths": ["/ledger/a.jpg"],
            "sample_mismatch_paths": ["/ledger/b.jpg"],
        }

    def media_file_dry_run_audit(self, *, start: str | None, end: str | None, limit: int) -> dict[str, object]:
        return {
            "coverage": "BEST_EFFORT",
            "method": "Heuristic correlation over run timestamps and recompute/apply evidence.",
            "window": {"start": start, "end": end},
            "candidates": [{"run_id": "dryrun-1", "confidence": "MEDIUM"}],
            "limitations": [],
        }

    def admin_observability_summary(self) -> dict[str, object]:
        return {
            "metrics_enabled": True,
            "prometheus_url": "http://prometheus.local",
            "grafana_url": "http://grafana.local",
            "generated_at": "2026-03-14T10:00:00+00:00",
            "window_hours": 24,
            "recent_failure_count": 2,
            "recent_runs_by_status": {"COMPLETED": 8, "FAILED": 2},
            "recent_runs_by_type": {"INGEST": 3, "PLAN": 2, "APPLY": 1},
            "last_success_by_type": {"INGEST": "2026-03-14T09:00:00+00:00", "PLAN": None},
            "latest_metrics": self.latest_metrics(),
        }

    def admin_observability_failures(self, *, limit: int) -> dict[str, object]:
        _ = limit
        return {
            "failure_events": [
                {
                    "id": "f1",
                    "run_id": "11111111-1111-1111-1111-111111111111",
                    "phase": "planning",
                    "error_code": "PLANNING_FAILED",
                    "error_message": "planner exploded",
                    "created_at": "2026-03-14T08:00:00+00:00",
                }
            ],
            "failed_operation_runs": [
                {
                    "operation_run_id": "abc",
                    "operation_type": "PLAN",
                    "status": "FAILED",
                    "started_at": "2026-03-14T08:00:00+00:00",
                    "completed_at": "2026-03-14T08:01:00+00:00",
                    "error_message": "planner exploded",
                    "context": {},
                }
            ],
        }

    def admin_observability_metrics_series(self, *, hours: int) -> dict[str, object]:
        _ = hours
        return {
            "hours": 24,
            "series": {
                "operation_volume": [{"timestamp": "2026-03-14T08:00:00+00:00", "value": 4}],
                "failure_volume": [{"timestamp": "2026-03-14T08:00:00+00:00", "value": 1}],
                "latency_ms_avg": [{"timestamp": "2026-03-14T08:00:00+00:00", "value": 88.5}],
            },
        }

    def _ledger_payload(self, *, page: int, limit: int) -> dict[str, object]:
        return {
            "total_count": 1,
            "page": page,
            "limit": limit,
            "total_pages": 1,
            "items": [
                {
                    "id": "55555555-0000-0000-0000-000000000001",
                    "current_path": "/ledger/a.jpg",
                    "discovered_path": "/ledger/a.jpg",
                    "size_bytes": 1024,
                    "hash_sha256": "a" * 64,
                    "status": "INGESTED",
                    "discovered_at": "2026-03-01T10:00:00+00:00",
                    "ingested_at": "2026-03-01T10:00:01+00:00",
                    "deleted_at": None,
                }
            ],
        }


class _FakeOperationServices:
    def ingest(self, *, folder_path: str, dry_run: bool) -> dict[str, object]:
        return {
            "operation": "INGEST",
            "mode": "VALIDATION_ONLY" if dry_run else "EXECUTION",
            "report": {"scan": {"files_scanned": 3}},
            "summary": {
                "files_scanned": 3,
                "new_contents": 1,
                "new_instances": 2,
                "duplicates_detected": 0,
                "metadata_extracted": 3,
                "duration_s": 0.25,
            },
            "folder_path": folder_path,
        }

    def plan(self, *, folder_path: str, strict_metadata: bool) -> dict[str, object]:
        return {
            "operation": "PLAN",
            "run_id": "11111111-1111-1111-1111-111111111111",
            "strict_metadata": strict_metadata,
            "summary": {"scanned_count": 2, "move_actions": 1, "noop_actions": 1, "duplicate_actions": 0},
            "folder_path": folder_path,
        }

    def apply(self, *, run_id: str, collision_mode: str) -> dict[str, object]:
        _ = UUID(run_id)
        if collision_mode not in {"rename", "skip", "fail"}:
            raise ValueError("collision_mode must be one of: rename, skip, fail.")
        return {
            "operation": "APPLY",
            "run_id": run_id,
            "collision_mode": collision_mode,
            "summary": {"applied_count": 2, "moves_count": 1, "duplicates_count": 1, "noop_count": 0, "errors_count": 0, "skipped_count": 0},
        }

    def canonical_recompute(
        self,
        *,
        policy_name: str,
        dry_run: bool,
        preferred_roots: tuple[str, ...],
    ) -> dict[str, object]:
        _ = preferred_roots
        return {
            "operation": "CANONICAL_RECOMPUTE",
            "mode": "DRY_RUN" if dry_run else "APPLY",
            "policy_name": policy_name,
            "summary": {"scanned_count": 4, "changed_count": 1, "applied_count": 0 if dry_run else 1},
        }

    def operator_run(self, *, folder_path: str, policy_name: str, dry_run: bool) -> dict[str, object]:
        return self.run(folder_path=folder_path, policy_name=policy_name, dry_run=dry_run)

    def run(self, *, folder_path: str, policy_name: str, dry_run: bool) -> dict[str, object]:
        if folder_path == "/missing":
            raise ValueError("Folder path does not exist: /missing")
        if dry_run:
            return {
                "mode": "VALIDATION_ONLY",
                "validation_report": {
                    "mode": "VALIDATION_ONLY",
                    "root_path": folder_path,
                    "generated_at": "2026-03-03T00:00:00+00:00",
                    "scan": {"files_scanned": 12, "files_missing_during_scan": 0},
                    "delta": {
                        "would_insert": 6,
                        "would_update": 4,
                        "would_mark_deleted": 2,
                        "hash_mismatch_observed": 1,
                        "would_reappear_after_delete": 0,
                    },
                    "samples": {
                        "would_insert": [],
                        "would_update": [],
                        "would_mark_deleted": [],
                        "hash_mismatch_observed": [],
                    },
                    "warnings": [],
                },
            }
        return {
            "mode": "EXECUTION",
            "run_id": "33333333-3333-3333-3333-333333333333",
            "summary_metrics": {
                "ingest": {
                    "files_scanned": 12,
                    "new_contents": 6,
                    "new_instances": 8,
                    "duplicates_detected": 4,
                    "metadata_extracted": 10,
                },
                "plan": {
                    "scanned_count": 8,
                    "move_actions": 3,
                    "duplicate_actions": 2,
                    "noop_actions": 2,
                    "skipped_count": 1,
                },
                "apply": {
                    "applied_count": 5,
                    "moves_count": 3,
                    "duplicates_count": 2,
                    "noop_count": 0,
                    "errors_count": 0,
                    "skipped_count": 0,
                },
                "dry_run": False,
                "policy_name": policy_name.upper(),
            },
            "duplicates_found": 2,
            "canonical_changes": 1,
        }

    def operations_catalog(self) -> dict[str, object]:
        return {
            "items": [
                {"operation_id": "ingest", "supports_dry_run": True},
                {"operation_id": "plan", "supports_dry_run": False},
            ]
        }

    def policy_get(self) -> dict[str, object]:
        return {
            "canonical_priority": {
                "selected_policy": "PREFER_ROOT",
                "preferred_roots": ["/archive", "/media"],
            },
            "tie_breaker_rules": {
                "effective_order": [
                    "preferred_root_match DESC",
                    "first_seen_at ASC",
                    "file_instance_id ASC",
                ],
                "policy_name": "PREFER_ROOT",
                "policy_version": "v1",
            },
            "recanonicalization": {"enabled": True},
            "metadata": {
                "updated_at": "2026-03-01T10:00:00+00:00",
                "version": 7,
            },
        }

    def policy_set(
        self,
        *,
        selected_policy: str,
        preferred_roots: tuple[str, ...],
        recanonicalization_enabled: bool,
        version: int,
    ) -> dict[str, object]:
        if version != 7:
            raise ServiceLayerException(
                code="POLICY_VERSION_CONFLICT",
                message="Policy settings version conflict: expected 7, got stale.",
                http_status=409,
            )
        return {
            "canonical_priority": {
                "selected_policy": selected_policy,
                "preferred_roots": list(preferred_roots),
            },
            "tie_breaker_rules": {
                "effective_order": [
                    "preferred_root_match DESC",
                    "first_seen_at ASC",
                    "file_instance_id ASC",
                ],
                "policy_name": selected_policy,
                "policy_version": "v1",
            },
            "recanonicalization": {"enabled": recanonicalization_enabled},
            "metadata": {
                "updated_at": "2026-03-01T10:30:00+00:00",
                "version": 8,
            },
        }

    def tag_enrichment(self, *, run_all: bool, canonical_id: str | None, batch_size: int, source: str) -> dict[str, object]:
        _ = source
        if run_all == (canonical_id is not None):
            raise ValueError("Specify exactly one of all=true or canonical_id.")
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0.")
        return {"scope": "ALL" if run_all else "SINGLE", "number_of_items_processed": 2, "operation_run_id": "op-1"}

    def media_file_validate(self, *, folder_path: str) -> dict[str, object]:
        if not Path(folder_path).exists():
            raise ValueError(f"Folder path does not exist: {folder_path}")
        return {
            "mode": "VALIDATION_ONLY",
            "root_path": folder_path,
            "generated_at": "2026-03-03T00:00:00+00:00",
            "scan": {"files_scanned": 3, "files_missing_during_scan": 0},
            "delta": {
                "would_insert": 1,
                "would_update": 1,
                "would_mark_deleted": 0,
                "hash_mismatch_observed": 0,
                "would_reappear_after_delete": 0,
            },
            "samples": {
                "would_insert": [],
                "would_update": [],
                "would_mark_deleted": [],
                "hash_mismatch_observed": [],
            },
            "warnings": [],
        }


class _FakeAdminServices:
    def db_reset(self, *, dry_run: bool, challenge_word: str | None) -> dict[str, object]:
        if not dry_run and challenge_word != "media-manager":
            raise ValueError("challenge_word is incorrect.")
        return {
            "success": True,
            "dry_run": bool(dry_run),
            "affected_tables": ["media_file", "file_instances"],
            "message": "Dry-run only. No data deleted." if dry_run else "Database reset completed.",
        }

    def benchmark_metadata_queue(self, *, items: int, batch_size: int, challenge_word: str | None) -> dict[str, object]:
        if challenge_word != "media-manager":
            raise ValueError("challenge_word is incorrect.")
        return {
            "queued": True,
            "operation_run_id": "aaaaaaaa-1111-1111-1111-111111111111",
            "benchmark": {
                "benchmark_run_id": "bbbbbbbb-1111-1111-1111-111111111111",
                "operation_run_id": "aaaaaaaa-1111-1111-1111-111111111111",
                "benchmark_type": "METADATA",
                "status": "QUEUED",
                "parameters": {"items": items, "batch_size": batch_size},
                "queued_at": "2026-03-14T10:00:00+00:00",
                "started_at": None,
                "completed_at": None,
                "cancel_requested_at": None,
            },
        }

    def benchmark_discovery_queue(self, *, items: int, challenge_word: str | None) -> dict[str, object]:
        if challenge_word != "media-manager":
            raise ValueError("challenge_word is incorrect.")
        return {
            "queued": True,
            "operation_run_id": "cccccccc-1111-1111-1111-111111111111",
            "benchmark": {
                "benchmark_run_id": "dddddddd-1111-1111-1111-111111111111",
                "operation_run_id": "cccccccc-1111-1111-1111-111111111111",
                "benchmark_type": "DISCOVERY",
                "status": "QUEUED",
                "parameters": {"items": items},
                "queued_at": "2026-03-14T10:00:00+00:00",
                "started_at": None,
                "completed_at": None,
                "cancel_requested_at": None,
            },
        }

    def benchmark_runs(self, *, limit: int = 50) -> list[dict[str, object]]:
        _ = limit
        return [
            {
                "benchmark_run_id": "bbbbbbbb-1111-1111-1111-111111111111",
                "operation_run_id": "aaaaaaaa-1111-1111-1111-111111111111",
                "benchmark_type": "METADATA",
                "status": "QUEUED",
                "parameters": {"items": 1000, "batch_size": 250},
                "queued_at": "2026-03-14T10:00:00+00:00",
                "started_at": None,
                "completed_at": None,
                "cancel_requested_at": None,
                "report_payload": None,
                "summary_payload": None,
                "cleanup_status": None,
                "cleanup_error": None,
                "error_message": None,
            }
        ]

    def benchmark_run_detail(self, *, operation_run_id: str) -> dict[str, object]:
        return {
            "benchmark_run_id": "bbbbbbbb-1111-1111-1111-111111111111",
            "operation_run_id": operation_run_id,
            "benchmark_type": "METADATA",
            "status": "COMPLETED",
            "parameters": {"items": 1000, "batch_size": 250},
            "queued_at": "2026-03-14T10:00:00+00:00",
            "started_at": "2026-03-14T10:00:01+00:00",
            "completed_at": "2026-03-14T10:00:03+00:00",
            "cancel_requested_at": None,
            "report_payload": {"results": [{"scenario": "metadata"}]},
            "summary_payload": {"throughput_files_per_s": 1000.0},
            "cleanup_status": "COMPLETED",
            "cleanup_error": None,
            "error_message": None,
        }

    def benchmark_run_cancel(self, *, operation_run_id: str) -> dict[str, object]:
        return {
            "benchmark_run_id": "bbbbbbbb-1111-1111-1111-111111111111",
            "operation_run_id": operation_run_id,
            "benchmark_type": "METADATA",
            "status": "CANCEL_REQUESTED",
            "parameters": {"items": 1000, "batch_size": 250},
            "queued_at": "2026-03-14T10:00:00+00:00",
            "started_at": None,
            "completed_at": None,
            "cancel_requested_at": "2026-03-14T10:00:30+00:00",
            "report_payload": None,
            "summary_payload": None,
            "cleanup_status": None,
            "cleanup_error": None,
            "error_message": None,
        }


def test_dashboard_route_renders_template() -> None:
    """GET / should render the dashboard template through the base layout."""
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "Quick Operations" in response.text
    assert "Validate Ingest (dry-run)" in response.text
    assert "Composite Run (compatibility workflow)" in response.text
    assert "Folder Path" in response.text
    assert "Execute" in response.text
    assert "Open Operations" in response.text
    assert "Total Files" in response.text
    assert "Performance Metrics" in response.text
    assert "Media Manager Operator Console" in response.text
    assert "Dashboard</a>" in response.text
    assert "Operations</a>" in response.text
    assert "Runs</a>" in response.text
    assert "Duplicates</a>" in response.text
    assert "Policy</a>" in response.text
    assert "https://cdn.tailwindcss.com" in response.text


def test_operations_page_renders_template() -> None:
    client = TestClient(app)

    response = client.get("/operations")

    assert response.status_code == 200
    assert "Operations" in response.text
    assert "Run Ingest" in response.text
    assert "Run Plan" in response.text
    assert "Run Apply" in response.text
    assert "Run Canonical Recompute" in response.text
    assert "Run Tag Enrichment" in response.text
    assert "Run Composite" in response.text


def test_console_v2_route_serves_spa_shell() -> None:
    client = TestClient(app)

    response = client.get("/console-v2")

    assert response.status_code == 200
    assert '<div id="root"></div>' in response.text
    assert "/static-v2/assets/" in response.text


def test_legacy_routes_remain_template_based_when_v2_flag_off(monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_MANAGER_UI_V2_ENABLED", "0")
    flagged_app = main_module.create_app()
    client = TestClient(flagged_app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "Quick Operations" in response.text


def test_legacy_routes_cutover_to_v2_when_flag_enabled_including_admin(monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_MANAGER_UI_V2_ENABLED", "1")
    flagged_app = main_module.create_app()
    client = TestClient(flagged_app)

    dashboard = client.get("/")
    operations = client.get("/operations")
    admin = client.get("/admin")

    assert dashboard.status_code == 200
    assert '<div id="root"></div>' in dashboard.text
    assert "/static-v2/assets/" in dashboard.text

    assert operations.status_code == 200
    assert '<div id="root"></div>' in operations.text
    assert "/static-v2/assets/" in operations.text

    assert admin.status_code == 200
    assert '<div id="root"></div>' in admin.text
    assert "/static-v2/assets/" in admin.text


def test_dashboard_summary_endpoint_returns_json() -> None:
    """GET /api/dashboard-summary should return summary fields as JSON."""
    app.dependency_overrides[get_read_services] = _FakeReadServices
    client = TestClient(app)
    try:
        response = client.get("/api/dashboard-summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["data"]["result"] == {
        "total_files": 10,
        "total_images": 6,
        "total_videos": 4,
        "duplicate_groups": 2,
        "canonical_files": 8,
        "total_runs": 3,
    }


def test_latest_metrics_endpoint_returns_json() -> None:
    """GET /api/latest-metrics should return metrics fields as JSON."""
    app.dependency_overrides[get_read_services] = _FakeReadServices
    client = TestClient(app)
    try:
        response = client.get("/api/latest-metrics")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["data"]["result"] == {
        "ingest_time_ms": 12.5,
        "plan_time_ms": 6.0,
        "apply_time_ms": 4.5,
        "db_time_ms": 9.2,
        "cache_hit_rate": 92.0,
        "last_regression_status": "PASS",
    }


def test_runs_page_renders_template() -> None:
    """GET /runs should render the run history page template."""
    client = TestClient(app)

    response = client.get("/runs")

    assert response.status_code == 200
    assert "Run History" in response.text
    assert "Operation Type" in response.text
    assert "Linked Run ID" in response.text
    assert "Apply Filters" in response.text


def test_gallery_page_renders_template() -> None:
    """GET /gallery should render the canonical gallery page template."""
    client = TestClient(app)

    response = client.get("/gallery")

    assert response.status_code == 200
    assert "Canonical Gallery" in response.text
    assert "Browse canonical media currently stored in the database." in response.text
    assert "Previous" in response.text
    assert "Next" in response.text


def test_discover_page_renders_template_with_ssr_content() -> None:
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        response = client.get("/discover")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Discover" in response.text
    assert "discover-grid" in response.text
    assert "discover-tag-input" in response.text
    assert "discover-sort-by" in response.text
    assert "Top 0.9200" in response.text


def test_discover_page_uses_tag_name_default_sort_order_asc() -> None:
    fake = _FakeService()
    app.dependency_overrides[get_operator_console_service] = lambda: fake
    client = TestClient(app)
    try:
        response = client.get("/discover?sort_by=tag_name")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake.last_gallery_call is not None
    assert fake.last_gallery_call["sort_by"] == "tag_name"
    assert fake.last_gallery_call["sort_order"] == "asc"


def test_discover_page_rejects_invalid_sort_order() -> None:
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        response = client.get("/discover?sort_order=sideways")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "sort_order" in response.json()["detail"]


def test_discover_page_rejects_invalid_sort_by() -> None:
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        response = client.get("/discover?sort_by=broken")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "sort_by" in response.json()["detail"]


def test_ledger_page_renders_template() -> None:
    client = TestClient(app)

    response = client.get("/ledger")

    assert response.status_code == 200
    assert "MediaFile Ledger" in response.text
    assert "Ledger Health Check" in response.text
    assert "Run Hash Audit" in response.text
    assert "By Hash" in response.text
    assert "Path History" in response.text
    assert "Reappearances" in response.text


def test_runs_endpoint_returns_json() -> None:
    """GET /api/runs should return run history rows as JSON."""
    app.dependency_overrides[get_read_services] = _FakeReadServices
    client = TestClient(app)
    try:
        response = client.get("/api/runs")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["data"]["result"][0]["operation_run_id"] == "abc"


def test_status_endpoint_uses_canonical_api_base() -> None:
    app.dependency_overrides[get_read_services] = _FakeReadServices
    client = TestClient(app)
    try:
        response = client.get("/api/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["data"]["active_phase"] == "phase13"


def test_read_endpoints_use_canonical_api_base() -> None:
    app.dependency_overrides[get_read_services] = _FakeReadServices
    client = TestClient(app)
    try:
        summary = client.get("/api/dashboard-summary")
        metrics = client.get("/api/latest-metrics")
        runs = client.get("/api/runs?limit=25")
    finally:
        app.dependency_overrides.clear()

    assert summary.status_code == 200
    assert metrics.status_code == 200
    assert runs.status_code == 200
    assert summary.json()["data"]["result"]["total_files"] == 10
    assert metrics.json()["data"]["result"]["ingest_time_ms"] == 12.5
    assert runs.json()["data"]["result"][0]["operation_run_id"] == "abc"


def test_operation_runs_endpoint_uses_canonical_api_base() -> None:
    app.dependency_overrides[get_read_services] = _FakeReadServices
    client = TestClient(app)
    try:
        response = client.get("/api/operation-runs?limit=10&operation_type=INGEST&status=COMPLETED")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["data"]["result"][0]["operation_run_id"] == "abc"


def test_internal_runs_endpoint_uses_canonical_api_base() -> None:
    app.dependency_overrides[get_read_services] = _FakeReadServices
    client = TestClient(app)
    try:
        response = client.get("/api/internal-runs?limit=10")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["data"]["result"][0]["run_id"] == "11111111-1111-1111-1111-111111111111"


def test_media_file_by_hash_endpoint_returns_paginated_shape() -> None:
    fake = _FakeReadServices()
    app.dependency_overrides[get_read_services] = lambda: fake
    client = TestClient(app)
    try:
        response = client.get("/api/media-file/by-hash?hash_prefix=abcd&page=2&limit=10")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["data"]["result"]
    assert payload["page"] == 2
    assert payload["limit"] == 10
    assert payload["items"][0]["status"] == "INGESTED"
    assert fake.last_media_file_call == {"mode": "hash", "hash_prefix": "abcd", "page": 2, "limit": 10}


def test_media_file_history_endpoint_returns_paginated_shape() -> None:
    fake = _FakeReadServices()
    app.dependency_overrides[get_read_services] = lambda: fake
    client = TestClient(app)
    try:
        response = client.get("/api/media-file/history?path=/ledger/a.jpg&page=1&limit=30")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["data"]["result"]
    assert payload["total_count"] == 1
    assert fake.last_media_file_call == {"mode": "history", "path": "/ledger/a.jpg", "page": 1, "limit": 30}


def test_media_file_by_status_endpoint_returns_paginated_shape() -> None:
    fake = _FakeReadServices()
    app.dependency_overrides[get_read_services] = lambda: fake
    client = TestClient(app)
    try:
        response = client.get("/api/media-file/by-status?status=processed&page=1&limit=30")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["data"]["result"]
    assert payload["items"][0]["hash_sha256"] == "a" * 64
    assert fake.last_media_file_call == {"mode": "status", "status": "PROCESSED", "page": 1, "limit": 30}


def test_media_file_reappearances_endpoint_returns_paginated_shape() -> None:
    fake = _FakeReadServices()
    app.dependency_overrides[get_read_services] = lambda: fake
    client = TestClient(app)
    try:
        response = client.get("/api/media-file/reappearances?path=/ledger/a.jpg&page=1&limit=5")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["data"]["result"]
    assert payload["items"][0]["current_path"] == "/ledger/a.jpg"
    assert fake.last_media_file_call == {"mode": "reappearances", "path": "/ledger/a.jpg", "page": 1, "limit": 5}


def test_media_file_analytics_endpoint_returns_expected_shape() -> None:
    app.dependency_overrides[get_read_services] = _FakeReadServices
    client = TestClient(app)
    try:
        response = client.get("/api/media-file/analytics")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["data"]["result"]
    assert payload["totals"]["files_tracked"] == 11
    assert payload["totals"]["duplicate_hash_groups"] == 2
    assert payload["by_status"]["INGESTED"] == 6
    assert payload["window"]["mode"] == "all_time"


def test_media_file_hash_audit_endpoint_returns_expected_shape() -> None:
    fake = _FakeReadServices()
    app.dependency_overrides[get_read_services] = lambda: fake
    client = TestClient(app)
    try:
        response = client.get("/api/admin/hash-audit?root_path=/ledger&sample_limit=25")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["data"]["result"]
    assert payload["total_files"] == 10
    assert payload["missing_hash"] == 2
    assert payload["hash_mismatches"] == 1
    assert fake.last_media_file_call == {"mode": "hash_audit", "root_path": "/ledger", "sample_limit": 25}


def test_media_file_hash_audit_endpoint_rejects_invalid_params() -> None:
    app.dependency_overrides[get_read_services] = _FakeReadServices
    client = TestClient(app)
    try:
        bad_sample = client.get("/api/admin/hash-audit?sample_limit=500")
        bad_root = client.get("/api/admin/hash-audit?root_path= ")
    finally:
        app.dependency_overrides.clear()

    assert bad_sample.status_code == 400
    assert bad_sample.json()["ok"] is False
    assert "sample_limit" in bad_sample.json()["errors"][0]["message"]
    assert bad_root.status_code == 400
    assert "root_path" in bad_root.json()["errors"][0]["message"]


def test_media_file_dry_run_audit_endpoint_returns_expected_shape() -> None:
    app.dependency_overrides[get_read_services] = _FakeReadServices
    client = TestClient(app)
    try:
        response = client.get("/api/media-file/dry-run-audit?limit=10")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["data"]["result"]
    assert payload["coverage"] == "BEST_EFFORT"
    assert payload["candidates"][0]["confidence"] == "MEDIUM"


def test_media_file_dry_run_audit_endpoint_rejects_invalid_limit() -> None:
    app.dependency_overrides[get_read_services] = _FakeReadServices
    client = TestClient(app)
    try:
        response = client.get("/api/media-file/dry-run-audit?limit=999")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert "limit" in response.json()["errors"][0]["message"]


def test_post_media_file_validate_returns_validation_payload(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir(parents=True, exist_ok=True)
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/media-file/validate",
            json={"folder_path": str(dataset), "policy_name": "FIRST_SEEN"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["data"]["result"]
    assert payload["mode"] == "VALIDATION_ONLY"
    assert payload["delta"]["would_insert"] == 1


def test_post_media_file_validate_rejects_invalid_folder(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/media-file/validate",
            json={"folder_path": str(missing), "policy_name": None},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert "does not exist" in response.json()["errors"][0]["message"]


def test_media_file_endpoints_reject_invalid_inputs() -> None:
    app.dependency_overrides[get_read_services] = _FakeReadServices
    client = TestClient(app)
    try:
        empty_hash = client.get("/api/media-file/by-hash?hash_prefix= ")
        empty_path = client.get("/api/media-file/history?path=")
        bad_status = client.get("/api/media-file/by-status?status=bad")
        bad_page = client.get("/api/media-file/reappearances?path=/x&page=0")
        bad_limit = client.get("/api/media-file/reappearances?path=/x&limit=999")
    finally:
        app.dependency_overrides.clear()

    assert empty_hash.status_code == 400
    assert "hash_prefix" in empty_hash.json()["errors"][0]["message"]
    assert empty_path.status_code == 400
    assert "path" in empty_path.json()["errors"][0]["message"]
    assert bad_status.status_code == 400
    assert "status" in bad_status.json()["errors"][0]["message"]
    assert bad_page.status_code == 400
    assert "page" in bad_page.json()["errors"][0]["message"]
    assert bad_limit.status_code == 400
    assert "limit" in bad_limit.json()["errors"][0]["message"]


def test_api_canonical_returns_paginated_shape() -> None:
    """GET /api/canonical should return paginated canonical media payload."""
    app.dependency_overrides[get_read_services] = _FakeReadServices
    client = TestClient(app)
    try:
        response = client.get("/api/canonical?page=1&limit=30")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["data"]["result"] == {
        "total_count": 2,
        "page": 1,
        "limit": 30,
        "total_pages": 1,
        "items": [
            {
                "id": "33333333-0000-0000-0000-000000000001",
                "filename": "canon-a.jpg",
                "file_type": "image",
                "media_url": "/media/33333333-0000-0000-0000-000000000001",
                "matched_tags": ["city", "travel"],
                "top_confidence_score": 0.92,
                "sort_tag_name": "city",
            },
            {
                "id": "33333333-0000-0000-0000-000000000002",
                "filename": "canon-b.mov",
                "file_type": "video",
                "media_url": "/media/33333333-0000-0000-0000-000000000002",
                "matched_tags": [],
                "top_confidence_score": None,
                "sort_tag_name": None,
            },
        ],
    }


def test_api_canonical_out_of_range_page_returns_empty_items() -> None:
    """GET /api/canonical should preserve page and return empty items when out-of-range."""
    app.dependency_overrides[get_read_services] = _FakeReadServices
    client = TestClient(app)
    try:
        response = client.get("/api/canonical?page=99&limit=30")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["data"]["result"]
    assert payload["page"] == 99
    assert payload["items"] == []


def test_api_canonical_accepts_discovery_query_params() -> None:
    """GET /api/canonical should accept filtering and sorting query params."""
    app.dependency_overrides[get_read_services] = _FakeReadServices
    client = TestClient(app)
    try:
        response = client.get(
            "/api/canonical?page=1&limit=30&tags=city,travel&sort_by=tag_name&sort_order=asc&source=ai&min_confidence=0.5"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["data"]["result"]
    assert payload["page"] == 1
    assert payload["items"][0]["matched_tags"] == ["city", "travel"]


def test_api_canonical_applies_default_sort_order_for_tag_name() -> None:
    fake = _FakeReadServices()
    app.dependency_overrides[get_read_services] = lambda: fake
    client = TestClient(app)
    try:
        response = client.get("/api/canonical?sort_by=tag_name")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake.last_gallery_call is not None
    assert fake.last_gallery_call["sort_order"] == "asc"


def test_api_canonical_rejects_invalid_sort_by() -> None:
    app.dependency_overrides[get_read_services] = _FakeReadServices
    client = TestClient(app)
    try:
        response = client.get("/api/canonical?sort_by=unsupported")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "sort_by" in response.json()["errors"][0]["message"]


def test_api_canonical_rejects_invalid_source_and_confidence() -> None:
    app.dependency_overrides[get_read_services] = _FakeReadServices
    client = TestClient(app)
    try:
        bad_source = client.get("/api/canonical?source=bad")
        bad_conf = client.get("/api/canonical?min_confidence=3.0")
    finally:
        app.dependency_overrides.clear()

    assert bad_source.status_code == 400
    assert "source" in bad_source.json()["errors"][0]["message"]
    assert bad_conf.status_code == 400
    assert "min_confidence" in bad_conf.json()["errors"][0]["message"]


def test_api_canonical_tags_returns_suggestions() -> None:
    fake = _FakeReadServices()
    app.dependency_overrides[get_read_services] = lambda: fake
    client = TestClient(app)
    try:
        response = client.get("/api/canonical/tags?q=ci&limit=2")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["data"]["result"] == {"items": ["city", "city night"]}
    assert fake.last_tag_suggestions_call == {"q": "ci", "limit": 2}


def test_media_endpoint_streams_file() -> None:
    """GET /media/{id} should stream media bytes when row is eligible."""
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        response = client.get("/media/33333333-0000-0000-0000-000000000001")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("video/mp4")


def test_media_endpoint_returns_404_for_missing() -> None:
    """GET /media/{id} should return 404 when media cannot be resolved."""
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        response = client.get("/media/33333333-0000-0000-0000-000000000099")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_gallery_detail_page_renders_template() -> None:
    """GET /gallery/{id} should render detailed canonical media page."""
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        response = client.get("/gallery/33333333-0000-0000-0000-000000000001?page=3")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Canonical Media Detail" in response.text
    assert "canon-a.jpg" in response.text
    assert "/gallery?page=3" in response.text


def test_gallery_detail_page_returns_404_for_unknown() -> None:
    """GET /gallery/{id} should return 404 when no canonical detail row exists."""
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        response = client.get("/gallery/33333333-0000-0000-0000-000000000099")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_duplicates_page_renders_template() -> None:
    """GET /duplicates should render the duplicate group browser page template."""
    client = TestClient(app)

    response = client.get("/duplicates")

    assert response.status_code == 200
    assert "Duplicate Group Browser" in response.text
    assert "Group Details" in response.text
    assert "Loading duplicate groups" in response.text


def test_duplicates_endpoint_returns_json() -> None:
    """GET /api/duplicates should return duplicate group payload."""
    app.dependency_overrides[get_read_services] = _FakeReadServices
    client = TestClient(app)
    try:
        response = client.get("/api/duplicates")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["data"]["result"] == {
        "groups": [
            {
                "group_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "files": [
                    {
                        "file_instance_id": "aaaaaaaa-0000-0000-0000-000000000001",
                        "absolute_path": "/dataset/a.jpg",
                        "media_type": "IMG",
                        "is_image": True,
                        "thumbnail_url": "/api/thumbnail/aaaaaaaa-0000-0000-0000-000000000001",
                    },
                    {
                        "file_instance_id": "aaaaaaaa-0000-0000-0000-000000000002",
                        "absolute_path": "/dataset/b.jpg",
                        "media_type": "IMG",
                        "is_image": True,
                        "thumbnail_url": "/api/thumbnail/aaaaaaaa-0000-0000-0000-000000000002",
                    },
                ],
                "canonical_file": {
                    "file_instance_id": "aaaaaaaa-0000-0000-0000-000000000001",
                    "absolute_path": "/dataset/a.jpg",
                },
            }
        ]
    }


def test_thumbnail_endpoint_returns_file_response() -> None:
    """GET /api/thumbnail/{id} should stream image bytes when eligible."""
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        response = client.get("/api/thumbnail/aaaaaaaa-0000-0000-0000-000000000001")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/jpeg")


def test_thumbnail_endpoint_returns_404_for_missing_or_ineligible() -> None:
    """GET /api/thumbnail/{id} should return 404 when thumbnail is unavailable."""
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        response = client.get("/api/thumbnail/aaaaaaaa-0000-0000-0000-000000000099")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_policy_page_renders_template() -> None:
    """GET /policy should render the policy management page template."""
    client = TestClient(app)

    response = client.get("/policy")

    assert response.status_code == 200
    assert "Policy Configuration" in response.text
    assert "Canonical Priority Rules" in response.text
    assert "Tie-breaker Rules" in response.text
    assert "Recanonicalization" in response.text


def test_admin_page_renders_template() -> None:
    client = TestClient(app)
    response = client.get("/admin")
    assert response.status_code == 200
    assert "Reset Database" in response.text
    assert "Dry-run complete. Review affected tables." in response.text


def test_get_policy_endpoint_returns_structured_json() -> None:
    """GET /api/policy should return structured policy payload."""
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.get("/api/policy")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["data"]["result"]
    assert payload["canonical_priority"]["selected_policy"] == "PREFER_ROOT"
    assert payload["canonical_priority"]["preferred_roots"] == ["/archive", "/media"]
    assert payload["recanonicalization"]["enabled"] is True
    assert payload["metadata"]["version"] == 7


def test_post_policy_endpoint_updates_settings() -> None:
    """POST /api/policy should persist settings and return confirmation payload."""
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/policy",
            json={
                "selected_policy": "PREFER_ROOT",
                "preferred_roots": ["/a", "/b"],
                "recanonicalization_enabled": False,
                "version": 7,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["data"]["result"]
    assert payload["canonical_priority"]["preferred_roots"] == ["/a", "/b"]
    assert payload["metadata"]["version"] == 8


def test_post_policy_endpoint_returns_version_conflict() -> None:
    """POST /api/policy should return 409 on stale version updates."""
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/policy",
            json={
                "selected_policy": "FIRST_SEEN",
                "preferred_roots": [],
                "recanonicalization_enabled": False,
                "version": 6,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "version conflict" in response.json()["errors"][0]["message"].lower()


def test_post_run_endpoint_returns_trigger_summary() -> None:
    """POST /api/run should return run trigger result payload."""
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/run",
            json={
                "folder_path": "/dataset",
                "policy_name": "PREFER_ROOT",
                "dry_run": True,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["data"]["result"]
    assert payload["mode"] == "VALIDATION_ONLY"
    assert payload["validation_report"]["delta"]["would_update"] == 4
    assert payload["validation_report"]["scan"]["files_scanned"] == 12


def test_post_run_endpoint_non_dry_run_returns_execution_payload() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/run",
            json={
                "folder_path": "/dataset",
                "policy_name": "PREFER_ROOT",
                "dry_run": False,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["data"]["result"]
    assert payload["mode"] == "EXECUTION"
    assert payload["run_id"] == "33333333-3333-3333-3333-333333333333"
    assert payload["summary_metrics"]["dry_run"] is False


def test_post_ingest_uses_canonical_api_base() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post("/api/ingest", json={"folder_path": "/dataset", "dry_run": True})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["data"]["result"]["operation"] == "INGEST"


def test_post_ingest_execute_returns_summary_fields() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post("/api/ingest", json={"folder_path": "/dataset", "dry_run": False})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["data"]["result"]
    assert payload["mode"] == "EXECUTION"
    assert payload["summary"]["files_scanned"] == 3
    assert payload["summary"]["new_contents"] == 1
    assert payload["summary"]["new_instances"] == 2
    assert payload["summary"]["duplicates_detected"] == 0
    assert payload["summary"]["metadata_extracted"] == 3
    assert payload["summary"]["duration_s"] == 0.25


def test_post_ingest_invalid_path_returns_actionable_400() -> None:
    class _BadPathOperationServices(_FakeOperationServices):
        def ingest(self, *, folder_path: str, dry_run: bool) -> dict[str, object]:
            _ = dry_run
            raise ValueError(
                "Folder path does not exist or is not a directory: "
                f"{folder_path}. Accepted examples: /mnt/c/path/to/folder, C:\\path\\to\\folder "
                "(auto-mapped on WSL), and unquoted absolute paths."
            )

    app.dependency_overrides[get_operation_services] = _BadPathOperationServices
    client = TestClient(app)
    try:
        response = client.post("/api/ingest", json={"folder_path": '"/mnt/C/foo"', "dry_run": True})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "VALIDATION_ERROR"
    assert "Accepted examples" in payload["errors"][0]["message"]


def test_execute_mutation_logs_4xx_without_traceback(monkeypatch) -> None:
    calls: list[str] = []

    def _warn(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        _ = args, kwargs
        calls.append(f"warning:{message}")

    def _exc(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        _ = args, kwargs
        calls.append(f"exception:{message}")

    monkeypatch.setattr(main_module.LOGGER, "warning", _warn)
    monkeypatch.setattr(main_module.LOGGER, "exception", _exc)

    response = main_module._execute_mutation("ingest", lambda: (_ for _ in ()).throw(ValueError("bad input")))

    assert response.status_code == 400
    assert "warning:v2 mutation rejected" in calls
    assert not any(call.startswith("exception:") for call in calls)


def test_execute_mutation_logs_5xx_with_traceback(monkeypatch) -> None:
    calls: list[str] = []

    def _warn(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        _ = args, kwargs
        calls.append(f"warning:{message}")

    def _exc(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        _ = args, kwargs
        calls.append(f"exception:{message}")

    monkeypatch.setattr(main_module.LOGGER, "warning", _warn)
    monkeypatch.setattr(main_module.LOGGER, "exception", _exc)

    response = main_module._execute_mutation("ingest", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    assert response.status_code == 500
    assert "exception:v2 mutation failed" in calls
    assert not any(call.startswith("warning:") for call in calls)


def test_post_plan_uses_canonical_api_base() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post("/api/plan", json={"folder_path": "/dataset", "strict_metadata": True})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["data"]["result"]
    assert payload["operation"] == "PLAN"
    assert payload["strict_metadata"] is True


def test_post_apply_uses_canonical_api_base() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/apply",
            json={"run_id": "11111111-1111-1111-1111-111111111111", "collision_mode": "rename"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["data"]["result"]["operation"] == "APPLY"


def test_post_apply_rejects_invalid_collision_mode() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/apply",
            json={"run_id": "11111111-1111-1111-1111-111111111111", "collision_mode": "bad"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert response.json()["errors"][0]["code"] == "VALIDATION_ERROR"


def test_post_apply_rejects_invalid_run_id() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/apply",
            json={"run_id": "not-a-uuid", "collision_mode": "rename"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert response.json()["errors"][0]["code"] == "VALIDATION_ERROR"


def test_post_canonical_recompute_uses_canonical_api_base() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/canonical/recompute",
            json={"policy_name": "FIRST_SEEN", "dry_run": True, "preferred_roots": ["/a"]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["data"]["result"]
    assert payload["operation"] == "CANONICAL_RECOMPUTE"
    assert payload["mode"] == "DRY_RUN"


def test_get_operations_catalog_uses_canonical_api_base() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.get("/api/operations/catalog")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["ok"] is True
    items = response.json()["data"]["result"]["items"]
    assert len(items) == 2
    assert items[0]["operation_id"] == "ingest"


def test_canonical_service_error_returns_structured_400() -> None:
    class _BadReadServices(_FakeReadServices):
        def dashboard_summary(self) -> dict[str, object]:
            raise ValueError("bad input")

    app.dependency_overrides[get_read_services] = _BadReadServices
    client = TestClient(app)
    try:
        response = client.get("/api/dashboard-summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert response.json()["errors"][0]["code"] == "VALIDATION_ERROR"


def test_post_run_endpoint_returns_bad_request_for_invalid_folder() -> None:
    """POST /api/run should return 400 for invalid folder paths."""
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/run",
            json={
                "folder_path": "/missing",
                "policy_name": "FIRST_SEEN",
                "dry_run": False,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "does not exist" in response.json()["errors"][0]["message"]


def test_post_tag_enrichment_endpoint_returns_summary() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/tag-enrichment",
            json={"all": True, "batch_size": 5, "source": "system"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["data"]["result"]
    assert payload["scope"] == "ALL"
    assert payload["number_of_items_processed"] == 2
    assert payload["operation_run_id"]


def test_post_tag_enrichment_endpoint_validation_error() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/tag-enrichment",
            json={"all": True, "canonical_id": "11111111-1111-1111-1111-111111111111"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "exactly one" in response.json()["errors"][0]["message"].lower()


def test_post_tag_enrichment_endpoint_internal_error() -> None:
    class _BadOperationServices(_FakeOperationServices):
        def tag_enrichment(self, *, run_all: bool, canonical_id: str | None, batch_size: int, source: str) -> dict[str, object]:
            _ = run_all, canonical_id, batch_size, source
            raise RuntimeError("pipeline exploded")

    app.dependency_overrides[get_operation_services] = _BadOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/tag-enrichment",
            json={"all": True},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert "pipeline exploded" in response.json()["errors"][0]["message"]


def test_post_db_reset_dry_run_returns_envelope() -> None:
    app.dependency_overrides[get_admin_services] = _FakeAdminServices
    client = TestClient(app)
    try:
        response = client.post("/api/admin/db-reset", json={"dry_run": True})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["result"]["dry_run"] is True
    assert payload["data"]["result"]["affected_tables"] == ["media_file", "file_instances"]


def test_post_db_reset_requires_correct_challenge() -> None:
    app.dependency_overrides[get_admin_services] = _FakeAdminServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/admin/db-reset",
            json={"dry_run": False, "challenge_word": "wrong"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False


def test_post_db_reset_env_forbidden_returns_403() -> None:
    class _ForbiddenAdminServices:
        def db_reset(self, *, dry_run: bool, challenge_word: str | None) -> dict[str, object]:
            _ = dry_run, challenge_word
            raise ServiceLayerException(code="FORBIDDEN_ENV", message="forbidden", http_status=403)

    app.dependency_overrides[get_admin_services] = _ForbiddenAdminServices
    client = TestClient(app)
    try:
        response = client.post("/api/admin/db-reset", json={"dry_run": True})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403
    payload = response.json()
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "FORBIDDEN_ENV"


def test_main_entrypoint_starts_uvicorn(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_run(app_path: str, *, host: str, port: int, reload: bool) -> None:
        captured.update({"app_path": app_path, "host": host, "port": port, "reload": reload})

    monkeypatch.setenv("MEDIA_MANAGER_API_HOST", "0.0.0.0")
    monkeypatch.setenv("MEDIA_MANAGER_API_PORT", "8123")
    monkeypatch.setenv("MEDIA_MANAGER_API_RELOAD", "true")
    monkeypatch.setattr("uvicorn.run", _fake_run)

    main_module.main()

    assert captured == {
        "app_path": "operator_console.main:app",
        "host": "0.0.0.0",
        "port": 8123,
        "reload": True,
    }
