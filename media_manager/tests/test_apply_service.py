from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from media_manager.app.core.errors import ApplyStateError
from media_manager.app.persistence.apply import ApplyService
from media_manager.app.persistence.models import (
    ApplyAuditItem,
    ApplyAuditRun,
    FailureEvent,
    FailurePhase,
    Run,
    RunStateDB,
)
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

    def _raise_on_execute(_run_id, _action, _collision_mode) -> None:
        raise RuntimeError("simulated apply failure")

    monkeypatch.setattr(service, "_execute_action", _raise_on_execute)

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
        audit = session.scalar(select(ApplyAuditRun).where(ApplyAuditRun.run_id == run_id))
        assert audit is not None
        assert audit.status == "FAILED"
        assert audit.error_message is not None
        assert "simulated apply failure" in audit.error_message


def test_apply_service_state_enforcement_non_planned_raises(session_factory) -> None:
    run_service = RunService(session_factory)
    service = ApplyService(session_factory)
    run = run_service.create_run()

    with pytest.raises(ApplyStateError, match="Apply is only allowed from PLANNED"):
        service.apply_run(run.id)


def test_apply_service_uses_deterministic_ordering(tmp_path: Path, session_factory) -> None:
    run_id = _create_planned_run_with_actions(tmp_path, session_factory)
    service = ApplyService(session_factory)
    actions = service._load_actions_for_apply(run_id)
    ordering_keys = [(action.target_path or "", str(action.file_id), str(action.id)) for action in actions]
    assert ordering_keys == sorted(ordering_keys)


def test_apply_failure_transitions_through_applying_before_failed(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = _create_planned_run_with_actions(tmp_path, session_factory)
    service = ApplyService(session_factory)
    transitions: list[tuple[str, str]] = []

    def _capture(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        if message != "Transitioning run state":
            return
        extra = kwargs.get("extra", {})
        transitions.append((extra.get("from", ""), extra.get("to", "")))

    def _raise_on_execute(_run_id, _action, _collision_mode) -> None:
        raise RuntimeError("simulated transition failure")

    import media_manager.app.persistence.apply as apply_module

    monkeypatch.setattr(apply_module.logger, "info", _capture)
    monkeypatch.setattr(service, "_execute_action", _raise_on_execute)

    with pytest.raises(RuntimeError, match="simulated transition failure"):
        service.apply_run(run_id)

    assert ("PLANNED", "APPLYING") in transitions
    assert ("APPLYING", "FAILED") in transitions
    assert ("PLANNED", "FAILED") not in transitions


def test_apply_service_writes_audit_items(tmp_path: Path, session_factory) -> None:
    run_id = _create_planned_run_with_actions(tmp_path, session_factory)
    service = ApplyService(session_factory)
    summary = service.apply_run(run_id, collision_mode="rename")
    assert summary.applied_count >= 1

    with session_factory() as session:
        audit_run = session.scalar(select(ApplyAuditRun).where(ApplyAuditRun.run_id == run_id))
        assert audit_run is not None
        assert audit_run.status == "COMPLETED"
        items = session.scalars(select(ApplyAuditItem).where(ApplyAuditItem.run_id == audit_run.id)).all()
        assert len(items) >= 1
        assert all(item.result in {"APPLIED", "SKIPPED", "FAILED"} for item in items)
