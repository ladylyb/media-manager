"""Smoke tests for the Operator Console FastAPI application."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient

from media_manager.app.core.errors import PolicySettingsVersionConflictError
import operator_console.main as main_module
from operator_console.main import (
    app,
    get_operator_console_service,
    get_policy_settings_service,
    get_operator_run_trigger_service,
    get_tag_enrichment_session_factory,
)


class _FakeService:
    """Simple fake read service for endpoint dependency overrides."""

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

    def get_canonical_gallery(self, page: int = 1, limit: int = 30) -> _FakePayload:
        if page > 10:
            return _FakePayload(
                {
                    "total_count": 2,
                    "page": page,
                    "total_pages": 1,
                    "items": [],
                }
            )
        return _FakePayload(
            {
                "total_count": 2,
                "page": page,
                "total_pages": 1,
                "items": [
                    {
                        "id": "33333333-0000-0000-0000-000000000001",
                        "filename": "canon-a.jpg",
                        "file_type": "image",
                        "media_url": "/media/33333333-0000-0000-0000-000000000001",
                    },
                    {
                        "id": "33333333-0000-0000-0000-000000000002",
                        "filename": "canon-b.mov",
                        "file_type": "video",
                        "media_url": "/media/33333333-0000-0000-0000-000000000002",
                    },
                ],
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
        return _FakeRunTriggerResult(
            {
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


def test_dashboard_route_renders_template() -> None:
    """GET / should render the dashboard template through the base layout."""
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "Run Trigger" in response.text
    assert "Folder Path" in response.text
    assert "Execute" in response.text
    assert "Total Files" in response.text
    assert "Performance Metrics" in response.text
    assert "Media Manager Operator Console" in response.text
    assert "Dashboard</a>" in response.text
    assert "Runs</a>" in response.text
    assert "Duplicates</a>" in response.text
    assert "Policy</a>" in response.text
    assert "https://cdn.tailwindcss.com" in response.text


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
        "total_pages": 1,
        "items": [
            {
                "id": "33333333-0000-0000-0000-000000000001",
                "filename": "canon-a.jpg",
                "file_type": "image",
                "media_url": "/media/33333333-0000-0000-0000-000000000001",
            },
            {
                "id": "33333333-0000-0000-0000-000000000002",
                "filename": "canon-b.mov",
                "file_type": "video",
                "media_url": "/media/33333333-0000-0000-0000-000000000002",
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
    assert payload["run_id"] == "33333333-3333-3333-3333-333333333333"
    assert payload["duplicates_found"] == 2
    assert payload["canonical_changes"] == 1
    assert payload["summary_metrics"]["policy_name"] == "PREFER_ROOT"
    assert payload["summary_metrics"]["dry_run"] is True
    assert payload["summary_metrics"]["ingest"]["files_scanned"] == 12


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
