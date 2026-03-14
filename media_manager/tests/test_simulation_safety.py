from __future__ import annotations

import os
import shutil
from pathlib import Path

from media_manager.app.cli import main


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_simulation_mode_non_mutation_guarantee(
    tmp_path: Path,
    test_database_url: str,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.chdir(tmp_path)

    dataset = tmp_path / "dataset"
    _write_file(dataset / "a" / "one.jpg", b"same")
    _write_file(dataset / "b" / "two.jpg", b"same")

    fs_calls = {"remove": 0, "move": 0}
    commit_calls = {"count": 0}
    apply_calls = {"count": 0}

    def _remove_guard(*args, **kwargs):  # type: ignore[no-untyped-def]
        fs_calls["remove"] += 1
        raise AssertionError("os.remove must not be called during simulation")

    def _move_guard(*args, **kwargs):  # type: ignore[no-untyped-def]
        fs_calls["move"] += 1
        raise AssertionError("shutil.move must not be called during simulation")

    def _commit_guard(*args, **kwargs):  # type: ignore[no-untyped-def]
        commit_calls["count"] += 1

    def _apply_guard(*args, **kwargs):  # type: ignore[no-untyped-def]
        apply_calls["count"] += 1
        raise AssertionError("ApplyService.apply_run must not be called during simulation")

    monkeypatch.setattr(os, "remove", _remove_guard)
    monkeypatch.setattr(shutil, "move", _move_guard)

    import sqlalchemy.orm.session as orm_session
    import media_manager.app.persistence.apply as apply_module

    monkeypatch.setattr(orm_session.Session, "commit", _commit_guard)
    monkeypatch.setattr(apply_module.ApplyService, "apply_run", _apply_guard)

    exit_code = main(["plan", str(dataset), "--simulate-policy", "--policy", "SHORTEST_PATH"])
    assert exit_code == 0

    decision_artifacts = sorted((tmp_path / "artifacts").glob("decision_trace_*.json"))
    simulation_artifacts = sorted((tmp_path / "artifacts").glob("simulation_delta_*.json"))

    assert decision_artifacts == []
    assert len(simulation_artifacts) == 1
    assert fs_calls == {"remove": 0, "move": 0}
    assert apply_calls["count"] == 0
    assert commit_calls["count"] == 0
