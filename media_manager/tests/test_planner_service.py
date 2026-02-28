from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select

from media_manager.app.core.errors import PlanningStateError
from media_manager.app.core.state_machine import RunState, validate_transition
from media_manager.app.persistence.base import transactional_session
from media_manager.app.persistence.models import (
    FailureEvent,
    File,
    PlannedAction,
    PlannedActionType,
    Run,
    RunStateDB,
)
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_duplicate_detection_workflow(tmp_path: Path, session_factory) -> None:
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)

    run = run_service.create_run()

    f1 = _write_file(tmp_path / "dup1.jpg", b"same-content")
    f2 = _write_file(tmp_path / "dup2.jpg", b"same-content")

    summary = planner.plan_run(run.id, [f1, f2])
    assert summary.duplicate_actions == 1

    with session_factory() as session:
        files = session.scalars(select(File).order_by(File.path)).all()
        assert len(files) == 2
        dup = next(f for f in files if f.path.endswith("dup2.jpg"))
        assert dup.is_duplicate is True
        assert dup.original_file_id is not None

        actions = session.scalars(select(PlannedAction).order_by(PlannedAction.source_path)).all()
        assert len(actions) == 2
        assert any(a.action_type == PlannedActionType.MARK_DUPLICATE.value for a in actions)


def test_duplicate_original_selection_deterministic_across_runs(
    tmp_path: Path, session_factory
) -> None:
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)

    first = _write_file(tmp_path / "a_dup.jpg", b"same-content")
    second = _write_file(tmp_path / "b_dup.jpg", b"same-content")

    run_1 = run_service.create_run()
    planner.plan_run(run_1.id, [first, second])

    with session_factory() as session:
        files = session.scalars(select(File).where(File.path.in_([str(first), str(second)]))).all()
        assert len(files) == 2

        originals = [f for f in files if not f.is_duplicate]
        duplicates = [f for f in files if f.is_duplicate]
        assert len(originals) == 1
        assert len(duplicates) == 1

        expected_original = sorted(files, key=lambda f: (f.created_at, f.id))[0]
        assert originals[0].id == expected_original.id
        assert duplicates[0].original_file_id == expected_original.id

    run_2 = run_service.create_run()
    planner.plan_run(run_2.id, [first, second])

    with session_factory() as session:
        files_after = session.scalars(select(File).where(File.path.in_([str(first), str(second)]))).all()
        assert len(files_after) == 2

        originals_after = [f for f in files_after if not f.is_duplicate]
        duplicates_after = [f for f in files_after if f.is_duplicate]
        assert len(originals_after) == 1
        assert len(duplicates_after) == 1
        assert originals_after[0].id == expected_original.id
        assert duplicates_after[0].original_file_id == expected_original.id


def test_planned_action_generation_move_and_noop(tmp_path: Path, session_factory) -> None:
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)

    run = run_service.create_run()

    # This path is already canonical for photo/year/month and should produce NOOP.
    noop_path = _write_file(tmp_path / "Media" / "Photos" / "2024" / "01" / "IMG_20240110.jpg", b"a")
    move_path = _write_file(tmp_path / "inbox" / "IMG_20240111.jpg", b"b")

    summary = planner.plan_run(run.id, [noop_path, move_path])
    assert summary.noop_actions == 1
    assert summary.move_actions == 1

    with session_factory() as session:
        actions = session.scalars(select(PlannedAction)).all()
        assert len(actions) == 2
        assert any(a.action_type == PlannedActionType.NOOP.value for a in actions)
        assert any(a.action_type == PlannedActionType.MOVE.value for a in actions)


def test_unsupported_mime_is_skipped_without_persistence(tmp_path: Path, session_factory) -> None:
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)

    run = run_service.create_run()
    unknown = _write_file(tmp_path / "mystery.xyzabc", b"blob")

    summary = planner.plan_run(run.id, [unknown])
    assert summary.scanned_count == 1
    assert summary.supported_count == 0
    assert summary.skipped_count == 1
    assert summary.move_actions == 0
    assert summary.noop_actions == 0
    assert summary.duplicate_actions == 0

    with session_factory() as session:
        files = session.scalars(select(File)).all()
        actions = session.scalars(select(PlannedAction)).all()
        assert len(files) == 0
        assert len(actions) == 0


def test_planned_actions_idempotent_on_reentry_same_transaction(
    tmp_path: Path, session_factory
) -> None:
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    run = run_service.create_run()
    candidate = _write_file(tmp_path / "inbox" / "IMG_20240111.jpg", b"x")

    with transactional_session(session_factory) as session:
        run_row = planner._lock_run(session, run.id)
        planner._validate_planning_state(run_row)

        validate_transition(RunState(run_row.state.value), RunState.PLANNED)
        run_row.state = RunStateDB.PLANNED
        run_row.version += 1
        run_row.updated_at = func.now()

        first_action = planner._plan_single_path(session, run_row, candidate)
        second_action = planner._plan_single_path(session, run_row, candidate)
        assert first_action == second_action

        count_in_txn = session.scalar(
            select(func.count()).select_from(PlannedAction).where(PlannedAction.run_id == run.id)
        )
        assert count_in_txn == 1

    with session_factory() as session:
        count_after_commit = session.scalar(
            select(func.count()).select_from(PlannedAction).where(PlannedAction.run_id == run.id)
        )
        assert count_after_commit == 1


def test_planning_transaction_rollback(tmp_path: Path, session_factory) -> None:
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)

    run = run_service.create_run()
    ok = _write_file(tmp_path / "ok.jpg", b"ok")
    bad = tmp_path / "missing.jpg"

    with pytest.raises(ValueError):
        planner.plan_run(run.id, [ok, bad])

    with session_factory() as session:
        count_files = len(session.scalars(select(File)).all())
        count_actions = len(session.scalars(select(PlannedAction)).all())
        failures = session.scalars(select(FailureEvent).where(FailureEvent.run_id == run.id)).all()
        persisted_run = session.scalar(select(Run).where(Run.id == run.id))

        assert count_files == 0
        assert count_actions == 0
        assert len(failures) == 1
        assert persisted_run is not None
        assert persisted_run.state.value == RunState.FAILED.value


def test_run_state_enforcement_for_planning(tmp_path: Path, session_factory) -> None:
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)

    run = run_service.create_run()
    run_service.transition_run(run.id, RunState.PLANNED)

    file_path = _write_file(tmp_path / "x.jpg", b"x")
    with pytest.raises(PlanningStateError):
        planner.plan_run(run.id, [file_path])

    run_apply = run_service.create_run()
    run_service.transition_run(run_apply.id, RunState.PLANNED)
    run_service.transition_run(run_apply.id, RunState.APPLYING)
    with pytest.raises(PlanningStateError):
        planner.plan_run(run_apply.id, [file_path])
