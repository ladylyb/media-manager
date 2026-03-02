from __future__ import annotations

from pathlib import Path

import pytest

import media_manager.app.observability as observability
from media_manager.app.observability import mount_metrics_endpoint, read_counter_value, record_ingest_metrics
from media_manager.app.persistence.apply import ApplyService
from media_manager.app.persistence.ingest import IngestService
import media_manager.app.persistence.materialized_reads as materialized_reads
from media_manager.app.persistence.materialized_reads import fetch_canonical_metadata
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService
from operator_console.main import app as operator_console_app


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _build_dataset(root: Path) -> list[Path]:
    first = _write_file(root / "inbox" / "first.jpg", b"first-unique")
    second = _write_file(root / "inbox" / "second.jpg", b"second-unique")
    duplicate = _write_file(root / "inbox" / "second_copy.jpg", b"second-unique")
    return [first, second, duplicate]


def _extract_metric_value(payload: str, metric_name: str, labels: dict[str, str]) -> float:
    metric_line_prefix = f"{metric_name}{{"
    for line in payload.splitlines():
        if not line.startswith(metric_line_prefix):
            continue
        if all(f'{key}="{value}"' in line for key, value in labels.items()):
            raw_value = line.rsplit(" ", maxsplit=1)[-1]
            try:
                return float(raw_value)
            except ValueError:
                return 0.0
    return 0.0


def test_metrics_endpoint_exposes_modules_1_to_4_metric_families(monkeypatch: pytest.MonkeyPatch) -> None:
    fastapi = pytest.importorskip("fastapi")
    testclient = pytest.importorskip("fastapi.testclient")
    monkeypatch.setenv("MEDIA_MANAGER_METRICS_ENABLED", "1")

    app = fastapi.FastAPI()
    assert mount_metrics_endpoint(app) is True

    # Seed labeled series so histogram/counter child lines are present in output.
    record_ingest_metrics(run_id="m5-exists", files_scanned=1, new_contents=1)
    observability.record_ingest_structured_metrics(
        run_id="m5-exists",
        dataset_id="suite",
        policy_name="default",
        files_scanned=1,
        new_contents=1,
        new_instances=1,
        duplicates_detected=0,
        hash_latencies_ms=[1.0],
        db_write_latencies_ms=[1.0],
    )
    observability.record_planner_stage_duration("m5-exists", "load_candidates", 0.001)
    observability.record_canonical_read_cache_metrics("m5-exists", "base", cache_hits=1, cache_misses=1)

    response = testclient.TestClient(app).get("/metrics")
    assert response.status_code == 200
    text = response.text

    # Module 2 histogram family.
    assert "planner_stage_duration_seconds_bucket" in text
    assert "planner_stage_duration_seconds_sum" in text
    assert "planner_stage_duration_seconds_count" in text

    # Module 3 cache metrics.
    assert "canonical_read_cache_hits_total" in text
    assert "canonical_read_cache_misses_total" in text
    assert "canonical_read_cache_hit_ratio_percent" in text

    # Module 4 structured ingest metrics.
    assert "files_scanned_total" in text
    assert "new_contents_total" in text
    assert "new_instances_total" in text
    assert "duplicates_detected_total" in text
    assert "hash_time_total_ms_bucket" in text
    assert "db_write_time_total_ms_bucket" in text

    # Legacy counters preserved.
    assert "ingest_files_scanned_total" in text
    assert "ingest_new_contents_total" in text
    assert "planner_actions_generated_total" in text
    assert "apply_actions_executed_total" in text


def test_deterministic_ingest_updates_structured_counters_and_histograms(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEDIA_MANAGER_METRICS_ENABLED", "1")
    ingest = IngestService(session_factory)
    files = _build_dataset(tmp_path / "dataset")
    labels = {"run_id": "none", "dataset_id": "unknown", "policy_name": "default"}

    before_scanned = read_counter_value("files_scanned_total", labels)
    before_contents = read_counter_value("new_contents_total", labels)
    before_duplicates = read_counter_value("duplicates_detected_total", labels)
    before_hash_count = read_counter_value("hash_time_total_ms_count", labels)
    before_hash_sum = read_counter_value("hash_time_total_ms_sum", labels)
    before_db_count = read_counter_value("db_write_time_total_ms_count", labels)
    before_db_sum = read_counter_value("db_write_time_total_ms_sum", labels)

    summary = ingest.ingest_paths(files)
    assert summary.files_scanned == 3
    assert summary.new_contents == 2
    assert summary.duplicates_detected == 1

    after_scanned = read_counter_value("files_scanned_total", labels)
    after_contents = read_counter_value("new_contents_total", labels)
    after_duplicates = read_counter_value("duplicates_detected_total", labels)
    after_hash_count = read_counter_value("hash_time_total_ms_count", labels)
    after_hash_sum = read_counter_value("hash_time_total_ms_sum", labels)
    after_db_count = read_counter_value("db_write_time_total_ms_count", labels)
    after_db_sum = read_counter_value("db_write_time_total_ms_sum", labels)

    assert after_scanned - before_scanned == 3
    assert after_contents - before_contents == 2
    assert after_duplicates - before_duplicates == 1
    assert after_hash_count - before_hash_count == 3
    assert after_db_count - before_db_count == 3
    assert after_hash_sum - before_hash_sum > 0.0
    assert after_db_sum - before_db_sum > 0.0


def test_planner_duration_histogram_is_recorded_and_monotonic(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEDIA_MANAGER_METRICS_ENABLED", "1")
    ingest = IngestService(session_factory)
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    files = _build_dataset(tmp_path / "planner")

    ingest.ingest_paths(files)
    first_run = run_service.create_run()
    first_summary = planner.plan_run(first_run.id, files, ingest_if_needed=False)

    labels = {"run_id": str(first_run.id), "stage": "action_generation"}
    first_count = read_counter_value("planner_stage_duration_seconds_count", labels)
    first_sum = read_counter_value("planner_stage_duration_seconds_sum", labels)
    assert first_count >= 1
    assert first_sum > 0.0

    second_run = run_service.create_run()
    second_summary = planner.plan_run(second_run.id, files, ingest_if_needed=False)

    assert (
        first_summary.scanned_count,
        first_summary.supported_count,
        first_summary.skipped_count,
        first_summary.move_actions,
        first_summary.noop_actions,
        first_summary.duplicate_actions,
    ) == (
        second_summary.scanned_count,
        second_summary.supported_count,
        second_summary.skipped_count,
        second_summary.move_actions,
        second_summary.noop_actions,
        second_summary.duplicate_actions,
    )

    second_labels = {"run_id": str(second_run.id), "stage": "action_generation"}
    second_count = read_counter_value("planner_stage_duration_seconds_count", second_labels)
    second_sum = read_counter_value("planner_stage_duration_seconds_sum", second_labels)
    assert second_count >= 1
    assert second_sum > 0.0


def test_cache_hit_ratio_metrics_are_correct_for_repeat_reads(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CANONICAL_READ_CACHE_ENABLED", "true")
    ingest = IngestService(session_factory)
    files = _build_dataset(tmp_path / "cache")
    ingest.ingest_paths(files)

    # Deterministic cache counters require a known-empty cache for the first read.
    materialized_reads._READ_CACHE.clear()
    labels = {"run_id": "m5-test", "source": "base"}
    before_hits = read_counter_value("canonical_read_cache_hits_total", labels)
    before_misses = read_counter_value("canonical_read_cache_misses_total", labels)

    with session_factory() as session:
        first = fetch_canonical_metadata(
            session,
            use_mv=False,
            sample_size=1000,
            use_cache=None,
            metrics_run_id="m5-test",
        )
        second = fetch_canonical_metadata(
            session,
            use_mv=False,
            sample_size=1000,
            use_cache=None,
            metrics_run_id="m5-test",
        )

    assert len(first) >= 1
    assert len(second) >= 1
    after_hits = read_counter_value("canonical_read_cache_hits_total", labels)
    after_misses = read_counter_value("canonical_read_cache_misses_total", labels)
    ratio_percent = read_counter_value("canonical_read_cache_hit_ratio_percent", labels)

    assert after_misses - before_misses == 1
    assert after_hits - before_hits == 1
    assert ratio_percent == 50.0


def test_disabled_metrics_mode_skips_structured_ingest_updates_but_runtime_remains_healthy(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    testclient = pytest.importorskip("fastapi.testclient")
    monkeypatch.setenv("MEDIA_MANAGER_METRICS_ENABLED", "0")

    ingest = IngestService(session_factory)
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    apply_service = ApplyService(session_factory)
    files = _build_dataset(tmp_path / "disabled")
    labels = {"run_id": "none", "dataset_id": "unknown", "policy_name": "default"}

    before_scanned = read_counter_value("files_scanned_total", labels)
    before_hash_count = read_counter_value("hash_time_total_ms_count", labels)

    ingest_summary = ingest.ingest_paths(files)
    run = run_service.create_run()
    plan_summary = planner.plan_run(run.id, files, ingest_if_needed=False)
    apply_summary = apply_service.apply_run(run.id)

    assert ingest_summary.files_scanned == 3
    assert plan_summary.run_id == run.id
    assert apply_summary.errors_count == 0

    after_scanned = read_counter_value("files_scanned_total", labels)
    after_hash_count = read_counter_value("hash_time_total_ms_count", labels)
    assert after_scanned - before_scanned == 0
    assert after_hash_count - before_hash_count == 0

    response = testclient.TestClient(operator_console_app).get("/metrics/")
    assert response.status_code == 200
    payload = response.text
    assert "files_scanned_total" in payload

    # Basic payload parsing guard for deterministic endpoint output.
    assert _extract_metric_value(payload, "files_scanned_total", labels) == after_scanned
