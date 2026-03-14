from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import func, select

from media_manager.app.cli import main
from media_manager.app.persistence.models import CanonicalAssignment


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _normalize_run_id(output: str) -> str:
    return re.sub(r"Run ID:\s+[0-9a-fA-F-]{36}", "Run ID: <uuid>", output)


def test_cli_canonical_recompute_defaults_to_dry_run(
    tmp_path: Path, test_database_url: str, monkeypatch, capsys, session_factory
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    root = tmp_path / "dataset"
    _write_file(root / "a.jpg", b"same")
    _write_file(root / "copy" / "a_copy.jpg", b"same")
    assert main(["ingest", str(root)]) == 0

    with session_factory() as session:
        before = session.scalar(select(func.count()).select_from(CanonicalAssignment))
    exit_code = main(["canonical", "recompute", "--policy", "SHORTEST_PATH"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Canonical Recompute Summary" in output
    with session_factory() as session:
        after = session.scalar(select(func.count()).select_from(CanonicalAssignment))
    assert before == after


def test_cli_canonical_recompute_apply_inserts_rows(
    tmp_path: Path, test_database_url: str, monkeypatch, session_factory
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    root = tmp_path / "dataset"
    _write_file(root / "longer" / "file_a.jpg", b"same")
    _write_file(root / "a.jpg", b"same")
    assert main(["ingest", str(root)]) == 0
    with session_factory() as session:
        before = session.scalar(select(func.count()).select_from(CanonicalAssignment))
    assert (
        main(
            [
                "canonical",
                "recompute",
                "--policy",
                "PREFER_ROOT",
                "--preferred-root",
                str((root / "longer").resolve(strict=False)),
                "--apply",
            ]
        )
        == 0
    )
    with session_factory() as session:
        after = session.scalar(select(func.count()).select_from(CanonicalAssignment))
    assert after == before + 1


def test_cli_canonical_recompute_invalid_policy_returns_error(
    test_database_url: str, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    exit_code = main(["canonical", "recompute", "--policy", "NOT_REAL"])
    assert exit_code == 1
    assert "Unknown canonical policy" in capsys.readouterr().err


def test_cli_canonical_recompute_conflicting_flags_return_usage_error(
    test_database_url: str, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    exit_code = main(["canonical", "recompute", "--policy", "FIRST_SEEN", "--dry-run", "--apply"])
    assert exit_code == 2
    assert "Specify only one of --dry-run or --apply." in capsys.readouterr().err


def test_cli_canonical_recompute_output_is_deterministic_across_runs(
    tmp_path: Path, test_database_url: str, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    root = tmp_path / "dataset"
    _write_file(root / "a.jpg", b"same")
    _write_file(root / "copy" / "a_copy.jpg", b"same")
    assert main(["ingest", str(root)]) == 0
    _ = capsys.readouterr()

    assert main(["canonical", "recompute", "--policy", "SHORTEST_PATH"]) == 0
    first = capsys.readouterr().out
    assert main(["canonical", "recompute", "--policy", "SHORTEST_PATH"]) == 0
    second = capsys.readouterr().out
    assert _normalize_run_id(first) == _normalize_run_id(second)
