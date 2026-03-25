from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from media_manager.app.core.errors import ApplyStateError
from media_manager.app.core.path_resolver import collision_filename
from media_manager.app.persistence.apply import ApplyService
from media_manager.app.persistence.models import (
    ApplyAuditItem,
    ApplyAuditRun,
    FileInstance,
    FailureEvent,
    FailurePhase,
    PlannedAction,
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


def _create_planned_run_with_moves_only(tmp_path: Path, session_factory) -> uuid.UUID:
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    run = run_service.create_run()

    move_a = _write_file(tmp_path / "inbox" / "IMG_20240111.jpg", b"content-a")
    move_b = _write_file(tmp_path / "inbox" / "IMG_20240112.jpg", b"content-b")
    planner.plan_run(run.id, [move_a, move_b])
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

    with pytest.raises(ApplyStateError, match="Apply is only allowed from PLANNED or FAILED"):
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


def test_apply_service_records_invalid_target_parent_path_failure(tmp_path: Path, session_factory) -> None:
    run_id = _create_planned_run_with_actions(tmp_path, session_factory)

    photos_dir = tmp_path / "Media" / "Photos"
    for child in sorted(photos_dir.rglob("*"), reverse=True):
        if child.is_file():
            child.unlink()
        elif child.is_dir():
            child.rmdir()
    photos_dir.rmdir()
    photos_dir.write_bytes(b"not-a-directory")

    service = ApplyService(session_factory)

    with pytest.raises(RuntimeError, match="Apply target parent path invalid"):
        service.apply_run(run_id)

    with session_factory() as session:
        run = session.scalar(select(Run).where(Run.id == run_id))
        assert run is not None
        assert run.state == RunStateDB.FAILED

        failures = session.scalars(select(FailureEvent).where(FailureEvent.run_id == run_id)).all()
        error_codes = {failure.error_code for failure in failures}
        assert "TARGET_PARENT_PATH_INVALID" in error_codes
        assert "APPLY_FAILED" in error_codes


def test_apply_rename_collision_mode_resolves_to_collision_suffix(tmp_path: Path, session_factory) -> None:
    run_id = _create_planned_run_with_moves_only(tmp_path, session_factory)

    with session_factory() as session:
        action = session.scalar(
            select(PlannedAction)
            .where(PlannedAction.run_id == run_id, PlannedAction.action_type == "RENAME")
            .order_by(PlannedAction.target_path.asc())
        )
        assert action is not None
        occupied_path = Path(action.target_path or "")
        file_row = session.get(FileInstance, action.file_id)
        assert file_row is not None

    _write_file(occupied_path, b"occupied")

    summary = ApplyService(session_factory).apply_run(run_id, collision_mode="rename")
    assert summary.applied_count == 2

    resolved_path = occupied_path.with_name(collision_filename(occupied_path.name, 1))
    assert occupied_path.exists()
    assert resolved_path.exists()

    with session_factory() as session:
        file_row = session.get(FileInstance, action.file_id)
        assert file_row is not None
        assert file_row.absolute_path == str(resolved_path.resolve(strict=False))

        audit_run = session.scalars(
            select(ApplyAuditRun).where(ApplyAuditRun.run_id == run_id).order_by(ApplyAuditRun.started_at.desc())
        ).first()
        assert audit_run is not None
        audit_item = session.scalar(
            select(ApplyAuditItem).where(
                ApplyAuditItem.run_id == audit_run.id,
                ApplyAuditItem.planned_action_id == action.id,
            )
        )
        assert audit_item is not None
        assert audit_item.result == "APPLIED"
        assert audit_item.target_path == str(resolved_path.resolve(strict=False))


def test_apply_skip_collision_mode_records_skipped_item_and_completes(tmp_path: Path, session_factory) -> None:
    run_id = _create_planned_run_with_moves_only(tmp_path, session_factory)

    with session_factory() as session:
        action = session.scalar(
            select(PlannedAction)
            .where(PlannedAction.run_id == run_id, PlannedAction.action_type == "RENAME")
            .order_by(PlannedAction.target_path.asc())
        )
        assert action is not None
        occupied_path = Path(action.target_path or "")

    _write_file(occupied_path, b"occupied")

    summary = ApplyService(session_factory).apply_run(run_id, collision_mode="skip")
    assert summary.skipped_count == 1

    with session_factory() as session:
        run = session.scalar(select(Run).where(Run.id == run_id))
        assert run is not None
        assert run.state == RunStateDB.COMPLETED

        audit_runs = session.scalars(select(ApplyAuditRun).where(ApplyAuditRun.run_id == run_id)).all()
        assert len(audit_runs) == 1
        skipped_item = session.scalar(
            select(ApplyAuditItem).where(
                ApplyAuditItem.run_id == audit_runs[0].id,
                ApplyAuditItem.planned_action_id == action.id,
            )
        )
        assert skipped_item is not None
        assert skipped_item.result == "SKIPPED"
        assert "collision_mode=skip" in (skipped_item.error_message or "")


def test_apply_fail_collision_mode_preserves_failure_behavior(tmp_path: Path, session_factory) -> None:
    run_id = _create_planned_run_with_moves_only(tmp_path, session_factory)

    with session_factory() as session:
        action = session.scalar(
            select(PlannedAction)
            .where(PlannedAction.run_id == run_id, PlannedAction.action_type == "RENAME")
            .order_by(PlannedAction.target_path.asc())
        )
        assert action is not None
        occupied_path = Path(action.target_path or "")

    _write_file(occupied_path, b"occupied")

    with pytest.raises(RuntimeError, match="Apply target path already occupied unexpectedly"):
        ApplyService(session_factory).apply_run(run_id, collision_mode="fail")

    with session_factory() as session:
        run = session.scalar(select(Run).where(Run.id == run_id))
        assert run is not None
        assert run.state == RunStateDB.FAILED
        failure_codes = {
            failure.error_code for failure in session.scalars(select(FailureEvent).where(FailureEvent.run_id == run_id)).all()
        }
        assert "TARGET_PATH_OCCUPIED" in failure_codes
        assert "APPLY_FAILED" in failure_codes


def test_apply_failed_run_resume_skips_previously_applied_actions(tmp_path: Path, session_factory) -> None:
    run_id = _create_planned_run_with_moves_only(tmp_path, session_factory)
    service = ApplyService(session_factory)
    real_execute = service._execute_action
    call_count = 0

    def _fail_after_first_action(run_uuid, action, collision_mode):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("simulated mid-run failure")
        return real_execute(run_uuid, action, collision_mode)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(service, "_execute_action", _fail_after_first_action)
    try:
        with pytest.raises(RuntimeError, match="simulated mid-run failure"):
            service.apply_run(run_id, collision_mode="rename")
    finally:
        monkeypatch.undo()

    resumed_summary = ApplyService(session_factory).apply_run(run_id, collision_mode="rename")
    assert resumed_summary.applied_count == 1

    with session_factory() as session:
        run = session.scalar(select(Run).where(Run.id == run_id))
        assert run is not None
        assert run.state == RunStateDB.COMPLETED

        audit_runs = session.scalars(
            select(ApplyAuditRun).where(ApplyAuditRun.run_id == run_id).order_by(ApplyAuditRun.started_at.asc())
        ).all()
        assert len(audit_runs) == 2

        applied_items = session.scalars(
            select(ApplyAuditItem)
            .join(ApplyAuditRun, ApplyAuditRun.id == ApplyAuditItem.run_id)
            .where(
                ApplyAuditRun.run_id == run_id,
                ApplyAuditItem.result == "APPLIED",
            )
        ).all()
        assert len(applied_items) == 2
