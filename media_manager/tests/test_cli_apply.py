from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

from sqlalchemy import select

from media_manager.app.cli import main
from media_manager.app.persistence.models import Run, RunStateDB
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _extract_run_id(output: str) -> uuid.UUID:
    match = re.search(r"Run ID:\s+([0-9a-fA-F-]{36})", output)
    assert match is not None
    return uuid.UUID(match.group(1))


def _normalize_run_id(output: str) -> str:
    return re.sub(r"Run ID:\s+[0-9a-fA-F-]{36}", "Run ID: <uuid>", output)


def _snapshot_files(root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for candidate in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.as_posix()):
        snapshot[candidate.as_posix()] = hashlib.sha256(candidate.read_bytes()).hexdigest()
    return snapshot


def _create_planned_run(tmp_path: Path, session_factory) -> tuple[uuid.UUID, Path]:
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    run = run_service.create_run()

    root = tmp_path / "dataset"
    noop_path = _write_file(root / "Media" / "Photos" / "2024" / "01" / "IMG_20240110.jpg", b"noop")
    move_path = _write_file(root / "inbox" / "IMG_20240111.jpg", b"dup-content")
    dup_path = _write_file(root / "inbox" / "dup_copy.jpg", b"dup-content")
    _write_file(root / "inbox" / "unsupported.customext", b"unsupported")
    planner.plan_run(run.id, [noop_path, move_path, dup_path, root / "inbox" / "unsupported.customext"])
    return run.id, root


def test_cli_apply_happy_path_mixed_actions_and_no_fs_mutation(
    tmp_path: Path, test_database_url: str, session_factory, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    run_id, root = _create_planned_run(tmp_path, session_factory)

    before = _snapshot_files(root)
    exit_code = main(["apply", str(run_id)])
    after = _snapshot_files(root)

    assert exit_code == 0
    assert before == after

    stdout = capsys.readouterr().out
    assert "MOVE" in stdout
    assert "DUPLICATE" in stdout
    assert "NOOP" in stdout
    assert "Summary" in stdout
    assert "  Files applied: 3" in stdout
    assert "  Moves: 1" in stdout
    assert "  Duplicates: 1" in stdout
    assert "  No-op: 1" in stdout
    assert "  Skipped: 0" in stdout
    assert "  Errors: 0" in stdout

    with session_factory() as session:
        run = session.scalar(select(Run).where(Run.id == run_id))
        assert run is not None
        assert run.state == RunStateDB.COMPLETED


def test_cli_apply_invalid_run_id_returns_error(test_database_url: str, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    exit_code = main(["apply", "invalid-run-id"])
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "Invalid run_id:" in captured.err


def test_cli_apply_non_existent_run_id_returns_error(test_database_url: str, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    missing = uuid.uuid4()
    exit_code = main(["apply", str(missing)])
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "Run not found:" in captured.err


def test_cli_apply_output_deterministic_across_equivalent_runs(
    tmp_path: Path, test_database_url: str, session_factory, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)

    run_id_1, _ = _create_planned_run(tmp_path, session_factory)
    run_id_2, _ = _create_planned_run(tmp_path, session_factory)

    assert main(["apply", str(run_id_1)]) == 0
    first = capsys.readouterr().out
    assert main(["apply", str(run_id_2)]) == 0
    second = capsys.readouterr().out

    assert _normalize_run_id(first) == _normalize_run_id(second)
    assert _extract_run_id(first) == run_id_1
    assert _extract_run_id(second) == run_id_2
