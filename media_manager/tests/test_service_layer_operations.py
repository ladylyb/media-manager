from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

import media_manager.app.service_layer.operations as operations_module
from media_manager.app.persistence.apply import ApplySummary
from media_manager.app.persistence.canonicalization import RecomputeMode, RecomputeSummary
from media_manager.app.persistence.ingest import IngestSummary
from media_manager.app.persistence.planner import PlanningSummary
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

        def ingest_paths(self, _files: list[Path], *, authoritative_root: Path | None = None, **kwargs):
            _ = authoritative_root, kwargs
            return SimpleNamespace()

        def classify_paths(self, _files: list[Path], **kwargs):
            _ = kwargs
            return None

    class _FakeRunService:
        def __init__(self, _session_factory) -> None:
            pass

        def create_run(self, **kwargs):
            _ = kwargs
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
    assert catalog["items"][-1]["label"] == "Composite Run (Compatibility)"


def test_run_dry_run_is_validation_only_and_skips_mutators(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    target = dataset / "a.jpg"
    target.write_bytes(b"x")

    class _FakeIngestService:
        def __init__(self, _session_factory) -> None:
            pass

        @staticmethod
        def collect_files(root: Path) -> list[Path]:
            assert root == dataset
            return [target]

        def validate_paths(self, files: list[Path], *, authoritative_root: Path | None = None):
            assert files == [target]
            assert authoritative_root == dataset
            return SimpleNamespace(to_dict=lambda: {"mode": "VALIDATION_ONLY", "scan": {"files_scanned": 1}})

    class _ForbiddenRunService:
        def __init__(self, _session_factory) -> None:
            raise AssertionError("RunService must not be constructed for dry-run validation mode")

    class _ForbiddenPlanner:
        def __init__(self, _session_factory) -> None:
            raise AssertionError("PlanningService must not be constructed for dry-run validation mode")

    class _ForbiddenApplyService:
        def __init__(self, _session_factory) -> None:
            raise AssertionError("ApplyService must not be constructed for dry-run validation mode")

    monkeypatch.setattr(operations_module, "IngestService", _FakeIngestService)
    monkeypatch.setattr(operations_module, "RunService", _ForbiddenRunService)
    monkeypatch.setattr(operations_module, "PlanningService", _ForbiddenPlanner)
    monkeypatch.setattr(operations_module, "ApplyService", _ForbiddenApplyService)
    _install_fake_operation_run_service(monkeypatch)

    services = OperationServices(session_factory=object(), cache=_FakeCache(invalidations=[]))  # type: ignore[arg-type]
    payload = services.run(folder_path=str(dataset), policy_name="FIRST_SEEN", dry_run=True)

    assert payload["mode"] == "VALIDATION_ONLY"
    assert payload["validation_report"]["scan"]["files_scanned"] == 1


def test_run_execution_flows_through_service_layer_and_links_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    target = dataset / "a.jpg"
    target.write_bytes(b"x")
    run_id = uuid4()
    linked_ids: list[UUID] = []

    class _TrackingOperationRunService(_FakeOperationRunService):
        def link_run(self, operation_run_id, *, linked_run_id):  # type: ignore[no-untyped-def]
            _ = operation_run_id
            linked_ids.append(linked_run_id)

    class _FakeIngestService:
        def __init__(self, _session_factory) -> None:
            pass

        @staticmethod
        def collect_files(root: Path) -> list[Path]:
            assert root == dataset
            return [target]

        def ingest_paths(self, files: list[Path], **kwargs) -> IngestSummary:
            assert files == [target]
            _ = kwargs
            return IngestSummary(1, 1, 1, 0, 1, 0.1)

        def classify_paths(self, files: list[Path], **kwargs) -> None:
            assert files == [target]
            _ = kwargs

    class _FakeRunService:
        def __init__(self, _session_factory) -> None:
            pass

        def create_run(self, **kwargs):
            _ = kwargs
            return SimpleNamespace(id=run_id)

    class _FakePlanner:
        def __init__(self, _session_factory) -> None:
            pass

        def plan_run(self, planned_run_id, files, ingest_if_needed=False):
            assert planned_run_id == run_id
            assert files == [target]
            assert ingest_if_needed is False
            return PlanningSummary(run_id, 1, 1, 0, 1, 0, 0)

    class _FakeApplyService:
        def __init__(self, _session_factory) -> None:
            pass

        def apply_run(self, applied_run_id) -> ApplySummary:
            assert applied_run_id == run_id
            return ApplySummary(
                applied_count=1,
                skipped_count=0,
                duplicates_count=0,
                noop_count=0,
                errors_count=0,
                moves_count=1,
            )

    def _fake_build_policy(name: str):
        return SimpleNamespace(name=name, version="v1")

    def _fake_recompute(_session_factory, *, policy, context, mode):  # type: ignore[no-untyped-def]
        assert policy.name == "PREFER_ROOT"
        assert context.preferred_roots == ()
        assert mode == RecomputeMode.APPLY
        return RecomputeSummary(
            run_id=uuid4(),
            scanned_count=1,
            changed_count=2,
            failed_count=0,
            applied_count=2,
            status="COMPLETED",
            changed_content_ids=(),
            failed_content_ids=(),
        )

    monkeypatch.setattr(operations_module, "OperationRunService", _TrackingOperationRunService)
    monkeypatch.setattr(operations_module, "IngestService", _FakeIngestService)
    monkeypatch.setattr(operations_module, "RunService", _FakeRunService)
    monkeypatch.setattr(operations_module, "PlanningService", _FakePlanner)
    monkeypatch.setattr(operations_module, "ApplyService", _FakeApplyService)
    monkeypatch.setattr(operations_module, "build_canonical_policy", _fake_build_policy)
    monkeypatch.setattr(operations_module, "recompute_canonical_assignments", _fake_recompute)

    cache = _FakeCache(invalidations=[])
    services = OperationServices(session_factory=object(), cache=cache)  # type: ignore[arg-type]
    payload = services.run(folder_path=str(dataset), policy_name="PREFER_ROOT", dry_run=False)

    assert payload["mode"] == "EXECUTION"
    assert payload["run_id"] == str(run_id)
    assert payload["duplicates_found"] == 0
    assert payload["canonical_changes"] == 2
    assert payload["summary_metrics"]["policy_name"] == "PREFER_ROOT"
    assert payload["summary_metrics"]["apply"]["moves_count"] == 1
    assert linked_ids == [run_id]
    assert any(
        {"dashboard_summary", "latest_metrics", "status"}.issubset(set(invalidated))
        for invalidated in cache.invalidations
    )


def test_ingest_accepts_wrapped_quotes_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()

    class _FakeIngestService:
        def __init__(self, _session_factory) -> None:
            pass

        def validate_path(self, root: Path) -> SimpleNamespace:
            assert root == dataset
            return SimpleNamespace(to_dict=lambda: {"mode": "VALIDATION_ONLY", "delta": {"would_insert": 0}})

    monkeypatch.setattr(operations_module, "IngestService", _FakeIngestService)
    _install_fake_operation_run_service(monkeypatch)

    services = OperationServices(session_factory=object(), cache=_FakeCache(invalidations=[]))  # type: ignore[arg-type]
    payload = services.ingest(folder_path=f'"{dataset}"', dry_run=True)
    assert payload["mode"] == "VALIDATION_ONLY"


def test_ingest_accepts_mnt_uppercase_drive_path(monkeypatch: pytest.MonkeyPatch) -> None:
    canonical = Path("/mnt/c/Users/micro/Documents/Media-Manager-Test")
    uppercase = Path("/mnt/C/Users/micro/Documents/Media-Manager-Test")

    def _fake_exists(self: Path) -> bool:
        return str(self) == str(canonical)

    def _fake_is_dir(self: Path) -> bool:
        return str(self) == str(canonical)

    class _FakeIngestService:
        def __init__(self, _session_factory) -> None:
            pass

        def validate_path(self, root: Path) -> SimpleNamespace:
            assert root == canonical
            return SimpleNamespace(to_dict=lambda: {"mode": "VALIDATION_ONLY", "delta": {"would_insert": 0}})

    monkeypatch.setattr(Path, "exists", _fake_exists)
    monkeypatch.setattr(Path, "is_dir", _fake_is_dir)
    monkeypatch.setattr(operations_module, "IngestService", _FakeIngestService)
    _install_fake_operation_run_service(monkeypatch)

    services = OperationServices(session_factory=object(), cache=_FakeCache(invalidations=[]))  # type: ignore[arg-type]
    payload = services.ingest(folder_path=str(uppercase), dry_run=True)
    assert payload["mode"] == "VALIDATION_ONLY"


def test_ingest_accepts_windows_drive_path_via_wsl_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    mapped = Path("/mnt/c/Users/micro/Documents/Media-Manager-Test")
    windows = "C:\\Users\\micro\\Documents\\Media-Manager-Test"

    def _fake_exists(self: Path) -> bool:
        return str(self) == str(mapped)

    def _fake_is_dir(self: Path) -> bool:
        return str(self) == str(mapped)

    class _FakeIngestService:
        def __init__(self, _session_factory) -> None:
            pass

        def validate_path(self, root: Path) -> SimpleNamespace:
            assert root == mapped
            return SimpleNamespace(to_dict=lambda: {"mode": "VALIDATION_ONLY", "delta": {"would_insert": 0}})

    monkeypatch.setattr(Path, "exists", _fake_exists)
    monkeypatch.setattr(Path, "is_dir", _fake_is_dir)
    monkeypatch.setattr(operations_module, "IngestService", _FakeIngestService)
    _install_fake_operation_run_service(monkeypatch)

    services = OperationServices(session_factory=object(), cache=_FakeCache(invalidations=[]))  # type: ignore[arg-type]
    payload = services.ingest(folder_path=windows, dry_run=True)
    assert payload["mode"] == "VALIDATION_ONLY"


def test_ingest_rejects_nonexistent_after_normalization_with_actionable_message() -> None:
    services = OperationServices(session_factory=object(), cache=_FakeCache(invalidations=[]))  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Accepted examples: /mnt/c/path/to/folder"):
        services.ingest(folder_path='"/mnt/c/does/not/exist"', dry_run=True)


def test_plan_accepts_wrapped_quotes_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "a.jpg").write_bytes(b"x")

    class _FakeIngestService:
        def __init__(self, _session_factory) -> None:
            pass

        def collect_files(self, root: Path) -> list[Path]:
            assert root == dataset
            return [root / "a.jpg"]

        def ingest_paths(self, _files: list[Path], *, authoritative_root: Path | None = None, **kwargs):
            assert authoritative_root == dataset
            _ = kwargs
            return SimpleNamespace()

        def classify_paths(self, _files: list[Path], **kwargs):
            _ = kwargs
            return None

    class _FakeRunService:
        def __init__(self, _session_factory) -> None:
            pass

        def create_run(self, **kwargs):
            _ = kwargs
            return SimpleNamespace(id=uuid4())

    class _FakePlanner:
        def __init__(self, _session_factory) -> None:
            pass

        def plan_run(self, _run_id, _files, ingest_if_needed=False, strict_missing_metadata=False):
            _ = ingest_if_needed, strict_missing_metadata
            return SimpleNamespace(to_dict=lambda: {"scanned_count": 1, "move_actions": 0, "noop_actions": 1, "duplicate_actions": 0})

    monkeypatch.setattr(operations_module, "IngestService", _FakeIngestService)
    monkeypatch.setattr(operations_module, "RunService", _FakeRunService)
    monkeypatch.setattr(operations_module, "PlanningService", _FakePlanner)
    _install_fake_operation_run_service(monkeypatch)

    services = OperationServices(session_factory=object(), cache=_FakeCache(invalidations=[]))  # type: ignore[arg-type]
    payload = services.plan(folder_path=f'"{dataset}"', strict_metadata=False)
    assert payload["operation"] == "PLAN"


def test_media_file_validate_accepts_windows_drive_path(monkeypatch: pytest.MonkeyPatch) -> None:
    mapped = Path("/mnt/c/Users/micro/Documents/Media-Manager-Test")
    windows = "C:\\Users\\micro\\Documents\\Media-Manager-Test"

    def _fake_exists(self: Path) -> bool:
        return str(self) == str(mapped)

    def _fake_is_dir(self: Path) -> bool:
        return str(self) == str(mapped)

    class _FakeIngestService:
        def __init__(self, _session_factory) -> None:
            pass

        def validate_path(self, root: Path) -> SimpleNamespace:
            assert root == mapped
            return SimpleNamespace(to_dict=lambda: {"mode": "VALIDATION_ONLY", "delta": {"would_insert": 0}})

    monkeypatch.setattr(Path, "exists", _fake_exists)
    monkeypatch.setattr(Path, "is_dir", _fake_is_dir)
    monkeypatch.setattr(operations_module, "IngestService", _FakeIngestService)

    services = OperationServices(session_factory=object(), cache=_FakeCache(invalidations=[]))  # type: ignore[arg-type]
    payload = services.media_file_validate(folder_path=windows)
    assert payload["mode"] == "VALIDATION_ONLY"


def test_run_uses_resolved_folder_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()

    class _FakeIngestService:
        def __init__(self, _session_factory) -> None:
            pass

        @staticmethod
        def collect_files(root: Path) -> list[Path]:
            assert root == dataset
            return []

        def validate_paths(self, files: list[Path], *, authoritative_root: Path | None = None):
            assert files == []
            assert authoritative_root == dataset
            return SimpleNamespace(to_dict=lambda: {"mode": "VALIDATION_ONLY", "validation_report": {"delta": {"would_insert": 0}}})

    monkeypatch.setattr(operations_module, "IngestService", _FakeIngestService)
    _install_fake_operation_run_service(monkeypatch)

    services = OperationServices(session_factory=object(), cache=_FakeCache(invalidations=[]))  # type: ignore[arg-type]
    payload = services.run(folder_path=f"'{dataset}'", policy_name="FIRST_SEEN", dry_run=True)
    assert payload["mode"] == "VALIDATION_ONLY"
