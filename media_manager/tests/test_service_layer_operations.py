from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

import media_manager.app.service_layer.operations as operations_module
from media_manager.app.persistence.ingest import IngestSummary
from media_manager.app.service_layer.operations import OperationServices


@dataclass
class _FakeCache:
    invalidations: list[tuple[str, ...]]

    def invalidate(self, *keys: str) -> None:
        self.invalidations.append(tuple(keys))


class _FakeOperationRunService:
    def __init__(self, _session_factory) -> None:
        self._id = uuid4()

    def start(self, *, operation_type, context, linked_run_id=None):  # type: ignore[no-untyped-def]
        _ = operation_type, context, linked_run_id
        return SimpleNamespace(operation_run_id=str(self._id))

    def complete(self, operation_run_id):  # type: ignore[no-untyped-def]
        _ = operation_run_id
        return None

    def fail(self, operation_run_id, *, error_message):  # type: ignore[no-untyped-def]
        _ = operation_run_id, error_message
        return None

    def link_run(self, operation_run_id, *, linked_run_id):  # type: ignore[no-untyped-def]
        _ = operation_run_id, linked_run_id
        return None

    def list_history(self, *, limit, operation_type=None, status=None):  # type: ignore[no-untyped-def]
        _ = limit, operation_type, status
        return []


def _install_fake_operation_run_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(operations_module, "OperationRunService", _FakeOperationRunService)


def test_ingest_dry_run_is_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()

    class _FakeIngestService:
        def __init__(self, _session_factory) -> None:
            pass

        def validate_path(self, _root: Path) -> SimpleNamespace:
            return SimpleNamespace(to_dict=lambda: {"mode": "VALIDATION_ONLY", "delta": {"would_insert": 1}})

    monkeypatch.setattr(operations_module, "IngestService", _FakeIngestService)
    _install_fake_operation_run_service(monkeypatch)
    cache = _FakeCache(invalidations=[])
    services = OperationServices(session_factory=object(), cache=cache)  # type: ignore[arg-type]

    payload = services.ingest(folder_path=str(dataset), dry_run=True)

    assert payload["mode"] == "VALIDATION_ONLY"
    assert payload["operation"] == "INGEST"
    assert cache.invalidations == []


def test_ingest_execute_invalidates_caches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()

    class _FakeIngestService:
        def __init__(self, _session_factory) -> None:
            pass

        def ingest_path(self, _root: Path) -> IngestSummary:
            return IngestSummary(
                files_scanned=3,
                new_contents=1,
                new_instances=2,
                duplicates_detected=0,
                metadata_extracted=3,
                duration_s=0.25,
            )

    monkeypatch.setattr(operations_module, "IngestService", _FakeIngestService)
    _install_fake_operation_run_service(monkeypatch)
    cache = _FakeCache(invalidations=[])
    services = OperationServices(session_factory=object(), cache=cache)  # type: ignore[arg-type]

    payload = services.ingest(folder_path=str(dataset), dry_run=False)

    assert payload["mode"] == "EXECUTION"
    assert payload["summary"]["files_scanned"] == 3
    assert payload["summary"]["new_contents"] == 1
    assert payload["summary"]["new_instances"] == 2
    assert payload["summary"]["duplicates_detected"] == 0
    assert payload["summary"]["metadata_extracted"] == 3
    assert payload["summary"]["duration_s"] == 0.25
    assert any(
        {"dashboard_summary", "latest_metrics", "status"}.issubset(set(invalidated))
        for invalidated in cache.invalidations
    )


def test_plan_returns_run_and_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "a.jpg").write_bytes(b"x")
    run_id = uuid4()

    class _FakeIngestService:
        def __init__(self, _session_factory) -> None:
            pass

        def collect_files(self, root: Path) -> list[Path]:
            return [root / "a.jpg"]

        def ingest_paths(self, _files: list[Path], *, authoritative_root: Path | None = None):
            _ = authoritative_root
            return SimpleNamespace()

    class _FakeRunService:
        def __init__(self, _session_factory) -> None:
            pass

        def create_run(self):
            return SimpleNamespace(id=run_id)

    class _FakePlanner:
        def __init__(self, _session_factory) -> None:
            pass

        def plan_run(self, _run_id, _files, ingest_if_needed=False, strict_missing_metadata=False):
            _ = ingest_if_needed, strict_missing_metadata
            return SimpleNamespace(to_dict=lambda: {"scanned_count": 1, "move_actions": 1, "noop_actions": 0, "duplicate_actions": 0})

    monkeypatch.setattr(operations_module, "IngestService", _FakeIngestService)
    monkeypatch.setattr(operations_module, "RunService", _FakeRunService)
    monkeypatch.setattr(operations_module, "PlanningService", _FakePlanner)
    _install_fake_operation_run_service(monkeypatch)

    cache = _FakeCache(invalidations=[])
    services = OperationServices(session_factory=object(), cache=cache)  # type: ignore[arg-type]

    payload = services.plan(folder_path=str(dataset), strict_metadata=False)

    assert payload["operation"] == "PLAN"
    assert payload["run_id"] == str(run_id)
    assert payload["summary"]["scanned_count"] == 1


def test_apply_rejects_bad_collision_mode() -> None:
    cache = _FakeCache(invalidations=[])
    services = OperationServices(session_factory=object(), cache=cache)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="collision_mode must be one of"):
        services.apply(run_id=str(uuid4()), collision_mode="oops")


def test_canonical_recompute_apply_invalidates_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakePolicy:
        name = "FIRST_SEEN"
        version = "v1"

    def _fake_build_policy(_name: str):
        return _FakePolicy()

    def _fake_recompute(_session_factory, *, policy, context, mode):  # type: ignore[no-untyped-def]
        _ = policy, context, mode
        return SimpleNamespace(
            run_id=uuid4(),
            status="COMPLETED",
            scanned_count=2,
            changed_count=1,
            applied_count=1,
            failed_count=0,
            changed_content_ids=("a",),
            failed_content_ids=(),
        )

    monkeypatch.setattr(operations_module, "build_canonical_policy", _fake_build_policy)
    monkeypatch.setattr(operations_module, "recompute_canonical_assignments", _fake_recompute)
    _install_fake_operation_run_service(monkeypatch)

    cache = _FakeCache(invalidations=[])
    services = OperationServices(session_factory=object(), cache=cache)  # type: ignore[arg-type]

    payload = services.canonical_recompute(policy_name="FIRST_SEEN", dry_run=False, preferred_roots=())

    assert payload["operation"] == "CANONICAL_RECOMPUTE"
    assert payload["mode"] == "APPLY"
    assert any({"latest_metrics", "status"}.issubset(set(invalidated)) for invalidated in cache.invalidations)


def test_operations_catalog_contains_expected_items() -> None:
    cache = _FakeCache(invalidations=[])
    services = OperationServices(session_factory=object(), cache=cache)  # type: ignore[arg-type]

    catalog = services.operations_catalog()

    assert "items" in catalog
    ids = [item["operation_id"] for item in catalog["items"]]
    assert ids == ["ingest", "plan", "apply", "canonical_recompute", "tag_enrichment", "operator_run"]
