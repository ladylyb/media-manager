from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from media_manager.app.persistence.apply import ApplyService
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.models import (
    ApplyAuditItem,
    ApplyAuditRun,
    FailureEvent,
    FileInstance,
    FileInstanceStatus,
    PlannedAction,
)
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _truncate_all(session_factory) -> None:
    with session_factory.begin() as session:
        session.execute(
            text(
                "TRUNCATE TABLE media_metadata, metadata_codes, planned_actions, "
                "apply_audit_items, apply_audit_runs, "
                "canonical_recompute_items, canonical_recompute_runs, canonical_assignments, "
                "file_instances, file_contents, "
                "failure_events, files, content_objects, runs RESTART IDENTITY CASCADE"
            )
        )


def _prepare_duplicate_run(tmp_path: Path, session_factory) -> tuple[uuid.UUID, uuid.UUID, str, str]:
    ingest = IngestService(session_factory)
    planner = PlanningService(session_factory)
    run_service = RunService(session_factory)

    root = tmp_path / "dataset"
    files = [
        _write_file(root / "inbox" / "dup_a.jpg", b"same-bytes"),
        _write_file(root / "inbox" / "dup_b.jpg", b"same-bytes"),
        _write_file(root / "inbox" / "unique.jpg", b"unique-bytes"),
    ]

    ingest.ingest_paths(files)
    run = run_service.create_run()
    planner.plan_run(run.id, files, ingest_if_needed=False)

    with session_factory() as session:
        duplicate_content_ids = (
            select(FileInstance.content_id)
            .where(FileInstance.status == FileInstanceStatus.ACTIVE.value)
            .group_by(FileInstance.content_id)
            .having(func.count(FileInstance.file_instance_id) > 1)
            .subquery()
        )
        action = session.scalar(
            select(PlannedAction)
            .join(FileInstance, FileInstance.file_instance_id == PlannedAction.file_id)
            .where(
                PlannedAction.run_id == run.id,
                FileInstance.content_id.in_(select(duplicate_content_ids.c.content_id)),
                PlannedAction.target_path.is_not(None),
                PlannedAction.source_path != PlannedAction.target_path,
            )
            .order_by(PlannedAction.target_path.asc().nulls_last(), PlannedAction.file_id.asc(), PlannedAction.id.asc())
            .limit(1)
        )
        assert action is not None
        return run.id, action.id, action.source_path, action.target_path or ""


def test_readable_canonical_allows_duplicate_mutation(tmp_path: Path, session_factory) -> None:
    run_id, action_id, source_path, _target_path = _prepare_duplicate_run(tmp_path, session_factory)
    service = ApplyService(session_factory)

    summary = service.apply_run(run_id)

    assert summary.applied_count >= 1
    assert not Path(source_path).exists()

    with session_factory() as session:
        failures = session.scalars(
            select(FailureEvent).where(FailureEvent.run_id == run_id, FailureEvent.error_code == "CANONICAL_UNREADABLE")
        ).all()
        assert failures == []

        audit_run = session.scalar(select(ApplyAuditRun).where(ApplyAuditRun.run_id == run_id))
        assert audit_run is not None
        item = session.scalar(
            select(ApplyAuditItem).where(
                ApplyAuditItem.run_id == audit_run.id,
                ApplyAuditItem.planned_action_id == action_id,
            )
        )
        assert item is not None
        assert item.result == "APPLIED"


def test_unreadable_canonical_skips_action_and_records_drift(
    tmp_path: Path,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id, action_id, source_path, target_path = _prepare_duplicate_run(tmp_path, session_factory)
    service = ApplyService(session_factory)

    import media_manager.app.persistence.apply as apply_module

    monkeypatch.setattr(apply_module, "is_canonical_readable", lambda _path: False)

    summary = service.apply_run(run_id)

    assert summary.skipped_count >= 1
    assert Path(source_path).exists()
    assert not Path(target_path).exists()

    with session_factory() as session:
        failures = session.scalars(
            select(FailureEvent).where(FailureEvent.run_id == run_id, FailureEvent.error_code == "CANONICAL_UNREADABLE")
        ).all()
        assert len(failures) >= 1
        assert "Canonical unreadable" in failures[0].error_message

        audit_run = session.scalar(select(ApplyAuditRun).where(ApplyAuditRun.run_id == run_id))
        assert audit_run is not None
        item = session.scalar(
            select(ApplyAuditItem).where(
                ApplyAuditItem.run_id == audit_run.id,
                ApplyAuditItem.planned_action_id == action_id,
            )
        )
        assert item is not None
        assert item.result == "SKIPPED"
        assert item.error_message is not None
        assert "Canonical unreadable" in item.error_message


def test_idempotent_repeated_run_same_result_shape(
    tmp_path: Path,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import media_manager.app.persistence.apply as apply_module

    monkeypatch.setattr(apply_module, "is_canonical_readable", lambda _path: False)

    run_id1, _action_id1, _source1, _target1 = _prepare_duplicate_run(tmp_path / "a", session_factory)
    summary1 = ApplyService(session_factory).apply_run(run_id1)

    _truncate_all(session_factory)

    run_id2, _action_id2, _source2, _target2 = _prepare_duplicate_run(tmp_path / "b", session_factory)
    summary2 = ApplyService(session_factory).apply_run(run_id2)

    assert summary1.to_dict() == summary2.to_dict()


def test_injected_readability_failure_resilience(
    tmp_path: Path,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id, _action_id, source_path, _target_path = _prepare_duplicate_run(tmp_path, session_factory)
    service = ApplyService(session_factory)

    import media_manager.app.persistence.apply as apply_module

    def _raise_probe(_path):
        raise OSError("simulated probe failure")

    monkeypatch.setattr(apply_module, "is_canonical_readable", _raise_probe)

    summary = service.apply_run(run_id)

    assert summary.skipped_count >= 1
    assert Path(source_path).exists()

    with session_factory() as session:
        failures = session.scalars(
            select(FailureEvent).where(FailureEvent.run_id == run_id, FailureEvent.error_code == "CANONICAL_UNREADABLE")
        ).all()
        assert len(failures) >= 1
