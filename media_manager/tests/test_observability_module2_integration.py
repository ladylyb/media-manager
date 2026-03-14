from __future__ import annotations

from pathlib import Path

import pytest

import media_manager.app.observability as observability
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.materialized_reads import fetch_canonical_metadata, refresh_materialized_view
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


def test_metrics_endpoint_exposes_canonical_cache_series_for_base_and_mv_with_none_run_id(
    tmp_path: Path,
    test_database_url: str,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    testclient = pytest.importorskip("fastapi.testclient")
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("CANONICAL_READ_CACHE_ENABLED", "true")
    run_id = _run_planning_flow(tmp_path, session_factory)
    assert run_id

    from media_manager.app.persistence.base import create_db_engine

    engine = create_db_engine(test_database_url)
    refresh_materialized_view(engine, concurrently=False)

    with session_factory() as session:
        fetch_canonical_metadata(session, use_mv=False, sample_size=1000, use_cache=None, metrics_run_id=None)
        fetch_canonical_metadata(session, use_mv=True, sample_size=1000, use_cache=None, metrics_run_id=None)

    response = testclient.TestClient(operator_console_app).get("/metrics/")
    assert response.status_code == 200
    text = response.text
    assert 'canonical_read_cache_hit_ratio_percent{run_id="none",source="base"}' in text
    assert 'canonical_read_cache_hit_ratio_percent{run_id="none",source="mv"}' in text
    assert observability.read_counter_value(
        "canonical_read_cache_misses_total", {"run_id": "none", "source": "base"}
    ) >= 1
    assert observability.read_counter_value("canonical_read_cache_misses_total", {"run_id": "none", "source": "mv"}) >= 1
