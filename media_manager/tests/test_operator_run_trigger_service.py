from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

from media_manager.app.persistence.apply import ApplySummary
from media_manager.app.persistence.canonicalization import RecomputeMode, RecomputeSummary
from media_manager.app.persistence.ingest import IngestSummary
from media_manager.app.persistence.operator_run_trigger import (
    OperatorRunTriggerService,
    RunTriggerCommand,
)
from media_manager.app.persistence.planner import PlanningSummary


@dataclass
class _RunObj:
    id: uuid.UUID


def test_trigger_run_dry_run_skips_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import media_manager.app.persistence.operator_run_trigger as module

    root = tmp_path / "dataset"
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.jpg").write_bytes(b"a")

    apply_calls = {"count": 0}
    recompute_mode = {"value": None}

    class FakeIngestService:
        def __init__(self, _session_factory) -> None:
            pass

        @staticmethod
        def collect_files(_root: Path) -> list[Path]:
            return [root / "a.jpg"]

        def ingest_paths(self, _files: list[Path]) -> IngestSummary:
            return IngestSummary(
                files_scanned=1,
                new_contents=1,
                new_instances=1,
                duplicates_detected=0,
                metadata_extracted=1,
                duration_s=0.1,
            )

    class FakeRunService:
        def __init__(self, _session_factory) -> None:
            pass

        def create_run(self) -> _RunObj:
            return _RunObj(id=uuid.UUID("11111111-1111-1111-1111-111111111111"))

    class FakePlanningService:
        def __init__(self, _session_factory) -> None:
            pass

        def plan_run(self, run_id, _files, ingest_if_needed=False):
            assert ingest_if_needed is False
            return PlanningSummary(
                run_id=run_id,
                scanned_count=1,
                supported_count=1,
                skipped_count=0,
                move_actions=1,
                noop_actions=0,
                duplicate_actions=2,
            )

    class FakeApplyService:
        def __init__(self, _session_factory) -> None:
            pass

        def apply_run(self, _run_id) -> ApplySummary:
            apply_calls["count"] += 1
            return ApplySummary(
                applied_count=0,
                skipped_count=0,
                duplicates_count=0,
                noop_count=0,
                errors_count=0,
                moves_count=0,
            )

    def fake_recompute(_session_factory, *, policy, context, mode):
        _ = policy, context
        recompute_mode["value"] = mode
        return RecomputeSummary(
            run_id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            scanned_count=1,
            changed_count=3,
            failed_count=0,
            applied_count=0,
            status="COMPLETED",
            changed_content_ids=(),
            failed_content_ids=(),
        )

    monkeypatch.setattr(module, "IngestService", FakeIngestService)
    monkeypatch.setattr(module, "RunService", FakeRunService)
    monkeypatch.setattr(module, "PlanningService", FakePlanningService)
    monkeypatch.setattr(module, "ApplyService", FakeApplyService)
    monkeypatch.setattr(module, "recompute_canonical_assignments", fake_recompute)

    service = OperatorRunTriggerService(session_factory=None)
    result = service.trigger_run(RunTriggerCommand(folder_path=str(root), policy_name="FIRST_SEEN", dry_run=True))

    assert result.run_id == "11111111-1111-1111-1111-111111111111"
    assert result.duplicates_found == 2
    assert result.canonical_changes == 3
    assert result.summary_metrics["apply"] is None
    assert result.summary_metrics["policy_name"] == "FIRST_SEEN"
    assert result.summary_metrics["dry_run"] is True
    assert apply_calls["count"] == 0
    assert recompute_mode["value"] == RecomputeMode.DRY_RUN


def test_trigger_run_full_run_invokes_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import media_manager.app.persistence.operator_run_trigger as module

    root = tmp_path / "dataset"
    root.mkdir(parents=True, exist_ok=True)

    apply_calls = {"count": 0}

    class FakeIngestService:
        def __init__(self, _session_factory) -> None:
            pass

        @staticmethod
        def collect_files(_root: Path) -> list[Path]:
            return []

        def ingest_paths(self, _files: list[Path]) -> IngestSummary:
            return IngestSummary(0, 0, 0, 0, 0, 0.0)

    class FakeRunService:
        def __init__(self, _session_factory) -> None:
            pass

        def create_run(self) -> _RunObj:
            return _RunObj(id=uuid.UUID("22222222-2222-2222-2222-222222222222"))

    class FakePlanningService:
        def __init__(self, _session_factory) -> None:
            pass

        def plan_run(self, run_id, _files, ingest_if_needed=False):
            assert ingest_if_needed is False
            return PlanningSummary(run_id, 0, 0, 0, 0, 0, 4)

    class FakeApplyService:
        def __init__(self, _session_factory) -> None:
            pass

        def apply_run(self, _run_id) -> ApplySummary:
            apply_calls["count"] += 1
            return ApplySummary(
                applied_count=5,
                skipped_count=0,
                duplicates_count=1,
                noop_count=0,
                errors_count=0,
                moves_count=4,
            )

    def fake_recompute(_session_factory, *, policy, context, mode):
        _ = policy, context
        assert mode == RecomputeMode.APPLY
        return RecomputeSummary(
            run_id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            scanned_count=2,
            changed_count=7,
            failed_count=0,
            applied_count=7,
            status="COMPLETED",
            changed_content_ids=(),
            failed_content_ids=(),
        )

    monkeypatch.setattr(module, "IngestService", FakeIngestService)
    monkeypatch.setattr(module, "RunService", FakeRunService)
    monkeypatch.setattr(module, "PlanningService", FakePlanningService)
    monkeypatch.setattr(module, "ApplyService", FakeApplyService)
    monkeypatch.setattr(module, "recompute_canonical_assignments", fake_recompute)

    service = OperatorRunTriggerService(session_factory=None)
    result = service.trigger_run(RunTriggerCommand(folder_path=str(root), policy_name="PREFER_ROOT", dry_run=False))

    assert result.run_id == "22222222-2222-2222-2222-222222222222"
    assert result.duplicates_found == 4
    assert result.canonical_changes == 7
    assert result.summary_metrics["apply"] is not None
    assert result.summary_metrics["policy_name"] == "PREFER_ROOT"
    assert result.summary_metrics["dry_run"] is False
    assert apply_calls["count"] == 1


def test_trigger_run_invalid_folder_validation(tmp_path: Path) -> None:
    service = OperatorRunTriggerService(session_factory=None)

    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="does not exist"):
        service.trigger_run(RunTriggerCommand(folder_path=str(missing), policy_name="FIRST_SEEN", dry_run=True))

    file_path = tmp_path / "file.txt"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a directory"):
        service.trigger_run(RunTriggerCommand(folder_path=str(file_path), policy_name="FIRST_SEEN", dry_run=True))


def test_trigger_run_rejects_unknown_policy(tmp_path: Path) -> None:
    root = tmp_path / "dataset"
    root.mkdir(parents=True, exist_ok=True)
    service = OperatorRunTriggerService(session_factory=None)

    with pytest.raises(Exception, match="Unknown canonical policy"):
        service.trigger_run(RunTriggerCommand(folder_path=str(root), policy_name="NOPE", dry_run=True))


def test_trigger_result_shape_stable_across_repeated_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import media_manager.app.persistence.operator_run_trigger as module

    root = tmp_path / "dataset"
    root.mkdir(parents=True, exist_ok=True)

    run_counter = {"count": 0}

    class FakeIngestService:
        def __init__(self, _session_factory) -> None:
            pass

        @staticmethod
        def collect_files(_root: Path) -> list[Path]:
            return []

        def ingest_paths(self, _files: list[Path]) -> IngestSummary:
            return IngestSummary(0, 0, 0, 0, 0, 0.0)

    class FakeRunService:
        def __init__(self, _session_factory) -> None:
            pass

        def create_run(self) -> _RunObj:
            run_counter["count"] += 1
            return _RunObj(id=uuid.uuid5(uuid.NAMESPACE_DNS, f"run-{run_counter['count']}"))

    class FakePlanningService:
        def __init__(self, _session_factory) -> None:
            pass

        def plan_run(self, run_id, _files, ingest_if_needed=False):
            assert ingest_if_needed is False
            return PlanningSummary(run_id, 3, 3, 0, 1, 1, 1)

    class FakeApplyService:
        def __init__(self, _session_factory) -> None:
            pass

        def apply_run(self, _run_id) -> ApplySummary:
            return ApplySummary(2, 0, 1, 0, 0, 1)

    def fake_recompute(_session_factory, *, policy, context, mode):
        _ = policy, context, mode
        return RecomputeSummary(
            run_id=uuid.uuid4(),
            scanned_count=1,
            changed_count=2,
            failed_count=0,
            applied_count=2,
            status="COMPLETED",
            changed_content_ids=(),
            failed_content_ids=(),
        )

    monkeypatch.setattr(module, "IngestService", FakeIngestService)
    monkeypatch.setattr(module, "RunService", FakeRunService)
    monkeypatch.setattr(module, "PlanningService", FakePlanningService)
    monkeypatch.setattr(module, "ApplyService", FakeApplyService)
    monkeypatch.setattr(module, "recompute_canonical_assignments", fake_recompute)

    service = OperatorRunTriggerService(session_factory=None)
    first = service.trigger_run(RunTriggerCommand(folder_path=str(root), policy_name="FIRST_SEEN", dry_run=False)).to_dict()
    second = service.trigger_run(RunTriggerCommand(folder_path=str(root), policy_name="FIRST_SEEN", dry_run=False)).to_dict()

    assert set(first.keys()) == {"run_id", "summary_metrics", "duplicates_found", "canonical_changes"}
    assert set(second.keys()) == set(first.keys())
    assert set(first["summary_metrics"].keys()) == {"ingest", "plan", "apply", "dry_run", "policy_name"}
    assert set(second["summary_metrics"].keys()) == set(first["summary_metrics"].keys())
    assert first["duplicates_found"] == second["duplicates_found"] == 1
    assert first["canonical_changes"] == second["canonical_changes"] == 2
