from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import delete, select, text, update

from media_manager.app.core.errors import MissingRequiredMetadataError
from media_manager.app.persistence.apply import ApplyService
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.models import (
    CanonicalAssignment,
    FileContent,
    FileInstance,
    MediaMetadata,
    MetadataCode,
    PlannedAction,
)
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _build_dataset(root: Path, total_files: int = 50) -> list[Path]:
    files: list[Path] = []
    for idx in range(total_files):
        payload = f"payload-{idx}".encode("utf-8")
        files.append(_write_file(root / "inbox" / f"IMG_{idx:04d}.jpg", payload))

    # extra duplicates
    files.append(_write_file(root / "inbox" / "dup_a.jpg", b"shared-dup"))
    files.append(_write_file(root / "inbox" / "dup_b.jpg", b"shared-dup"))
    return sorted(files, key=lambda p: p.as_posix())


def _final_paths(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


def _canonical_by_hash(session_factory) -> dict[str, str]:
    with session_factory() as session:
        rows = session.execute(
            select(
                FileContent.content_id,
                FileContent.sha256_hash,
                CanonicalAssignment.canonical_instance_id,
                FileInstance.absolute_path,
                CanonicalAssignment.assigned_at,
                CanonicalAssignment.assignment_id,
            )
            .join(CanonicalAssignment, CanonicalAssignment.content_id == FileContent.content_id)
            .join(FileInstance, FileInstance.file_instance_id == CanonicalAssignment.canonical_instance_id)
            .order_by(FileContent.content_id.asc(), CanonicalAssignment.assigned_at.desc(), CanonicalAssignment.assignment_id.desc())
        ).all()

    by_content: dict[str, tuple[str, str]] = {}
    for content_id, sha, _instance_id, path, _assigned_at, _assignment_id in rows:
        key = str(content_id)
        if key not in by_content:
            by_content[key] = (sha, path)
    return {sha: path for sha, path in by_content.values()}


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


def _force_taken_dt(session_factory, value: str) -> None:
    with session_factory.begin() as session:
        taken_dt_code = session.scalar(select(MetadataCode.id).where(MetadataCode.code_type == "TAKEN_DT"))
        session.execute(
            update(MediaMetadata)
            .where(MediaMetadata.code_id == taken_dt_code)
            .values(decode_value=value)
        )


def test_phase8_strict_missing_metadata_behavior(tmp_path: Path, session_factory) -> None:
    root = tmp_path / "dataset-strict"
    files = _build_dataset(root, total_files=20)
    ingest = IngestService(session_factory)
    ingest.ingest_paths(files)

    # Remove OWNER metadata for one content to simulate missing required metadata.
    missing_path = files[0]
    with session_factory.begin() as session:
        content_id = session.scalar(select(FileInstance.content_id).where(FileInstance.absolute_path == str(missing_path.resolve())))
        owner_code_id = session.scalar(select(MetadataCode.id).where(MetadataCode.code_type == "OWNER"))
        session.execute(
            delete(MediaMetadata).where(
                MediaMetadata.content_id == content_id,
                MediaMetadata.code_id == owner_code_id,
            )
        )

    planner = PlanningService(session_factory)
    run_service = RunService(session_factory)

    relaxed_run = run_service.create_run()
    relaxed_summary = planner.plan_run(
        relaxed_run.id,
        files,
        ingest_if_needed=False,
        strict_missing_metadata=False,
        required_metadata_codes={"OWNER", "CONTEXT", "TAKEN_DT"},
    )
    assert relaxed_summary.skipped_count >= 1

    strict_run = run_service.create_run()
    with pytest.raises(MissingRequiredMetadataError):
        planner.plan_run(
            strict_run.id,
            files,
            ingest_if_needed=False,
            strict_missing_metadata=True,
            required_metadata_codes={"OWNER", "CONTEXT", "TAKEN_DT"},
        )


def test_phase8_collision_modes_and_deterministic_rename(tmp_path: Path, session_factory) -> None:
    root = tmp_path / "dataset-collisions"
    files = _build_dataset(root, total_files=20)
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    ingest = IngestService(session_factory)
    apply_service = ApplyService(session_factory)

    ingest.ingest_paths(files)

    run = run_service.create_run()
    planner.plan_run(run.id, files, ingest_if_needed=False)
    with session_factory() as session:
        action = session.scalar(
            select(PlannedAction)
            .where(PlannedAction.run_id == run.id, PlannedAction.target_path.is_not(None))
            .order_by(PlannedAction.target_path.asc())
        )
        assert action is not None
        collision_target = Path(action.target_path)

    collision_target.parent.mkdir(parents=True, exist_ok=True)
    collision_target.write_bytes(b"preexisting")

    summary = apply_service.apply_run(run.id, collision_mode="rename")
    assert summary.applied_count >= 1
    assert any(path.name.endswith("__dup01.jpg") for path in collision_target.parent.glob("*__dup01.jpg"))
    assert not any(path.name.endswith("__dup1.jpg") for path in collision_target.parent.glob("*__dup1.jpg"))

    _truncate_all(session_factory)
    root_skip = tmp_path / "dataset-skip"
    files_skip = _build_dataset(root_skip, total_files=20)
    ingest.ingest_paths(files_skip)
    run_skip = run_service.create_run()
    planner.plan_run(run_skip.id, files_skip, ingest_if_needed=False)
    with session_factory() as session:
        action_skip = session.scalar(
            select(PlannedAction)
            .where(PlannedAction.run_id == run_skip.id, PlannedAction.target_path.is_not(None))
            .order_by(PlannedAction.target_path.asc())
        )
        assert action_skip is not None
        skip_target = Path(action_skip.target_path)
    skip_target.parent.mkdir(parents=True, exist_ok=True)
    skip_target.write_bytes(b"preexisting")
    skip_summary = apply_service.apply_run(run_skip.id, collision_mode="skip")
    assert skip_summary.skipped_count >= 1

    _truncate_all(session_factory)
    root_fail = tmp_path / "dataset-fail"
    files_fail = _build_dataset(root_fail, total_files=20)
    ingest.ingest_paths(files_fail)
    run_fail = run_service.create_run()
    planner.plan_run(run_fail.id, files_fail, ingest_if_needed=False)
    with session_factory() as session:
        action_fail = session.scalar(
            select(PlannedAction)
            .where(PlannedAction.run_id == run_fail.id, PlannedAction.target_path.is_not(None))
            .order_by(PlannedAction.target_path.asc())
        )
        assert action_fail is not None
        fail_target = Path(action_fail.target_path)
    fail_target.parent.mkdir(parents=True, exist_ok=True)
    fail_target.write_bytes(b"preexisting")
    with pytest.raises(Exception):
        apply_service.apply_run(run_fail.id, collision_mode="fail")


def test_phase8_deterministic_replay_and_canonical_assignment(tmp_path: Path, session_factory) -> None:
    root1 = tmp_path / "dataset-a"
    files1 = _build_dataset(root1)
    ingest = IngestService(session_factory)
    planner = PlanningService(session_factory)
    run_service = RunService(session_factory)
    apply_service = ApplyService(session_factory)

    ingest.ingest_paths(files1)
    _force_taken_dt(session_factory, "2024-01-01T00:00:00+00:00")
    run1 = run_service.create_run()
    planner.plan_run(run1.id, files1, ingest_if_needed=False)
    run1_repeat = run_service.create_run()
    planner.plan_run(run1_repeat.id, files1, ingest_if_needed=False)
    with session_factory() as session:
        plan_first = session.scalars(
            select(PlannedAction.target_path)
            .where(PlannedAction.run_id == run1.id)
            .order_by(PlannedAction.target_path.asc().nulls_last(), PlannedAction.file_id.asc(), PlannedAction.id.asc())
        ).all()
        plan_repeat = session.scalars(
            select(PlannedAction.target_path)
            .where(PlannedAction.run_id == run1_repeat.id)
            .order_by(PlannedAction.target_path.asc().nulls_last(), PlannedAction.file_id.asc(), PlannedAction.id.asc())
        ).all()
    assert plan_first == plan_repeat

    apply_service.apply_run(run1.id, collision_mode="rename")
    paths_first = _final_paths(root1)
    canon_first = _canonical_by_hash(session_factory)

    _truncate_all(session_factory)
    root2 = tmp_path / "dataset-b"
    files2 = _build_dataset(root2)
    ingest.ingest_paths(files2)
    _force_taken_dt(session_factory, "2024-01-01T00:00:00+00:00")
    run2 = run_service.create_run()
    planner.plan_run(run2.id, files2, ingest_if_needed=False)
    apply_service.apply_run(run2.id, collision_mode="rename")
    paths_second = _final_paths(root2)
    canon_second = _canonical_by_hash(session_factory)

    assert paths_first == paths_second
    assert sorted(canon_first.keys()) == sorted(canon_second.keys())
    # canonical assignment must be deterministic by normalized location pattern.
    norm_first = sorted(Path(p).name for p in canon_first.values())
    norm_second = sorted(Path(p).name for p in canon_second.values())
    assert norm_first == norm_second


def test_phase8_unreadable_canonical_skips_duplicate_group_consistently(
    tmp_path: Path,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import media_manager.app.persistence.apply as apply_module

    monkeypatch.setattr(apply_module, "is_canonical_readable", lambda _path: False)

    root = tmp_path / "dataset-unreadable"
    files = _build_dataset(root, total_files=20)
    ingest = IngestService(session_factory)
    planner = PlanningService(session_factory)
    run_service = RunService(session_factory)
    apply_service = ApplyService(session_factory)

    ingest.ingest_paths(files)
    run = run_service.create_run()
    planner.plan_run(run.id, files, ingest_if_needed=False)

    summary = apply_service.apply_run(run.id, collision_mode="rename")
    assert summary.skipped_count >= 1
