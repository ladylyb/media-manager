from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select, update

from media_manager.app.core.errors import PlanningStateError
from media_manager.app.core.state_machine import RunState
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.models import (
    FailureEvent,
    FileContent,
    FileInstance,
    PlannedAction,
    PlannedActionType,
    Run,
)
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_duplicate_identity_and_canonical_selection(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    first = _write_file(tmp_path / "a.jpg", b"same-content")
    second = _write_file(tmp_path / "b.jpg", b"same-content")

    ingest.ingest_paths([first, second])
    with session_factory() as session:
        contents = session.scalars(select(FileContent)).all()
        instances = session.scalars(select(FileInstance).order_by(FileInstance.absolute_path)).all()
        assert len(contents) == 1
        assert len(instances) == 2
        content = contents[0]
        assert content.canonical_file_instance_id is not None
        expected = sorted(instances, key=lambda i: (i.first_seen_at, i.file_instance_id))[0]
        assert content.canonical_file_instance_id == expected.file_instance_id


def test_planner_generates_actions_from_canonical_instances_only(tmp_path: Path, session_factory) -> None:
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    ingest = IngestService(session_factory)

    run = run_service.create_run()
    noop_path = _write_file(tmp_path / "Media" / "Photos" / "2024" / "01" / "IMG_20240110_LL_General.jpg", b"a")
    move_path = _write_file(tmp_path / "inbox" / "IMG_20240111.jpg", b"b")
    dup_path = _write_file(tmp_path / "inbox" / "dup_copy.jpg", b"b")

    ingest.ingest_paths([noop_path, move_path, dup_path])
    summary = planner.plan_run(run.id, [noop_path, move_path, dup_path])
    assert summary.supported_count >= 2

    with session_factory() as session:
        actions = session.scalars(select(PlannedAction).where(PlannedAction.run_id == run.id)).all()
        assert len(actions) >= 2
        assert any(a.action_type in {PlannedActionType.RENAME.value, PlannedActionType.COLLISION_RESOLVED.value} for a in actions)


def test_planner_does_not_hash_when_planning_from_db_only(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_service = RunService(session_factory)
    ingest = IngestService(session_factory)
    planner = PlanningService(session_factory)

    candidate = _write_file(tmp_path / "x.jpg", b"x")
    ingest.ingest_paths([candidate])
    run = run_service.create_run()

    import media_manager.app.core.hashing as hashing_module

    monkeypatch.setattr(hashing_module, "sha256_file", lambda _p: (_ for _ in ()).throw(RuntimeError("no-hash")))
    summary = planner.plan_run(run.id)
    assert summary.supported_count >= 1


def test_planner_state_enforcement(tmp_path: Path, session_factory) -> None:
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    path = _write_file(tmp_path / "x.jpg", b"x")

    run = run_service.create_run()
    run_service.transition_run(run.id, RunState.PLANNED)
    with pytest.raises(PlanningStateError):
        planner.plan_run(run.id, [path])


def test_planning_failure_records_failure_event(tmp_path: Path, session_factory) -> None:
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    run = run_service.create_run()

    summary = planner.plan_run(run.id, [tmp_path / "missing.jpg"])
    assert summary.scanned_count == 0
    assert summary.skipped_count == 0
    with session_factory() as session:
        failures = session.scalars(select(FailureEvent).where(FailureEvent.run_id == run.id)).all()
        persisted_run = session.scalar(select(Run).where(Run.id == run.id))
        assert len(failures) == 0
        assert persisted_run is not None
        assert persisted_run.state.value == RunState.PLANNED.value


def test_planner_skips_inactive_canonical_instances(tmp_path: Path, session_factory) -> None:
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    ingest = IngestService(session_factory)

    path = _write_file(tmp_path / "x.jpg", b"x")
    ingest.ingest_paths([path])
    with session_factory.begin() as session:
        session.execute(update(FileInstance).values(status="DELETED"))

    run = run_service.create_run()
    summary = planner.plan_run(run.id, [path], ingest_if_needed=False)
    assert summary.scanned_count == 0
    assert summary.skipped_count >= 1
