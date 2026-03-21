from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

import media_manager.app.persistence.apply as apply_module
import media_manager.app.persistence.planner as planner_module
import media_manager.app.core.filenames as filenames_module
import media_manager.app.core.metadata_extractor as metadata_extractor_module
from media_manager.app.core.filenames import generate_canonical_filename
from media_manager.app.persistence.apply import ApplyService
from media_manager.app.persistence.models import PlannedAction
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


def test_generate_canonical_filename_deterministic() -> None:
    taken = datetime(2024, 1, 11, 6, 7, 8, tzinfo=UTC)
    first = generate_canonical_filename("IMG", taken, ".jpg", owner="LL", context="General")
    second = generate_canonical_filename("IMG", taken, ".jpg", owner="LL", context="General")
    assert first == second
    assert first == "IMG_20240111_060708_LL_General.jpg"


def test_generate_canonical_filename_uses_milliseconds_when_available() -> None:
    taken = datetime(2024, 1, 11, 6, 7, 8, 123000, tzinfo=UTC)
    generated = generate_canonical_filename("IMG", taken, ".jpg", owner="LL", context="General")
    assert generated == "IMG_20240111_060708123_LL_General.jpg"


def test_generate_canonical_filename_invalid_context_too_long() -> None:
    taken = datetime(2024, 1, 11, 6, 7, 8, tzinfo=UTC)
    with pytest.raises(ValueError, match="context must be <= 20 characters"):
        generate_canonical_filename("IMG", taken, ".jpg", context="ThisContextIsWayTooLong")


def test_plan_contains_canonical_full_target_path(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed_dt = datetime(2024, 1, 11, 10, 11, 12, tzinfo=UTC)
    monkeypatch.setattr(metadata_extractor_module, "extract_file_metadata", lambda _path, _hash: [
        metadata_extractor_module.MetadataItem("OWNER", "LL"),
        metadata_extractor_module.MetadataItem("CONTEXT", "General"),
        metadata_extractor_module.MetadataItem("TAKEN_DT", fixed_dt.isoformat()),
        metadata_extractor_module.MetadataItem("FS_CTIME", fixed_dt.isoformat()),
        metadata_extractor_module.MetadataItem("FS_MTIME", fixed_dt.isoformat()),
    ])

    source = _write_file(tmp_path / "dataset" / "inbox" / "photo_one.jpg", b"one")
    run = RunService(session_factory).create_run()
    PlanningService(session_factory).plan_run(run.id, [source])

    with session_factory() as session:
        action = session.scalar(select(PlannedAction).where(PlannedAction.run_id == run.id))
        assert action is not None
        assert action.action_type == "RENAME"
        assert action.target_path is not None
        assert action.target_path.endswith("IMG_20240111_101112_LL_General.jpg")
        assert Path(action.target_path).is_absolute()


def test_collision_resolution_happens_in_plan(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed_dt = datetime(2024, 1, 11, 10, 11, 12, tzinfo=UTC)
    monkeypatch.setattr(metadata_extractor_module, "extract_file_metadata", lambda _path, _hash: [
        metadata_extractor_module.MetadataItem("OWNER", "LL"),
        metadata_extractor_module.MetadataItem("CONTEXT", "General"),
        metadata_extractor_module.MetadataItem("TAKEN_DT", fixed_dt.isoformat()),
        metadata_extractor_module.MetadataItem("FS_CTIME", fixed_dt.isoformat()),
        metadata_extractor_module.MetadataItem("FS_MTIME", fixed_dt.isoformat()),
    ])

    first = _write_file(tmp_path / "dataset" / "inbox" / "a.jpg", b"first")
    second = _write_file(tmp_path / "dataset" / "inbox" / "b.jpg", b"second")
    run = RunService(session_factory).create_run()
    PlanningService(session_factory).plan_run(run.id, [first, second])

    with session_factory() as session:
        actions = session.scalars(
            select(PlannedAction).where(PlannedAction.run_id == run.id).order_by(PlannedAction.source_path)
        ).all()
        assert len(actions) == 2
        targets = [Path(a.target_path or "") for a in actions]
        assert len({str(t) for t in targets}) == 2
        assert any(a.action_type == "COLLISION_RESOLVED" for a in actions)
        assert any("_C01." in (a.target_path or "") for a in actions if a.action_type == "COLLISION_RESOLVED")


def test_replan_is_deterministic_for_targets(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed_dt = datetime(2024, 1, 11, 10, 11, 12, tzinfo=UTC)
    monkeypatch.setattr(metadata_extractor_module, "extract_file_metadata", lambda _path, _hash: [
        metadata_extractor_module.MetadataItem("OWNER", "LL"),
        metadata_extractor_module.MetadataItem("CONTEXT", "General"),
        metadata_extractor_module.MetadataItem("TAKEN_DT", fixed_dt.isoformat()),
        metadata_extractor_module.MetadataItem("FS_CTIME", fixed_dt.isoformat()),
        metadata_extractor_module.MetadataItem("FS_MTIME", fixed_dt.isoformat()),
    ])

    first = _write_file(tmp_path / "dataset" / "inbox" / "a.jpg", b"first")
    second = _write_file(tmp_path / "dataset" / "inbox" / "b.jpg", b"second")
    planner = PlanningService(session_factory)
    run_service = RunService(session_factory)

    run1 = run_service.create_run()
    planner.plan_run(run1.id, [first, second])
    with session_factory() as session:
        targets1 = session.scalars(
            select(PlannedAction.target_path)
            .where(PlannedAction.run_id == run1.id)
            .order_by(PlannedAction.source_path)
        ).all()

    run2 = run_service.create_run()
    planner.plan_run(run2.id, [first, second])
    with session_factory() as session:
        targets2 = session.scalars(
            select(PlannedAction.target_path)
            .where(PlannedAction.run_id == run2.id)
            .order_by(PlannedAction.source_path)
        ).all()

    assert targets1 == targets2


def test_apply_does_not_call_generate_canonical_filename(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed_dt = datetime(2024, 1, 11, 10, 11, 12, tzinfo=UTC)
    monkeypatch.setattr(metadata_extractor_module, "extract_file_metadata", lambda _path, _hash: [
        metadata_extractor_module.MetadataItem("OWNER", "LL"),
        metadata_extractor_module.MetadataItem("CONTEXT", "General"),
        metadata_extractor_module.MetadataItem("TAKEN_DT", fixed_dt.isoformat()),
        metadata_extractor_module.MetadataItem("FS_CTIME", fixed_dt.isoformat()),
        metadata_extractor_module.MetadataItem("FS_MTIME", fixed_dt.isoformat()),
    ])

    source = _write_file(tmp_path / "dataset" / "inbox" / "photo_one.jpg", b"one")
    run = RunService(session_factory).create_run()
    PlanningService(session_factory).plan_run(run.id, [source])

    monkeypatch.setattr(
        filenames_module,
        "generate_canonical_filename",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("apply must not generate canonical filename")),
    )

    before = _snapshot(tmp_path / "dataset")
    ApplyService(session_factory).apply_run(run.id)
    after = _snapshot(tmp_path / "dataset")

    assert before != after


def test_apply_executes_only_planned_paths(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed_dt = datetime(2024, 1, 11, 10, 11, 12, tzinfo=UTC)
    monkeypatch.setattr(metadata_extractor_module, "extract_file_metadata", lambda _path, _hash: [
        metadata_extractor_module.MetadataItem("OWNER", "LL"),
        metadata_extractor_module.MetadataItem("CONTEXT", "General"),
        metadata_extractor_module.MetadataItem("TAKEN_DT", fixed_dt.isoformat()),
        metadata_extractor_module.MetadataItem("FS_CTIME", fixed_dt.isoformat()),
        metadata_extractor_module.MetadataItem("FS_MTIME", fixed_dt.isoformat()),
    ])

    source = _write_file(tmp_path / "dataset" / "inbox" / "photo_one.jpg", b"one")
    run = RunService(session_factory).create_run()
    planner = PlanningService(session_factory)
    planner.plan_run(run.id, [source])

    with session_factory() as session:
        action = session.scalar(select(PlannedAction).where(PlannedAction.run_id == run.id))
        assert action is not None
        planned_target = Path(action.target_path or "")

    ApplyService(session_factory).apply_run(run.id)
    assert planned_target.exists()
    assert not source.exists()


def test_apply_logging_reflects_planned_action_types(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict] = []

    def _capture(_message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        calls.append(kwargs.get("extra", {}))

    monkeypatch.setattr(apply_module.logger, "info", _capture)
    fixed_dt = datetime(2024, 1, 11, 10, 11, 12, tzinfo=UTC)
    monkeypatch.setattr(metadata_extractor_module, "extract_file_metadata", lambda _path, _hash: [
        metadata_extractor_module.MetadataItem("OWNER", "LL"),
        metadata_extractor_module.MetadataItem("CONTEXT", "General"),
        metadata_extractor_module.MetadataItem("TAKEN_DT", fixed_dt.isoformat()),
        metadata_extractor_module.MetadataItem("FS_CTIME", fixed_dt.isoformat()),
        metadata_extractor_module.MetadataItem("FS_MTIME", fixed_dt.isoformat()),
    ])

    first = _write_file(tmp_path / "dataset" / "inbox" / "a.jpg", b"first")
    second = _write_file(tmp_path / "dataset" / "inbox" / "b.jpg", b"second")
    run = RunService(session_factory).create_run()
    PlanningService(session_factory).plan_run(run.id, [first, second])
    ApplyService(session_factory).apply_run(run.id)

    actions = {extra.get("action") for extra in calls if extra.get("phase") == "apply"}
    assert "RENAME" in actions or "COLLISION_RESOLVED" in actions
