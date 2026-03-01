from __future__ import annotations

from pathlib import Path

from media_manager.app.cli import main


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

