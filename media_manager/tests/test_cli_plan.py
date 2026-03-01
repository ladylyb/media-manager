from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

from sqlalchemy import select

from media_manager.app.cli import main
from media_manager.app.persistence.models import FileInstance, PlannedAction, Run, RunStateDB


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


def test_cli_plan_empty_directory(tmp_path: Path, test_database_url: str, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    empty = tmp_path / "empty"
    empty.mkdir(parents=True, exist_ok=True)

    exit_code = main(["plan", str(empty)])
    assert exit_code == 0

    stdout = capsys.readouterr().out
    assert "Summary" in stdout
    assert "  Files scanned: 0" in stdout
    assert "  Moves: 0" in stdout
    assert "  Duplicates: 0" in stdout
    assert "  No-op: 0" in stdout
    assert "  Skipped: 0" in stdout


def test_cli_plan_mixed_actions_and_no_fs_mutation(
    tmp_path: Path, test_database_url: str, session_factory, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)

    root = tmp_path / "dataset"
    noop_path = _write_file(root / "Media" / "Photos" / "2024" / "01" / "IMG_20240110.jpg", b"noop")
    move_path = _write_file(root / "inbox" / "IMG_20240111.jpg", b"dup-content")
    _write_file(root / "inbox" / "dup_copy.jpg", b"dup-content")
    unsupported = _write_file(root / "inbox" / "unsupported.customext", b"unsupported")

    before = _snapshot_files(root)
    exit_code = main(["plan", str(root)])
    after = _snapshot_files(root)
    assert exit_code == 0
    assert before == after

    stdout = capsys.readouterr().out
    assert "MOVE" in stdout
    assert "DUPLICATE" in stdout
    assert "NOOP" not in stdout
    assert "Summary" in stdout
    assert "  Files scanned: 2" in stdout
    assert "  Moves: 1" in stdout
    assert "  Duplicates: 1" in stdout
    assert "  No-op: 0" in stdout
    assert "  Skipped: 1" in stdout

    run_id = _extract_run_id(stdout)
    with session_factory() as session:
        run = session.scalar(select(Run).where(Run.id == run_id))
        assert run is not None
        assert run.state == RunStateDB.PLANNED

        actions = session.scalars(select(PlannedAction).where(PlannedAction.run_id == run_id)).all()
        assert len(actions) == 2
        assert all(unsupported.as_posix() not in action.source_path.replace("\\", "/") for action in actions)

        file_rows = session.scalars(select(FileInstance)).all()
        assert unsupported.as_posix() in {row.absolute_path.replace("\\", "/") for row in file_rows}
        assert noop_path.as_posix() in {row.absolute_path.replace("\\", "/") for row in file_rows}
        assert move_path.as_posix() in {row.absolute_path.replace("\\", "/") for row in file_rows}


def test_cli_plan_output_deterministic_across_runs(
    tmp_path: Path, test_database_url: str, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)

    root = tmp_path / "dataset"
    _write_file(root / "Media" / "Photos" / "2024" / "01" / "IMG_20240110.jpg", b"noop")
    _write_file(root / "inbox" / "IMG_20240111.jpg", b"dup-content")
    _write_file(root / "inbox" / "dup_copy.jpg", b"dup-content")
    _write_file(root / "inbox" / "unsupported.customext", b"unsupported")

    assert main(["plan", str(root)]) == 0
    first = capsys.readouterr().out
    assert main(["plan", str(root)]) == 0
    second = capsys.readouterr().out

    assert _normalize_run_id(first) == _normalize_run_id(second)


def test_cli_plan_invalid_path_returns_error(test_database_url: str, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    missing = Path("does-not-exist-12345")

    exit_code = main(["plan", str(missing)])
    assert exit_code != 0

    captured = capsys.readouterr()
    assert "Path does not exist:" in captured.err
