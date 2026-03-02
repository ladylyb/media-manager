from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select

from media_manager.app.persistence.apply import ApplyService
from media_manager.app.persistence.models import CanonicalAssignment, FailureEvent, PlannedAction
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _prepare_run(tmp_path: Path, session_factory) -> tuple[str, dict[str, int]]:
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    run = run_service.create_run()

    move_a = _write_file(tmp_path / "inbox" / "IMG_20240111.jpg", b"dup-content")
    move_b = _write_file(tmp_path / "inbox" / "dup_copy.jpg", b"dup-content")
    planner.plan_run(run.id, [move_a, move_b])

    with session_factory() as session:
        actions = session.scalars(select(PlannedAction).where(PlannedAction.run_id == run.id)).all()
        expected = {
            "moves": sum(1 for a in actions if a.action_type in {"RENAME", "MOVE"}),
            "duplicates": sum(1 for a in actions if a.action_type in {"COLLISION_RESOLVED", "MARK_DUPLICATE"}),
            "noop": sum(1 for a in actions if a.action_type in {"SKIP", "NOOP"}),
            "total": len(actions),
        }

    return str(run.id), expected


def test_apply_behavioral_parity_without_simulation(tmp_path: Path, session_factory, monkeypatch) -> None:
    run_id, expected = _prepare_run(tmp_path, session_factory)
    service = ApplyService(session_factory)

    rename_calls: list[tuple[str, str]] = []
    real_rename = Path.rename

    def _rename_wrapper(self: Path, target: Path) -> Path:  # type: ignore[override]
        rename_calls.append((str(self.resolve(strict=False)), str(target.resolve(strict=False))))
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", _rename_wrapper)

    with session_factory() as session:
        before_assignments = int(session.scalar(select(func.count()).select_from(CanonicalAssignment)) or 0)

    summary = service.apply_run(run_id)

    with session_factory() as session:
        after_assignments = int(session.scalar(select(func.count()).select_from(CanonicalAssignment)) or 0)
        failures = session.scalars(select(FailureEvent)).all()

    assert summary.moves_count == expected["moves"]
    assert summary.duplicates_count == expected["duplicates"]
    assert summary.noop_count == expected["noop"]
    assert summary.applied_count == expected["total"]

    assert len(rename_calls) == expected["total"]
    assert before_assignments == after_assignments
    assert failures == []
