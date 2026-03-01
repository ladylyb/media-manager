from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import func, select

from media_manager.app.persistence.apply import ApplyService
from media_manager.app.persistence.models import MediaMetadata, PlannedAction
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _snapshot(root: Path) -> dict[str, str]:
    state: dict[str, str] = {}
    for candidate in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.as_posix()):
        state[candidate.as_posix()] = hashlib.sha256(candidate.read_bytes()).hexdigest()
    return state


def test_phase6_metadata_pipeline_end_to_end(tmp_path: Path, session_factory) -> None:
    root = tmp_path / "dataset"
    first = _write_file(root / "inbox" / "a.jpg", b"first")
    second = _write_file(root / "inbox" / "b.jpg", b"second")
    unsupported = _write_file(root / "inbox" / "unsupported.abcx", b"u")

    run = RunService(session_factory).create_run()
    planner = PlanningService(session_factory)
    summary = planner.plan_run(run.id, [first, second, unsupported])
    assert summary.scanned_count == 2
    assert summary.skipped_count == 1

    with session_factory() as session:
        metadata_rows = session.scalars(select(MediaMetadata)).all()
        metadata_count_before_apply = len(metadata_rows)
        actions = session.scalars(
            select(PlannedAction).where(PlannedAction.run_id == run.id).order_by(PlannedAction.source_path)
        ).all()
        assert len(metadata_rows) > 0
        assert len(actions) == 2
        assert all(action.target_path for action in actions)
        planned_targets = [action.target_path for action in actions]
        assert planned_targets == sorted(planned_targets)

    before = _snapshot(root)
    apply_summary = ApplyService(session_factory).apply_run(run.id)
    after = _snapshot(root)
    assert apply_summary.applied_count == 2
    assert before != after
    assert not first.exists()
    assert not second.exists()

    with session_factory() as session:
        metadata_count_after_apply = session.scalar(select(func.count()).select_from(MediaMetadata))
        assert metadata_count_after_apply == metadata_count_before_apply
