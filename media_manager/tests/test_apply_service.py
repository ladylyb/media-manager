from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from media_manager.app.core.errors import ApplyStateError
from media_manager.app.persistence.apply import ApplyService
from media_manager.app.persistence.models import FailureEvent, FailurePhase, Run, RunStateDB
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _create_planned_run_with_actions(tmp_path: Path, session_factory) -> uuid.UUID:
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    run = run_service.create_run()

    noop_path = _write_file(tmp_path / "Media" / "Photos" / "2024" / "01" / "IMG_20240110.jpg", b"noop")
    move_path = _write_file(tmp_path / "inbox" / "IMG_20240111.jpg", b"dup-content")
    dup_path = _write_file(tmp_path / "inbox" / "dup_copy.jpg", b"dup-content")
    _write_file(tmp_path / "inbox" / "unsupported.customext", b"unsupported")
    planner.plan_run(run.id, [noop_path, move_path, dup_path, tmp_path / "inbox" / "unsupported.customext"])
    return run.id


def test_apply_service_rollback_records_failure_and_failed_state(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = _create_planned_run_with_actions(tmp_path, session_factory)
    service = ApplyService(session_factory)

    def _raise_on_execute(_action) -> None:
        raise RuntimeError("simulated apply failure")

    monkeypatch.setattr(service, "_simulate_execute", _raise_on_execute)

    with pytest.raises(RuntimeError, match="simulated apply failure"):
        service.apply_run(run_id)

    with session_factory() as session:
        run = session.scalar(select(Run).where(Run.id == run_id))
        assert run is not None
        assert run.state == RunStateDB.FAILED

        failures = session.scalars(select(FailureEvent).where(FailureEvent.run_id == run_id)).all()
        assert len(failures) == 1
        assert failures[0].phase == FailurePhase.APPLY
        assert failures[0].error_code == "APPLY_FAILED"


def test_apply_service_state_enforcement_non_planned_raises(session_factory) -> None:
    run_service = RunService(session_factory)
    service = ApplyService(session_factory)
    run = run_service.create_run()

    with pytest.raises(ApplyStateError, match="Apply is only allowed from PLANNED"):
        service.apply_run(run.id)
