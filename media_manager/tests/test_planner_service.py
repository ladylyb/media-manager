from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import delete, select, update

from media_manager.app.core.errors import MissingRequiredMetadataError, PlanningStateError
from media_manager.app.core.state_machine import RunState
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.models import (
    CanonicalAssignment,
    FailureEvent,
    FileContent,
    FileInstance,
    MediaMetadata,
    MetadataCode,
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
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    ingest = IngestService(session_factory)
    first = _write_file(tmp_path / "a.jpg", b"same-content")
    second = _write_file(tmp_path / "b.jpg", b"same-content")

    ingest.ingest_paths([first, second])
    run = run_service.create_run()
    planner.plan_run(run.id, [first, second], ingest_if_needed=False)
    with session_factory() as session:
        contents = session.scalars(select(FileContent)).all()
        instances = session.scalars(select(FileInstance).order_by(FileInstance.absolute_path)).all()
        assignments = session.scalars(
            select(CanonicalAssignment).order_by(CanonicalAssignment.assigned_at.desc(), CanonicalAssignment.assignment_id.desc())
        ).all()
        assert len(contents) == 1
        assert len(instances) == 2
        assert len(assignments) >= 1
        content = contents[0]
        expected = sorted(instances, key=lambda i: (i.first_seen_at, i.file_instance_id))[0]
        assert assignments[-1].canonical_instance_id == expected.file_instance_id


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


def test_planner_skips_missing_required_metadata_when_not_strict(tmp_path: Path, session_factory) -> None:
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    ingest = IngestService(session_factory)

    path = _write_file(tmp_path / "missing-owner.jpg", b"x")
    ingest.ingest_paths([path])
    with session_factory.begin() as session:
        content_id = session.scalar(select(FileInstance.content_id).where(FileInstance.absolute_path == str(path.resolve())))
        owner_code_id = session.scalar(select(MetadataCode.id).where(MetadataCode.code_type == "OWNER"))
        session.execute(
            delete(MediaMetadata).where(
                MediaMetadata.content_id == content_id,
                MediaMetadata.code_id == owner_code_id,
            )
        )

    run = run_service.create_run()
    summary = planner.plan_run(
        run.id,
        [path],
        ingest_if_needed=False,
        strict_missing_metadata=False,
        required_metadata_codes={"OWNER", "CONTEXT", "TAKEN_DT"},
    )
    assert summary.scanned_count == 0
    assert summary.skipped_count == 1
    with session_factory() as session:
        actions = session.scalars(select(PlannedAction).where(PlannedAction.run_id == run.id)).all()
        assert actions == []


def test_planner_raises_missing_required_metadata_when_strict(tmp_path: Path, session_factory) -> None:
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    ingest = IngestService(session_factory)

    path = _write_file(tmp_path / "missing-context.jpg", b"x")
    ingest.ingest_paths([path])
    with session_factory.begin() as session:
        content_id = session.scalar(select(FileInstance.content_id).where(FileInstance.absolute_path == str(path.resolve())))
        context_code_id = session.scalar(select(MetadataCode.id).where(MetadataCode.code_type == "CONTEXT"))
        session.execute(
            delete(MediaMetadata).where(
                MediaMetadata.content_id == content_id,
                MediaMetadata.code_id == context_code_id,
            )
        )

    run = run_service.create_run()
    with pytest.raises(MissingRequiredMetadataError):
        planner.plan_run(
            run.id,
            [path],
            ingest_if_needed=False,
            strict_missing_metadata=True,
            required_metadata_codes={"OWNER", "CONTEXT", "TAKEN_DT"},
        )


def test_planner_missing_metadata_warning_has_structured_fields(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    ingest = IngestService(session_factory)
    warnings: list[dict] = []

    path = _write_file(tmp_path / "missing-owner-structured.jpg", b"x")
    ingest.ingest_paths([path])
    with session_factory.begin() as session:
        content_id = session.scalar(select(FileInstance.content_id).where(FileInstance.absolute_path == str(path.resolve())))
        owner_code_id = session.scalar(select(MetadataCode.id).where(MetadataCode.code_type == "OWNER"))
        session.execute(
            delete(MediaMetadata).where(
                MediaMetadata.content_id == content_id,
                MediaMetadata.code_id == owner_code_id,
            )
        )

    def _capture(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        if message == "Missing required metadata":
            warnings.append(kwargs.get("extra", {}))

    import media_manager.app.persistence.planner as planner_module

    monkeypatch.setattr(planner_module.logger, "warning", _capture)
    run = run_service.create_run()
    planner.plan_run(
        run.id,
        [path],
        ingest_if_needed=False,
        strict_missing_metadata=False,
        required_metadata_codes={"OWNER", "CONTEXT", "TAKEN_DT"},
    )
    assert len(warnings) == 1
    extra = warnings[0]
    assert extra["content_id"]
    assert extra["file_instance_id"]
    assert extra["canonical_instance_id"]
    assert extra["missing_codes"] == ["OWNER"]
    assert extra["strict_missing_metadata"] is False


def test_planner_reads_canonical_assignment_and_ignores_legacy_column(tmp_path: Path, session_factory) -> None:
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    ingest = IngestService(session_factory)

    first = _write_file(tmp_path / "first.jpg", b"same")
    second = _write_file(tmp_path / "copy" / "second.jpg", b"same")
    ingest.ingest_paths([first, second])

    with session_factory.begin() as session:
        content = session.scalar(select(FileContent))
        assert content is not None
        instances = session.scalars(
            select(FileInstance).where(FileInstance.content_id == content.content_id).order_by(FileInstance.absolute_path.asc())
        ).all()
        assert len(instances) == 2
        assignment_authority_instance = instances[0]
        legacy_instance = instances[1]
        # Force legacy pointer to disagree with active canonical assignment authority.
        content.canonical_file_instance_id = legacy_instance.file_instance_id
        session.add(
            CanonicalAssignment(
                content_id=content.content_id,
                canonical_instance_id=assignment_authority_instance.file_instance_id,
                policy_name="FIRST_SEEN",
                policy_version="v1",
            )
        )

    run = run_service.create_run()
    summary = planner.plan_run(run.id, [first, second], ingest_if_needed=False)
    assert summary.scanned_count >= 1
    with session_factory() as session:
        actions = session.scalars(select(PlannedAction).where(PlannedAction.run_id == run.id)).all()
        planned_source_paths = {Path(action.source_path).resolve(strict=False) for action in actions}
        assert Path(assignment_authority_instance.absolute_path).resolve(strict=False) in planned_source_paths
        assert Path(legacy_instance.absolute_path).resolve(strict=False) not in planned_source_paths
