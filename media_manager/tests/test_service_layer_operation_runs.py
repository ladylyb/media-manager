from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select

import media_manager.app.service_layer.operations as operations_module
from media_manager.app.persistence.models import OperationRun, OperationRunStatus, OperationRunType
from media_manager.app.service_layer.operations import OperationServices


@dataclass
class _FakeCache:
    invalidations: list[tuple[str, ...]]

    def invalidate(self, *keys: str) -> None:
        self.invalidations.append(tuple(keys))


def test_ingest_dry_run_creates_completed_operation_run(tmp_path: Path, session_factory) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "a.jpg").write_bytes(b"abc")
    cache = _FakeCache(invalidations=[])
    service = OperationServices(session_factory=session_factory, cache=cache)

    payload = service.ingest(folder_path=str(dataset), dry_run=True)

    assert payload["operation"] == "INGEST"
    assert payload["mode"] == "VALIDATION_ONLY"
    with session_factory() as session:
        rows = session.scalars(select(OperationRun).order_by(OperationRun.started_at.desc())).all()
    assert len(rows) == 1
    assert rows[0].operation_type == OperationRunType.INGEST
    assert rows[0].status == OperationRunStatus.COMPLETED
    assert rows[0].context.get("dry_run") is True


def test_plan_failure_marks_operation_run_failed(tmp_path: Path, session_factory, monkeypatch) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "a.jpg").write_bytes(b"abc")

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
            return SimpleNamespace(id=None)

    class _FailPlanner:
        def __init__(self, _session_factory) -> None:
            pass

        def plan_run(self, *_args, **_kwargs):
            raise RuntimeError("planned failure")

    monkeypatch.setattr(operations_module, "IngestService", _FakeIngestService)
    monkeypatch.setattr(operations_module, "RunService", _FakeRunService)
    monkeypatch.setattr(operations_module, "PlanningService", _FailPlanner)

    cache = _FakeCache(invalidations=[])
    service = OperationServices(session_factory=session_factory, cache=cache)

    try:
        service.plan(folder_path=str(dataset), strict_metadata=False)
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "planned failure" in str(exc)

    with session_factory() as session:
        rows = session.scalars(select(OperationRun).order_by(OperationRun.started_at.desc())).all()
    assert len(rows) == 1
    assert rows[0].operation_type == OperationRunType.PLAN
    assert rows[0].status == OperationRunStatus.FAILED
    assert rows[0].error_message is not None
