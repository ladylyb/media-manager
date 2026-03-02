from __future__ import annotations

import json
from pathlib import Path

from media_manager.app.cli import main


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _decision_files(root: Path) -> list[Path]:
    return sorted(root.glob("artifacts/decision_trace_*.json"), key=lambda p: p.name)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_deterministic_trace_artifact_equality_across_runs(
    tmp_path: Path,
    test_database_url: str,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.chdir(tmp_path)

    dataset = tmp_path / "dataset"
    _write_file(dataset / "0_long_folder_name" / "really_long_file_name.jpg", b"same-bytes")
    _write_file(dataset / "z.jpg", b"same-bytes")

    assert main(["plan", str(dataset)]) == 0
    assert main(["plan", str(dataset)]) == 0

    artifacts = _decision_files(tmp_path)
    assert len(artifacts) == 2

    first = _load(artifacts[0])
    second = _load(artifacts[1])

    assert first["trace_version"] == "phase10.v1"
    assert second["trace_version"] == "phase10.v1"
    assert first["decisions"] == second["decisions"]


def test_explain_cli_returns_structured_explanation(
    tmp_path: Path,
    test_database_url: str,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.chdir(tmp_path)

    dataset = tmp_path / "dataset"
    _write_file(dataset / "a" / "one.jpg", b"dup")
    _write_file(dataset / "b" / "two.jpg", b"dup")

    assert main(["plan", str(dataset)]) == 0

    artifacts = _decision_files(tmp_path)
    assert artifacts
    payload = _load(artifacts[-1])
    target_file_id = payload["decisions"][0]["candidate_instance_ids"][0]

    assert main(["explain-file", target_file_id]) == 0
    output = capsys.readouterr().out
    assert "File Decision Explanation" in output
    assert "Decision Reason:" in output
    assert "Tie Breaker:" in output
    assert "Candidates:" in output
    assert target_file_id in output


def test_explain_cli_handles_no_trace_artifact(
    tmp_path: Path,
    test_database_url: str,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.chdir(tmp_path)

    assert main(["explain-file", "00000000-0000-0000-0000-000000000000"]) == 1
    err = capsys.readouterr().err
    assert "No decision trace artifact available." in err


def test_explain_cli_handles_file_not_in_trace(
    tmp_path: Path,
    test_database_url: str,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.chdir(tmp_path)

    dataset = tmp_path / "dataset"
    _write_file(dataset / "a" / "one.jpg", b"dup")
    _write_file(dataset / "b" / "two.jpg", b"dup")
    assert main(["plan", str(dataset)]) == 0

    unknown = "00000000-0000-0000-0000-000000000000"
    assert main(["explain-file", unknown]) == 1
    err = capsys.readouterr().err
    assert f"File not found in latest decision trace: {unknown}" in err
