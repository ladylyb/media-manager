"""Smoke tests for the Operator Console FastAPI application."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient

from media_manager.app.core.errors import PolicySettingsVersionConflictError
from media_manager.app.service_layer.errors import ServiceLayerException
import operator_console.main as main_module
from operator_console.main import (
    app,
    get_admin_services,
    get_ingest_service,
    get_operation_services,
    get_operator_console_service,
    get_policy_settings_service,
    get_read_services,
    get_operator_run_trigger_service,
    get_tag_enrichment_session_factory,
)


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
            raise PolicySettingsVersionConflictError("Policy settings version conflict: expected 7, got stale.")
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
    def status(self) -> dict[str, object]:
        return {"active_phase": "phase13"}

    def dashboard_summary(self) -> dict[str, object]:
        return {"total_files": 10}

    def latest_metrics(self) -> dict[str, object]:
        return {"ingest_time_ms": 12.5}

    def runs(self, *, limit: int) -> list[dict[str, object]]:
        _ = limit
        return [{"run_id": "abc"}]

    def canonical(self, **kwargs) -> dict[str, object]:  # type: ignore[no-untyped-def]
        _ = kwargs
        return {"total_count": 0, "page": 1, "limit": 30, "total_pages": 0, "items": []}

    def canonical_tags(self, *, q: str | None, limit: int) -> dict[str, object]:
        _ = q, limit
        return {"items": ["city"]}

    def duplicates(self) -> dict[str, object]:
        return {"groups": []}

    def media_file_by_hash(self, *, hash_prefix: str, page: int, limit: int) -> dict[str, object]:
        _ = hash_prefix, page, limit
        return {"total_count": 0, "page": 1, "limit": 30, "total_pages": 0, "items": []}

    def media_file_history(self, *, path: str, page: int, limit: int) -> dict[str, object]:
        _ = path, page, limit
        return {"total_count": 0, "page": 1, "limit": 30, "total_pages": 0, "items": []}

    def media_file_by_status(self, *, status: str, page: int, limit: int) -> dict[str, object]:
        _ = status, page, limit
        return {"total_count": 0, "page": 1, "limit": 30, "total_pages": 0, "items": []}

    def media_file_reappearances(self, *, path: str, page: int, limit: int) -> dict[str, object]:
        _ = path, page, limit
        return {"total_count": 0, "page": 1, "limit": 30, "total_pages": 0, "items": []}

    def media_file_analytics(self) -> dict[str, object]:
        return {"totals": {"files_tracked": 0}, "window": {"mode": "all_time"}}

    def ledger_hash_audit(self, *, root_path: str | None, sample_limit: int) -> dict[str, object]:
        _ = root_path, sample_limit
        return {
            "total_files": 0,
            "missing_hash": 0,
            "hash_mismatches": 0,
            "deleted_rows_skipped": 0,
            "sample_missing_hash_paths": [],
            "sample_mismatch_paths": [],
        }

    def media_file_dry_run_audit(self, *, start: str | None, end: str | None, limit: int) -> dict[str, object]:
        _ = start, end, limit
        return {"coverage": "BEST_EFFORT", "method": "x", "window": {"start": None, "end": None}, "candidates": [], "limitations": []}


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
        _ = policy_name
        return {"mode": "VALIDATION_ONLY" if dry_run else "EXECUTION", "run_id": "r1", "folder_path": folder_path}

    def operations_catalog(self) -> dict[str, object]:
        return {
            "items": [
                {"operation_id": "ingest", "supports_dry_run": True},
                {"operation_id": "plan", "supports_dry_run": False},
            ]
        }

    def policy_get(self) -> dict[str, object]:
        return {"canonical_priority": {"selected_policy": "FIRST_SEEN"}, "metadata": {"version": 1}}

    def policy_set(
        self,
        *,
        selected_policy: str,
        preferred_roots: tuple[str, ...],
        recanonicalization_enabled: bool,
        version: int,
    ) -> dict[str, object]:
        _ = preferred_roots, recanonicalization_enabled
        if version < 0:
            raise ValueError("invalid version")
        return {"canonical_priority": {"selected_policy": selected_policy}, "metadata": {"version": version + 1}}

    def tag_enrichment(self, *, run_all: bool, canonical_id: str | None, batch_size: int, source: str) -> dict[str, object]:
        _ = run_all, canonical_id, batch_size, source
        return {"scope": "ALL", "number_of_items_processed": 2}

    def media_file_validate(self, *, folder_path: str) -> dict[str, object]:
        return {"mode": "VALIDATION_ONLY", "root_path": folder_path, "delta": {"would_insert": 0}}


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


def test_dashboard_route_renders_template() -> None:
    """GET / should render the dashboard template through the base layout."""
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "Quick Operations" in response.text
    assert "Validate Ingest (dry-run)" in response.text
    assert "Composite Run (legacy pipeline)" in response.text
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


def test_dashboard_summary_endpoint_returns_json() -> None:
    """GET /api/dashboard-summary should return summary fields as JSON."""
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        response = client.get("/api/dashboard-summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "total_files": 10,
        "total_images": 6,
        "total_videos": 4,
        "duplicate_groups": 2,
        "canonical_files": 8,
        "total_runs": 3,
    }


def test_latest_metrics_endpoint_returns_json() -> None:
    """GET /api/latest-metrics should return metrics fields as JSON."""
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        response = client.get("/api/latest-metrics")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
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
    assert "Files Processed" in response.text
    assert "Duplicates Found" in response.text
    assert "Runtime (ms)" in response.text
    assert "Regression" in response.text


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
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        response = client.get("/api/runs")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == [
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


def test_v2_status_endpoint_returns_cli_envelope() -> None:
    app.dependency_overrides[get_read_services] = _FakeReadServices
    client = TestClient(app)
    try:
        response = client.get("/api/v2/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["data"]["active_phase"] == "phase13"


def test_v2_read_endpoints_return_cli_envelopes() -> None:
    app.dependency_overrides[get_read_services] = _FakeReadServices
    client = TestClient(app)
    try:
        summary = client.get("/api/v2/dashboard-summary")
        metrics = client.get("/api/v2/latest-metrics")
        runs = client.get("/api/v2/runs?limit=25")
    finally:
        app.dependency_overrides.clear()

    assert summary.status_code == 200
    assert metrics.status_code == 200
    assert runs.status_code == 200
    assert summary.json()["data"]["result"]["total_files"] == 10
    assert metrics.json()["data"]["result"]["ingest_time_ms"] == 12.5
    assert runs.json()["data"]["result"][0]["run_id"] == "abc"


def test_v2_canonical_duplicates_and_ledger_endpoints_return_service_envelopes() -> None:
    app.dependency_overrides[get_read_services] = _FakeReadServices
    client = TestClient(app)
    try:
        canonical = client.get("/api/v2/canonical?page=1&limit=30")
        tags = client.get("/api/v2/canonical/tags?q=ci&limit=5")
        duplicates = client.get("/api/v2/duplicates")
        by_hash = client.get("/api/v2/media-file/by-hash?hash_prefix=abc&page=1&limit=30")
        analytics = client.get("/api/v2/media-file/analytics")
        audit = client.get("/api/v2/ledger/hash-audit?sample_limit=20")
    finally:
        app.dependency_overrides.clear()

    assert canonical.status_code == 200
    assert tags.status_code == 200
    assert duplicates.status_code == 200
    assert by_hash.status_code == 200
    assert analytics.status_code == 200
    assert audit.status_code == 200


def test_media_file_by_hash_endpoint_returns_paginated_shape() -> None:
    fake = _FakeService()
    app.dependency_overrides[get_operator_console_service] = lambda: fake
    client = TestClient(app)
    try:
        response = client.get("/api/media-file/by-hash?hash_prefix=abcd&page=2&limit=10")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"] == 2
    assert payload["limit"] == 10
    assert payload["items"][0]["status"] == "INGESTED"
    assert fake.last_media_file_call == {"mode": "hash", "hash_prefix": "abcd", "page": 2, "limit": 10}


def test_media_file_history_endpoint_returns_paginated_shape() -> None:
    fake = _FakeService()
    app.dependency_overrides[get_operator_console_service] = lambda: fake
    client = TestClient(app)
    try:
        response = client.get("/api/media-file/history?path=/ledger/a.jpg&page=1&limit=30")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 1
    assert fake.last_media_file_call == {"mode": "history", "path": "/ledger/a.jpg", "page": 1, "limit": 30}


def test_media_file_by_status_endpoint_returns_paginated_shape() -> None:
    fake = _FakeService()
    app.dependency_overrides[get_operator_console_service] = lambda: fake
    client = TestClient(app)
    try:
        response = client.get("/api/media-file/by-status?status=processed&page=1&limit=30")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["hash_sha256"] == "a" * 64
    assert fake.last_media_file_call == {"mode": "status", "status": "PROCESSED", "page": 1, "limit": 30}


def test_media_file_reappearances_endpoint_returns_paginated_shape() -> None:
    fake = _FakeService()
    app.dependency_overrides[get_operator_console_service] = lambda: fake
    client = TestClient(app)
    try:
        response = client.get("/api/media-file/reappearances?path=/ledger/a.jpg&page=1&limit=5")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["current_path"] == "/ledger/a.jpg"
    assert fake.last_media_file_call == {"mode": "reappearances", "path": "/ledger/a.jpg", "page": 1, "limit": 5}


def test_media_file_analytics_endpoint_returns_expected_shape() -> None:
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        response = client.get("/api/media-file/analytics")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["totals"]["files_tracked"] == 11
    assert payload["totals"]["duplicate_hash_groups"] == 2
    assert payload["by_status"]["INGESTED"] == 6
    assert payload["window"]["mode"] == "all_time"


def test_media_file_hash_audit_endpoint_returns_expected_shape() -> None:
    fake = _FakeService()
    app.dependency_overrides[get_operator_console_service] = lambda: fake
    client = TestClient(app)
    try:
        response = client.get("/api/v1/ledger/hash-audit?root_path=/ledger&sample_limit=25")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_files"] == 10
    assert payload["missing_hash"] == 2
    assert payload["hash_mismatches"] == 1
    assert fake.last_media_file_call == {"mode": "hash_audit", "root_path": "/ledger", "sample_limit": 25}


def test_media_file_hash_audit_alias_endpoint_returns_expected_shape() -> None:
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        response = client.get("/api/media-file/hash-audit")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {
        "total_files",
        "missing_hash",
        "hash_mismatches",
        "deleted_rows_skipped",
        "sample_missing_hash_paths",
        "sample_mismatch_paths",
    }


def test_media_file_hash_audit_endpoint_rejects_invalid_params() -> None:
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        bad_sample = client.get("/api/v1/ledger/hash-audit?sample_limit=500")
        bad_root = client.get("/api/v1/ledger/hash-audit?root_path= ")
    finally:
        app.dependency_overrides.clear()

    assert bad_sample.status_code == 400
    assert "sample_limit" in bad_sample.json()["detail"]
    assert bad_root.status_code == 400
    assert "root_path" in bad_root.json()["detail"]


def test_media_file_dry_run_audit_endpoint_returns_expected_shape() -> None:
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        response = client.get("/api/media-file/dry-run-audit?limit=10")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["coverage"] == "BEST_EFFORT"
    assert payload["candidates"][0]["confidence"] == "MEDIUM"


def test_media_file_dry_run_audit_endpoint_rejects_invalid_limit() -> None:
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        response = client.get("/api/media-file/dry-run-audit?limit=999")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "limit" in response.json()["detail"]


def test_post_media_file_validate_returns_validation_payload(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir(parents=True, exist_ok=True)
    app.dependency_overrides[get_ingest_service] = _FakeIngestService
    client = TestClient(app)
    try:
        response = client.post(
            "/api/media-file/validate",
            json={"folder_path": str(dataset), "policy_name": "FIRST_SEEN"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "VALIDATION_ONLY"
    assert payload["delta"]["would_insert"] == 1


def test_post_media_file_validate_rejects_invalid_folder(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    app.dependency_overrides[get_ingest_service] = _FakeIngestService
    client = TestClient(app)
    try:
        response = client.post(
            "/api/media-file/validate",
            json={"folder_path": str(missing), "policy_name": None},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]


def test_media_file_endpoints_reject_invalid_inputs() -> None:
    app.dependency_overrides[get_operator_console_service] = _FakeService
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
    assert "hash_prefix" in empty_hash.json()["detail"]
    assert empty_path.status_code == 400
    assert "path" in empty_path.json()["detail"]
    assert bad_status.status_code == 400
    assert "status" in bad_status.json()["detail"]
    assert bad_page.status_code == 400
    assert "page" in bad_page.json()["detail"]
    assert bad_limit.status_code == 400
    assert "limit" in bad_limit.json()["detail"]


def test_api_canonical_returns_paginated_shape() -> None:
    """GET /api/canonical should return paginated canonical media payload."""
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        response = client.get("/api/canonical?page=1&limit=30")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
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
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        response = client.get("/api/canonical?page=99&limit=30")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"] == 99
    assert payload["items"] == []


def test_api_canonical_accepts_discovery_query_params() -> None:
    """GET /api/canonical should accept filtering and sorting query params."""
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        response = client.get(
            "/api/canonical?page=1&limit=30&tags=city,travel&sort_by=tag_name&sort_order=asc&source=ai&min_confidence=0.5"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"] == 1
    assert payload["items"][0]["matched_tags"] == ["city", "travel"]


def test_api_canonical_applies_default_sort_order_for_tag_name() -> None:
    fake = _FakeService()
    app.dependency_overrides[get_operator_console_service] = lambda: fake
    client = TestClient(app)
    try:
        response = client.get("/api/canonical?sort_by=tag_name")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake.last_gallery_call is not None
    assert fake.last_gallery_call["sort_order"] == "asc"


def test_api_canonical_rejects_invalid_sort_by() -> None:
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        response = client.get("/api/canonical?sort_by=unsupported")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "sort_by" in response.json()["detail"]


def test_api_canonical_rejects_invalid_source_and_confidence() -> None:
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        bad_source = client.get("/api/canonical?source=bad")
        bad_conf = client.get("/api/canonical?min_confidence=3.0")
    finally:
        app.dependency_overrides.clear()

    assert bad_source.status_code == 400
    assert "source" in bad_source.json()["detail"]
    assert bad_conf.status_code == 400
    assert "min_confidence" in bad_conf.json()["detail"]


def test_api_canonical_tags_returns_suggestions() -> None:
    fake = _FakeService()
    app.dependency_overrides[get_operator_console_service] = lambda: fake
    client = TestClient(app)
    try:
        response = client.get("/api/canonical/tags?q=ci&limit=2")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"items": ["city", "city night"]}
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
    app.dependency_overrides[get_operator_console_service] = _FakeService
    client = TestClient(app)
    try:
        response = client.get("/api/duplicates")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
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
    assert "Dry-Run Preview" in response.text


def test_get_policy_endpoint_returns_structured_json() -> None:
    """GET /api/policy should return structured policy payload."""
    app.dependency_overrides[get_policy_settings_service] = _FakePolicyService
    client = TestClient(app)
    try:
        response = client.get("/api/policy")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["canonical_priority"]["selected_policy"] == "PREFER_ROOT"
    assert payload["canonical_priority"]["preferred_roots"] == ["/archive", "/media"]
    assert payload["recanonicalization"]["enabled"] is True
    assert payload["metadata"]["version"] == 7


def test_post_policy_endpoint_updates_settings() -> None:
    """POST /api/policy should persist settings and return confirmation payload."""
    app.dependency_overrides[get_policy_settings_service] = _FakePolicyService
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
    payload = response.json()
    assert payload["message"] == "Policy settings saved."
    assert payload["canonical_priority"]["preferred_roots"] == ["/a", "/b"]
    assert payload["metadata"]["version"] == 8


def test_post_policy_endpoint_returns_version_conflict() -> None:
    """POST /api/policy should return 409 on stale version updates."""
    app.dependency_overrides[get_policy_settings_service] = _FakePolicyService
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
    assert "version conflict" in response.json()["detail"].lower()


def test_post_run_endpoint_returns_trigger_summary() -> None:
    """POST /api/run should return run trigger result payload."""
    app.dependency_overrides[get_operator_run_trigger_service] = _FakeRunTriggerService
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
    payload = response.json()
    assert payload["mode"] == "VALIDATION_ONLY"
    assert payload["validation_report"]["delta"]["would_update"] == 4
    assert payload["validation_report"]["scan"]["files_scanned"] == 12


def test_post_run_endpoint_non_dry_run_returns_execution_payload() -> None:
    app.dependency_overrides[get_operator_run_trigger_service] = _FakeRunTriggerService
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
    payload = response.json()
    assert payload["mode"] == "EXECUTION"
    assert payload["run_id"] == "33333333-3333-3333-3333-333333333333"
    assert payload["summary_metrics"]["dry_run"] is False


def test_post_run_v2_returns_service_envelope() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v2/run",
            json={
                "folder_path": "/dataset",
                "policy_name": "PREFER_ROOT",
                "dry_run": True,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["data"]["result"]["mode"] == "VALIDATION_ONLY"


def test_post_operator_run_v2_returns_service_envelope() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v2/operator-run",
            json={
                "folder_path": "/dataset",
                "policy_name": "PREFER_ROOT",
                "dry_run": True,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["data"]["result"]["mode"] == "VALIDATION_ONLY"


def test_post_operator_run_v2_parity_with_run_v2() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    payload = {"folder_path": "/dataset", "policy_name": "FIRST_SEEN", "dry_run": False}
    try:
        run_response = client.post("/api/v2/run", json=payload)
        alias_response = client.post("/api/v2/operator-run", json=payload)
    finally:
        app.dependency_overrides.clear()

    assert run_response.status_code == 200
    assert alias_response.status_code == 200
    assert run_response.json()["data"]["result"] == alias_response.json()["data"]["result"]


def test_post_ingest_v2_returns_service_envelope() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post("/api/v2/ingest", json={"folder_path": "/dataset", "dry_run": True})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["data"]["result"]["operation"] == "INGEST"


def test_post_ingest_v2_execute_returns_summary_fields() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post("/api/v2/ingest", json={"folder_path": "/dataset", "dry_run": False})
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


def test_post_plan_v2_returns_service_envelope() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post("/api/v2/plan", json={"folder_path": "/dataset", "strict_metadata": True})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["data"]["result"]
    assert payload["operation"] == "PLAN"
    assert payload["strict_metadata"] is True


def test_post_apply_v2_returns_service_envelope() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v2/apply",
            json={"run_id": "11111111-1111-1111-1111-111111111111", "collision_mode": "rename"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["data"]["result"]["operation"] == "APPLY"


def test_post_apply_v2_rejects_invalid_collision_mode() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v2/apply",
            json={"run_id": "11111111-1111-1111-1111-111111111111", "collision_mode": "bad"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert response.json()["errors"][0]["code"] == "VALIDATION_ERROR"


def test_post_apply_v2_rejects_invalid_run_id() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v2/apply",
            json={"run_id": "not-a-uuid", "collision_mode": "rename"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert response.json()["errors"][0]["code"] == "VALIDATION_ERROR"


def test_post_canonical_recompute_v2_returns_service_envelope() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v2/canonical/recompute",
            json={"policy_name": "FIRST_SEEN", "dry_run": True, "preferred_roots": ["/a"]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()["data"]["result"]
    assert payload["operation"] == "CANONICAL_RECOMPUTE"
    assert payload["mode"] == "DRY_RUN"


def test_get_operations_catalog_v2_returns_service_envelope() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.get("/api/v2/operations/catalog")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["ok"] is True
    items = response.json()["data"]["result"]["items"]
    assert len(items) == 2
    assert items[0]["operation_id"] == "ingest"


def test_post_policy_v2_returns_service_envelope() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v2/policy",
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
    assert response.json()["data"]["result"]["metadata"]["version"] == 8


def test_post_tag_enrichment_v2_returns_service_envelope() -> None:
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v2/tag-enrichment",
            json={"all": True, "batch_size": 5, "source": "system"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["data"]["result"]["number_of_items_processed"] == 2


def test_post_media_file_validate_v2_returns_service_envelope(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir(parents=True, exist_ok=True)
    app.dependency_overrides[get_operation_services] = _FakeOperationServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v2/media-file/validate",
            json={"folder_path": str(dataset), "policy_name": "FIRST_SEEN"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["data"]["result"]["mode"] == "VALIDATION_ONLY"


def test_v2_service_error_returns_structured_400() -> None:
    class _BadReadServices(_FakeReadServices):
        def dashboard_summary(self) -> dict[str, object]:
            raise ValueError("bad input")

    app.dependency_overrides[get_read_services] = _BadReadServices
    client = TestClient(app)
    try:
        response = client.get("/api/v2/dashboard-summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert response.json()["errors"][0]["code"] == "VALIDATION_ERROR"


def test_post_run_endpoint_returns_bad_request_for_invalid_folder() -> None:
    """POST /api/run should return 400 for invalid folder paths."""
    app.dependency_overrides[get_operator_run_trigger_service] = _FakeRunTriggerService
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
    assert "does not exist" in response.json()["detail"]


def test_post_tag_enrichment_endpoint_returns_summary(monkeypatch) -> None:
    class _Summary:
        def to_dict(self) -> dict[str, Any]:
            return {
                "run_id": "44444444-4444-4444-4444-444444444444",
                "timestamp": "2026-03-02T18:00:00+00:00",
                "number_of_items_processed": 2,
                "average_confidence": 0.75,
                "duration_ms": 10,
                "status": "COMPLETED",
                "failed_items": 0,
                "scope": "ALL",
            }

    def _fake_run(_session_factory, _command):  # type: ignore[no-untyped-def]
        return _Summary()

    monkeypatch.setattr(main_module, "run_tag_enrichment", _fake_run)
    app.dependency_overrides[get_tag_enrichment_session_factory] = lambda: object()
    client = TestClient(app)
    try:
        response = client.post(
            "/api/tag-enrichment",
            json={"all": True, "batch_size": 5, "source": "system"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "44444444-4444-4444-4444-444444444444"
    assert payload["number_of_items_processed"] == 2
    assert payload["scope"] == "ALL"


def test_post_tag_enrichment_endpoint_validation_error() -> None:
    app.dependency_overrides[get_tag_enrichment_session_factory] = lambda: object()
    client = TestClient(app)
    try:
        response = client.post(
            "/api/tag-enrichment",
            json={"all": True, "canonical_id": "11111111-1111-1111-1111-111111111111"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "exactly one" in response.json()["detail"].lower()


def test_post_tag_enrichment_endpoint_internal_error(monkeypatch) -> None:
    def _boom(_session_factory, _command):  # type: ignore[no-untyped-def]
        raise RuntimeError("pipeline exploded")

    monkeypatch.setattr(main_module, "run_tag_enrichment", _boom)
    app.dependency_overrides[get_tag_enrichment_session_factory] = lambda: object()
    client = TestClient(app)
    try:
        response = client.post(
            "/api/tag-enrichment",
            json={"all": True},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert "pipeline exploded" in response.json()["detail"]


def test_post_db_reset_v2_dry_run_returns_envelope() -> None:
    app.dependency_overrides[get_admin_services] = _FakeAdminServices
    client = TestClient(app)
    try:
        response = client.post("/api/v2/admin/db-reset", json={"dry_run": True})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["result"]["dry_run"] is True
    assert payload["data"]["result"]["affected_tables"] == ["media_file", "file_instances"]


def test_post_db_reset_v2_requires_correct_challenge() -> None:
    app.dependency_overrides[get_admin_services] = _FakeAdminServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v2/admin/db-reset",
            json={"dry_run": False, "challenge_word": "wrong"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False


def test_post_db_reset_alias_path_parity() -> None:
    app.dependency_overrides[get_admin_services] = _FakeAdminServices
    client = TestClient(app)
    try:
        response = client.post(
            "/api/admin/db-reset",
            json={"dry_run": False, "challenge_word": "media-manager"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["result"]["success"] is True


def test_post_db_reset_v2_env_forbidden_returns_403() -> None:
    class _ForbiddenAdminServices:
        def db_reset(self, *, dry_run: bool, challenge_word: str | None) -> dict[str, object]:
            _ = dry_run, challenge_word
            raise ServiceLayerException(code="FORBIDDEN_ENV", message="forbidden", http_status=403)

    app.dependency_overrides[get_admin_services] = _ForbiddenAdminServices
    client = TestClient(app)
    try:
        response = client.post("/api/v2/admin/db-reset", json={"dry_run": True})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403
    payload = response.json()
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "FORBIDDEN_ENV"
