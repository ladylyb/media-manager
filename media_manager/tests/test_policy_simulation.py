from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import text

from media_manager.app.cli import main
from media_manager.app.persistence.base import create_db_engine, create_session_factory
from media_manager.app.persistence.ingest import IngestService


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _simulation_files(root: Path) -> list[Path]:
    return sorted(root.glob("artifacts/simulation_delta_*.json"), key=lambda p: p.name)


def _payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _public_counts(db_url: str) -> dict[str, int]:
    engine = create_db_engine(db_url)
    with engine.begin() as conn:
        return {
            "runs": conn.execute(text("SELECT COUNT(*) FROM runs")).scalar_one(),
            "planned_actions": conn.execute(text("SELECT COUNT(*) FROM planned_actions")).scalar_one(),
            "canonical_assignments": conn.execute(text("SELECT COUNT(*) FROM canonical_assignments")).scalar_one(),
            "canonical_recompute_runs": conn.execute(text("SELECT COUNT(*) FROM canonical_recompute_runs")).scalar_one(),
            "canonical_recompute_items": conn.execute(text("SELECT COUNT(*) FROM canonical_recompute_items")).scalar_one(),
        }


def test_simulation_produces_no_db_mutation(
    tmp_path: Path,
    test_database_url: str,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.chdir(tmp_path)

    dataset = tmp_path / "dataset"
    _write_file(dataset / "0_long_folder_name" / "really_long_file_name.jpg", b"same-content")
    _write_file(dataset / "z.jpg", b"same-content")

    ingest = IngestService(create_session_factory(create_db_engine(test_database_url)))
    ingest.ingest_path(dataset)

    before = _public_counts(test_database_url)
    assert main(["plan", str(dataset), "--simulate-policy", "--policy", "SHORTEST_PATH"]) == 0
    after = _public_counts(test_database_url)

    assert before == after
    output = capsys.readouterr().out
    assert "Policy Simulation Summary" in output
    assert "Canonical Changes:" in output


def test_delta_summary_matches_expected_canonical_changes(
    tmp_path: Path,
    test_database_url: str,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.chdir(tmp_path)

    dataset = tmp_path / "dataset"
    _write_file(dataset / "0_long_folder_name" / "really_long_file_name.jpg", b"same-content")
    _write_file(dataset / "z.jpg", b"same-content")

    ingest = IngestService(create_session_factory(create_db_engine(test_database_url)))
    ingest.ingest_path(dataset)

    assert main(["plan", str(dataset), "--simulate-policy", "--policy", "SHORTEST_PATH"]) == 0
    artifacts = _simulation_files(tmp_path)
    assert artifacts
    delta = _payload(artifacts[-1])

    assert delta["canonical_changes_count"] == 1
    assert delta["demotions_count"] == 1
    assert delta["merges_count"] == 0
    assert len(delta["impacted_content_ids"]) == 1


def test_simulation_idempotent_across_repeated_execution(
    tmp_path: Path,
    test_database_url: str,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.chdir(tmp_path)

    dataset = tmp_path / "dataset"
    _write_file(dataset / "0_long_folder_name" / "really_long_file_name.jpg", b"same-content")
    _write_file(dataset / "z.jpg", b"same-content")

    ingest = IngestService(create_session_factory(create_db_engine(test_database_url)))
    ingest.ingest_path(dataset)

    assert main(["plan", str(dataset), "--simulate-policy", "--policy", "SHORTEST_PATH"]) == 0
    assert main(["plan", str(dataset), "--simulate-policy", "--policy", "SHORTEST_PATH"]) == 0

    artifacts = _simulation_files(tmp_path)
    assert len(artifacts) == 2

    first = _payload(artifacts[0])
    second = _payload(artifacts[1])

    first_without_run_id = {key: value for key, value in first.items() if key != "run_id"}
    second_without_run_id = {key: value for key, value in second.items() if key != "run_id"}
    assert first_without_run_id == second_without_run_id
