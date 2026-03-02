from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import select

from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.models import PlannedAction
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _plan_struct(summary, actions: list[PlannedAction]) -> dict[str, object]:
    ordered = sorted(
        actions,
        key=lambda row: (
            row.action_type,
            row.source_path,
            row.target_path or "",
            str(row.file_id),
        ),
    )
    return {
        "summary": {
            "scanned_count": summary.scanned_count,
            "supported_count": summary.supported_count,
            "skipped_count": summary.skipped_count,
            "move_actions": summary.move_actions,
            "noop_actions": summary.noop_actions,
            "duplicate_actions": summary.duplicate_actions,
        },
        "actions": [
            {
                "action_type": row.action_type,
                "source_path": row.source_path,
                "target_path": row.target_path,
                "file_id": str(row.file_id),
            }
            for row in ordered
        ],
    }


def _run_plan(path: Path, session_factory) -> dict[str, object]:
    run = RunService(session_factory).create_run()
    ingest = IngestService(session_factory)
    planner = PlanningService(session_factory)

    ingest_files = ingest.collect_files(path)
    ingest.ingest_paths(ingest_files)
    summary = planner.plan_run(run.id, ingest_files, ingest_if_needed=False)

    with session_factory() as session:
        actions = session.scalars(select(PlannedAction).where(PlannedAction.run_id == run.id)).all()
    return _plan_struct(summary, actions)


def test_plan_output_parity_structural_snapshot(tmp_path: Path, session_factory) -> None:
    dataset = tmp_path / "dataset"
    _write_file(dataset / "Media" / "Photos" / "2024" / "01" / "IMG_20240110.jpg", b"noop")
    _write_file(dataset / "inbox" / "IMG_20240111.jpg", b"dup-content")
    _write_file(dataset / "inbox" / "dup_copy.jpg", b"dup-content")
    _write_file(dataset / "inbox" / "unsupported.customext", b"unsupported")

    first = _run_plan(dataset, session_factory)
    second = _run_plan(dataset, session_factory)

    assert first == second
    assert first["summary"] == {
        "scanned_count": 2,
        "supported_count": 2,
        "skipped_count": 1,
        "move_actions": 1,
        "noop_actions": 0,
        "duplicate_actions": 1,
    }

    action_types = [row["action_type"] for row in first["actions"]]
    assert action_types == ["COLLISION_RESOLVED", "RENAME"]


def test_plan_structural_output_excludes_trace_artifact_fields(tmp_path: Path, session_factory) -> None:
    dataset = tmp_path / "dataset"
    _write_file(dataset / "a" / "one.jpg", b"same")
    _write_file(dataset / "b" / "two.jpg", b"same")

    plan_output = _run_plan(dataset, session_factory)

    # Regression contract: parity comparison is based on planner structure only.
    assert set(plan_output.keys()) == {"summary", "actions"}
    for row in plan_output["actions"]:
        assert "timestamp" not in row
        assert "artifact" not in row
        assert "run_id" not in row
