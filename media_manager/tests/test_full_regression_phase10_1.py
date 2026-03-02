from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from media_manager.app.persistence.apply import ApplyService
from media_manager.app.persistence.models import PlannedAction
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_phase10_1_plan_regression_contract(tmp_path: Path, session_factory) -> None:
    dataset = tmp_path / "dataset"
    _write_file(dataset / "Media" / "Photos" / "2024" / "01" / "IMG_20240110.jpg", b"noop")
    _write_file(dataset / "inbox" / "IMG_20240111.jpg", b"dup-content")
    _write_file(dataset / "inbox" / "dup_copy.jpg", b"dup-content")
    _write_file(dataset / "inbox" / "unsupported.customext", b"unsupported")

    run_a = RunService(session_factory).create_run()
    run_b = RunService(session_factory).create_run()
    planner = PlanningService(session_factory)

    files = sorted([p for p in dataset.rglob("*") if p.is_file()], key=lambda p: p.as_posix())
    summary_a = planner.plan_run(run_a.id, files, ingest_if_needed=True)
    summary_b = planner.plan_run(run_b.id, files, ingest_if_needed=True)

    assert summary_a.scanned_count == summary_b.scanned_count == 2
    assert summary_a.move_actions == summary_b.move_actions == 1
    assert summary_a.duplicate_actions == summary_b.duplicate_actions == 1
    assert summary_a.noop_actions == summary_b.noop_actions == 0
    assert summary_a.skipped_count == summary_b.skipped_count == 1


def test_phase10_1_apply_regression_contract(tmp_path: Path, session_factory) -> None:
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    apply_service = ApplyService(session_factory)

    run = run_service.create_run()
    first = _write_file(tmp_path / "inbox" / "IMG_20240111.jpg", b"dup-content")
    second = _write_file(tmp_path / "inbox" / "dup_copy.jpg", b"dup-content")

    planner.plan_run(run.id, [first, second], ingest_if_needed=True)
    with session_factory() as session:
        planned = session.scalars(select(PlannedAction).where(PlannedAction.run_id == run.id)).all()
        expected_total = len(planned)
        expected_moves = sum(1 for row in planned if row.action_type in {"RENAME", "MOVE"})
        expected_dupes = sum(1 for row in planned if row.action_type in {"COLLISION_RESOLVED", "MARK_DUPLICATE"})

    summary = apply_service.apply_run(str(run.id))

    assert summary.applied_count == expected_total
    assert summary.moves_count == expected_moves
    assert summary.duplicates_count == expected_dupes
    assert summary.errors_count == 0
