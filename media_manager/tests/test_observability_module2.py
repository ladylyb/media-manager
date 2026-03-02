from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import media_manager.app.observability as observability
import media_manager.app.persistence.planner as planner_module
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService
from operator_console.main import app as operator_console_app


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _build_dataset(tmp_path: Path) -> list[Path]:
    noop_path = _write_file(tmp_path / "Media" / "Photos" / "2024" / "01" / "IMG_20240110.jpg", b"noop")
    move_path = _write_file(tmp_path / "inbox" / "IMG_20240111.jpg", b"dup-content")
    dup_path = _write_file(tmp_path / "inbox" / "dup_copy.jpg", b"dup-content")
    return [noop_path, move_path, dup_path]


def _run_planning_flow(tmp_path: Path, session_factory) -> tuple[str, object]:
    ingest_service = IngestService(session_factory)
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)

    files = _build_dataset(tmp_path)
    ingest_service.ingest_paths(files)
    run = run_service.create_run()
    summary = planner.plan_run(run.id, files, ingest_if_needed=False)
    return str(run.id), summary


def test_histogram_family_visible_on_metrics_endpoint(tmp_path: Path, session_factory) -> None:
    testclient = pytest.importorskip("fastapi.testclient")
    run_id, _ = _run_planning_flow(tmp_path, session_factory)
    client = testclient.TestClient(operator_console_app)

    response = client.get("/metrics/")
    assert response.status_code == 200
    text = response.text
    assert "planner_stage_duration_seconds_bucket" in text
    assert "planner_stage_duration_seconds_sum" in text
    assert "planner_stage_duration_seconds_count" in text
    for stage in ("load_candidates", "metadata_lookup", "action_generation", "persist_actions"):
        assert f'planner_stage_duration_seconds_count{{run_id="{run_id}",stage="{stage}"}}' in text


def test_histogram_observation_failure_is_fail_open(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("histogram helper failure")

    monkeypatch.setattr(planner_module, "record_planner_stage_duration", _raise)

    run_id, summary = _run_planning_flow(tmp_path, session_factory)
    assert str(summary.run_id) == run_id
    assert summary.supported_count >= 1


def test_histogram_recording_is_additive_without_side_effects(tmp_path: Path, session_factory) -> None:
    labels = {"run_id": "phase11-module2-additive", "stage": "action_generation"}
    before = observability.read_counter_value("planner_stage_duration_seconds_count", labels)

    observability.record_planner_stage_duration(labels["run_id"], labels["stage"], 0.02)
    observability.record_planner_stage_duration(labels["run_id"], labels["stage"], 0.03)

    after = observability.read_counter_value("planner_stage_duration_seconds_count", labels)
    assert after - before == 2


def test_label_correctness_across_multiple_run_ids(tmp_path: Path, session_factory) -> None:
    testclient = pytest.importorskip("fastapi.testclient")

    first_id, _ = _run_planning_flow(tmp_path / "run1", session_factory)
    second_id, _ = _run_planning_flow(tmp_path / "run2", session_factory)

    client = testclient.TestClient(operator_console_app)
    text = client.get("/metrics/").text
    for run_id in (first_id, second_id):
        for stage in ("load_candidates", "metadata_lookup", "action_generation", "persist_actions"):
            assert f'planner_stage_duration_seconds_count{{run_id="{run_id}",stage="{stage}"}}' in text


def test_histogram_reload_safety() -> None:
    importlib.reload(observability)
    importlib.reload(observability)
    observability.record_planner_stage_duration("reload-safe-run", "load_candidates", 0.01)
    value = observability.read_counter_value(
        "planner_stage_duration_seconds_count",
        {"run_id": "reload-safe-run", "stage": "load_candidates"},
    )
    assert value >= 1

