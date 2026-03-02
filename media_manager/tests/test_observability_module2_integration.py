from __future__ import annotations

from pathlib import Path

import pytest

import media_manager.app.observability as observability
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService
from operator_console.main import app as operator_console_app


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _run_planning_flow(tmp_path: Path, session_factory) -> str:
    ingest_service = IngestService(session_factory)
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)

    noop_path = _write_file(tmp_path / "Media" / "Photos" / "2024" / "01" / "IMG_20240110.jpg", b"noop")
    move_path = _write_file(tmp_path / "inbox" / "IMG_20240111.jpg", b"dup-content")
    dup_path = _write_file(tmp_path / "inbox" / "dup_copy.jpg", b"dup-content")
    files = [noop_path, move_path, dup_path]

    ingest_service.ingest_paths(files)
    run = run_service.create_run()
    planner.plan_run(run.id, files, ingest_if_needed=False)
    return str(run.id)


def test_real_operator_console_metrics_exposes_planner_histogram(tmp_path: Path, session_factory) -> None:
    testclient = pytest.importorskip("fastapi.testclient")
    run_id = _run_planning_flow(tmp_path, session_factory)

    response = testclient.TestClient(operator_console_app).get("/metrics/")
    assert response.status_code == 200
    text = response.text
    assert "planner_stage_duration_seconds_bucket" in text
    assert "planner_stage_duration_seconds_count" in text
    assert "planner_stage_duration_seconds_sum" in text
    for stage in ("load_candidates", "metadata_lookup", "action_generation", "persist_actions"):
        assert f'planner_stage_duration_seconds_count{{run_id="{run_id}",stage="{stage}"}}' in text


def test_mount_metrics_endpoint_does_not_depend_on_standalone_server(monkeypatch: pytest.MonkeyPatch) -> None:
    fastapi = pytest.importorskip("fastapi")
    testclient = pytest.importorskip("fastapi.testclient")
    app = fastapi.FastAPI()

    monkeypatch.setattr(observability, "start_http_server", None)
    assert observability.mount_metrics_endpoint(app) is True

    response = testclient.TestClient(app).get("/metrics/")
    assert response.status_code == 200
    assert "planner_stage_duration_seconds" in response.text

