from __future__ import annotations

import re
from pathlib import Path

from media_manager.app.cli import main


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _names(glob_root: Path, pattern: str) -> list[str]:
    return sorted(path.name for path in glob_root.glob(pattern))


def test_decision_trace_and_simulation_artifact_filenames_are_unique(
    tmp_path: Path,
    test_database_url: str,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.chdir(tmp_path)

    dataset = tmp_path / "dataset"
    _write_file(dataset / "a" / "one.jpg", b"same")
    _write_file(dataset / "b" / "two.jpg", b"same")

    assert main(["plan", str(dataset)]) == 0
    assert main(["plan", str(dataset)]) == 0
    decision_names = _names(tmp_path / "artifacts", "decision_trace_*.json")

    assert len(decision_names) == 2
    assert len(set(decision_names)) == 2
    for name in decision_names:
        assert re.fullmatch(r"decision_trace_[0-9a-f\-]{36}\.json", name)

    assert main(["plan", str(dataset), "--simulate-policy", "--policy", "SHORTEST_PATH"]) == 0
    assert main(["plan", str(dataset), "--simulate-policy", "--policy", "SHORTEST_PATH"]) == 0
    simulation_names = _names(tmp_path / "artifacts", "simulation_delta_*.json")

    assert len(simulation_names) == 2
    assert len(set(simulation_names)) == 2
    for name in simulation_names:
        assert re.fullmatch(r"simulation_delta_[0-9a-f\-]{36}\.json", name)
