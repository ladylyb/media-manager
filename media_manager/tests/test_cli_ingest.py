from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from media_manager.app.cli import main
from media_manager.app.persistence.base import create_db_engine, create_session_factory
from media_manager.app.persistence.models import FileContent, FileInstance, MediaFile


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_cli_ingest_happy_path(tmp_path: Path, test_database_url: str, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    root = tmp_path / "dataset"
    _write_file(root / "a.jpg", b"a")
    _write_file(root / "b.jpg", b"b")
    exit_code = main(["ingest", str(root)])
    assert exit_code == 0
    stdout = capsys.readouterr().out
    assert "Ingest Summary" in stdout
    assert "Files scanned: 2" in stdout


def test_cli_ingest_invalid_path(tmp_path: Path, test_database_url: str, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    exit_code = main(["ingest", str(tmp_path / "missing")])
    assert exit_code != 0
    stderr = capsys.readouterr().err
    assert "Path does not exist:" in stderr


def test_cli_ingest_dry_run_is_read_only(tmp_path: Path, test_database_url: str, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    root = tmp_path / "dataset"
    _write_file(root / "a.jpg", b"a")

    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        before = (
            len(session.scalars(select(MediaFile)).all()),
            len(session.scalars(select(FileContent)).all()),
            len(session.scalars(select(FileInstance)).all()),
        )

    exit_code = main(["ingest", str(root), "--dry-run"])
    assert exit_code == 0
    stdout = capsys.readouterr().out
    assert "Ingest Validation (Dry Run)" in stdout
    assert "Would insert: 1" in stdout

    with session_factory() as session:
        after = (
            len(session.scalars(select(MediaFile)).all()),
            len(session.scalars(select(FileContent)).all()),
            len(session.scalars(select(FileInstance)).all()),
        )
    assert after == before


def test_cli_ingest_dry_run_json_output(tmp_path: Path, test_database_url: str, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    root = tmp_path / "dataset"
    _write_file(root / "a.jpg", b"a")

    exit_code = main(["ingest", str(root), "--dry-run", "--json"])
    assert exit_code == 0
    stdout = capsys.readouterr().out
    assert '"mode": "VALIDATION_ONLY"' in stdout
    assert '"would_insert": 1' in stdout


def test_cli_ingest_json_output_for_execute_mode(tmp_path: Path, test_database_url: str, monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    root = tmp_path / "dataset"
    _write_file(root / "a.jpg", b"a")
    root.mkdir(parents=True, exist_ok=True)
    exit_code = main(["ingest", str(root), "--json"])
    assert exit_code == 0
    payload = capsys.readouterr().out
    assert '"ok": true' in payload.lower()
    assert '"files_scanned": 1' in payload
