from __future__ import annotations

import importlib
import socket
import time
from pathlib import Path

import pytest
from sqlalchemy import select

import media_manager.app.observability as observability
import media_manager.app.persistence.apply as apply_module
import media_manager.app.persistence.ingest as ingest_module
import media_manager.app.persistence.planner as planner_module
from media_manager.app.observability import (
    mount_metrics_endpoint,
    read_counter_value,
    record_canonical_read_cache_disabled,
    record_canonical_read_cache_metrics,
    record_apply_metrics,
    record_ingest_metrics,
    record_planner_metrics,
    start_metrics_http_server_if_enabled,
)
from media_manager.app.persistence.apply import ApplyService
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.models import Run, RunStateDB
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService
from operator_console.main import app as operator_console_app
from operator_console.main import create_app as create_operator_console_app


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def test_metrics_endpoint_exists_and_exposes_prometheus_payload() -> None:
    fastapi = pytest.importorskip("fastapi")
    testclient = pytest.importorskip("fastapi.testclient")
    app = fastapi.FastAPI()
    assert mount_metrics_endpoint(app) is True

    record_ingest_metrics(run_id="endpoint-test", files_scanned=1, new_contents=1)
    record_planner_metrics(run_id="endpoint-test", actions_generated=1)
    record_apply_metrics(run_id="endpoint-test", actions_executed=1)
    record_canonical_read_cache_metrics(run_id="endpoint-test", source="mv", cache_hits=1, cache_misses=1)

    client = testclient.TestClient(app)
    response = client.get("/metrics")
    assert response.status_code == 200
    text = response.text
    assert "ingest_files_scanned_total" in text
    assert "ingest_new_contents_total" in text
    assert "planner_actions_generated_total" in text
    assert "apply_actions_executed_total" in text
    assert "canonical_read_cache_hits_total" in text
    assert "canonical_read_cache_misses_total" in text
    assert "canonical_read_cache_hit_ratio_percent" in text
    assert (
        "process_cpu_seconds_total" in text
        or "python_gc_objects_collected_total" in text
        or "python_info" in text
    )


def test_real_operator_console_app_exposes_metrics() -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    client = fastapi_testclient.TestClient(operator_console_app)

    record_ingest_metrics(run_id="operator-app", files_scanned=1, new_contents=1)
    response = client.get("/metrics/")
    assert response.status_code == 200
    text = response.text
    assert "ingest_files_scanned_total" in text
    assert "ingest_new_contents_total" in text
    assert "planner_actions_generated_total" in text
    assert "apply_actions_executed_total" in text


def test_repeated_create_app_calls_keep_metrics_endpoint_healthy() -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    app_one = create_operator_console_app()
    app_two = create_operator_console_app()
    record_ingest_metrics(run_id="repeat-app", files_scanned=1, new_contents=1)

    first = fastapi_testclient.TestClient(app_one).get("/metrics/")
    second = fastapi_testclient.TestClient(app_two).get("/metrics/")
    assert first.status_code == 200
    assert second.status_code == 200
    assert "ingest_files_scanned_total" in first.text
    assert "ingest_files_scanned_total" in second.text


def test_observability_module_reload_is_safe() -> None:
    importlib.reload(observability)
    importlib.reload(observability)
    record_ingest_metrics(run_id="reload-safe", files_scanned=1, new_contents=1)
    value = read_counter_value("ingest_files_scanned_total", {"run_id": "reload-safe", "phase": "ingest"})
    assert value >= 1


def test_counter_helpers_increment_expected_values() -> None:
    ingest_labels = {"run_id": "helper-run", "phase": "ingest"}
    planner_labels = {"run_id": "helper-run", "phase": "plan"}
    apply_labels = {"run_id": "helper-run", "phase": "apply"}

    before_scanned = read_counter_value("ingest_files_scanned_total", ingest_labels)
    before_new = read_counter_value("ingest_new_contents_total", ingest_labels)
    before_plan = read_counter_value("planner_actions_generated_total", planner_labels)
    before_apply = read_counter_value("apply_actions_executed_total", apply_labels)

    record_ingest_metrics(run_id="helper-run", files_scanned=3, new_contents=2)
    record_planner_metrics(run_id="helper-run", actions_generated=5)
    record_apply_metrics(run_id="helper-run", actions_executed=4)

    after_scanned = read_counter_value("ingest_files_scanned_total", ingest_labels)
    after_new = read_counter_value("ingest_new_contents_total", ingest_labels)
    after_plan = read_counter_value("planner_actions_generated_total", planner_labels)
    after_apply = read_counter_value("apply_actions_executed_total", apply_labels)

    assert after_scanned - before_scanned == 3
    assert after_new - before_new == 2
    assert after_plan - before_plan == 5
    assert after_apply - before_apply == 4


def test_canonical_read_cache_metric_helpers_update_expected_values() -> None:
    labels = {"run_id": "helper-cache-run", "source": "mv"}
    before_hits = read_counter_value("canonical_read_cache_hits_total", labels)
    before_misses = read_counter_value("canonical_read_cache_misses_total", labels)

    record_canonical_read_cache_metrics(run_id="helper-cache-run", source="mv", cache_hits=1, cache_misses=1)
    record_canonical_read_cache_metrics(run_id="helper-cache-run", source="mv", cache_hits=2, cache_misses=1)

    after_hits = read_counter_value("canonical_read_cache_hits_total", labels)
    after_misses = read_counter_value("canonical_read_cache_misses_total", labels)
    ratio_percent = read_counter_value("canonical_read_cache_hit_ratio_percent", labels)

    assert after_hits - before_hits == 2
    assert after_misses - before_misses == 1
    assert ratio_percent == pytest.approx(66.6666666666, abs=0.001)

    record_canonical_read_cache_disabled(run_id="helper-cache-run", source="mv")
    disabled_ratio = read_counter_value("canonical_read_cache_hit_ratio_percent", labels)
    assert disabled_ratio == 0.0


def test_canonical_read_cache_metric_helper_normalizes_none_and_non_string_run_id() -> None:
    none_labels = {"run_id": "none", "source": "base"}
    numeric_labels = {"run_id": "123", "source": "base"}

    before_none = read_counter_value("canonical_read_cache_hit_ratio_percent", none_labels)
    before_numeric = read_counter_value("canonical_read_cache_hit_ratio_percent", numeric_labels)

    record_canonical_read_cache_metrics(run_id=None, source="base", cache_hits=0, cache_misses=1)
    record_canonical_read_cache_metrics(run_id=123, source="base", cache_hits=1, cache_misses=1)  # type: ignore[arg-type]

    after_none = read_counter_value("canonical_read_cache_hit_ratio_percent", none_labels)
    after_numeric = read_counter_value("canonical_read_cache_hit_ratio_percent", numeric_labels)

    assert after_none != before_none or after_none == 0.0
    assert after_numeric == 50.0


def test_canonical_read_cache_metric_helper_ignores_out_of_order_snapshots_for_counter_deltas() -> None:
    labels = {"run_id": "out-of-order-run", "source": "mv"}
    before_hits = read_counter_value("canonical_read_cache_hits_total", labels)
    before_misses = read_counter_value("canonical_read_cache_misses_total", labels)

    record_canonical_read_cache_metrics(run_id="out-of-order-run", source="mv", cache_hits=10, cache_misses=5)
    record_canonical_read_cache_metrics(run_id="out-of-order-run", source="mv", cache_hits=7, cache_misses=3)
    record_canonical_read_cache_metrics(run_id="out-of-order-run", source="mv", cache_hits=11, cache_misses=6)

    after_hits = read_counter_value("canonical_read_cache_hits_total", labels)
    after_misses = read_counter_value("canonical_read_cache_misses_total", labels)

    assert after_hits - before_hits == 11
    assert after_misses - before_misses == 6


def test_counters_increment_correctly_under_concurrent_updates() -> None:
    labels = {"run_id": "concurrent-run", "phase": "plan"}
    before = read_counter_value("planner_actions_generated_total", labels)

    total_threads = 20
    increments_per_thread = 50

    import threading

    def _worker() -> None:
        for _ in range(increments_per_thread):
            record_planner_metrics(run_id="concurrent-run", actions_generated=1)

    threads = [threading.Thread(target=_worker) for _ in range(total_threads)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    after = read_counter_value("planner_actions_generated_total", labels)
    assert after - before == total_threads * increments_per_thread


def test_counters_increment_for_ingest_plan_apply_flow(tmp_path: Path, session_factory) -> None:
    ingest_service = IngestService(session_factory)
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    apply_service = ApplyService(session_factory)

    noop_path = _write_file(tmp_path / "Media" / "Photos" / "2024" / "01" / "IMG_20240110.jpg", b"noop")
    move_path = _write_file(tmp_path / "inbox" / "IMG_20240111.jpg", b"dup-content")
    dup_path = _write_file(tmp_path / "inbox" / "dup_copy.jpg", b"dup-content")

    ingest_labels = {"run_id": "none", "phase": "ingest"}
    before_scanned = read_counter_value("ingest_files_scanned_total", ingest_labels)
    before_new = read_counter_value("ingest_new_contents_total", ingest_labels)
    ingest_summary = ingest_service.ingest_paths([noop_path, move_path, dup_path])
    after_scanned = read_counter_value("ingest_files_scanned_total", ingest_labels)
    after_new = read_counter_value("ingest_new_contents_total", ingest_labels)

    assert after_scanned - before_scanned == ingest_summary.files_scanned
    assert after_new - before_new == ingest_summary.new_contents

    run = run_service.create_run()
    planner_labels = {"run_id": str(run.id), "phase": "plan"}
    before_plan = read_counter_value("planner_actions_generated_total", planner_labels)
    plan_summary = planner.plan_run(run.id, [noop_path, move_path, dup_path], ingest_if_needed=False)
    after_plan = read_counter_value("planner_actions_generated_total", planner_labels)

    planned_actions = plan_summary.move_actions + plan_summary.noop_actions + plan_summary.duplicate_actions
    assert after_plan - before_plan == planned_actions

    apply_labels = {"run_id": str(run.id), "phase": "apply"}
    before_apply = read_counter_value("apply_actions_executed_total", apply_labels)
    apply_summary = apply_service.apply_run(run.id)
    after_apply = read_counter_value("apply_actions_executed_total", apply_labels)

    assert after_apply - before_apply == apply_summary.applied_count + apply_summary.skipped_count


def test_metrics_server_start_is_opt_in_and_non_blocking(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = _free_port()
    monkeypatch.setenv("MEDIA_MANAGER_METRICS_ENABLED", "1")
    monkeypatch.setenv("MEDIA_MANAGER_METRICS_PORT", str(port))

    start = time.perf_counter()
    assert start_metrics_http_server_if_enabled() is True

    ingest_service = IngestService(session_factory)
    dataset = tmp_path / "dataset"
    file_path = _write_file(dataset / "a.jpg", b"a")
    summary = ingest_service.ingest_paths([file_path])
    elapsed = time.perf_counter() - start

    assert summary.files_scanned == 1
    assert elapsed < 3.0


def test_metrics_server_start_is_thread_safe_single_start(monkeypatch: pytest.MonkeyPatch) -> None:
    import threading

    monkeypatch.setattr(observability, "_server_started", False)
    monkeypatch.setenv("MEDIA_MANAGER_METRICS_ENABLED", "1")
    monkeypatch.setenv("MEDIA_MANAGER_METRICS_PORT", str(_free_port()))

    call_count = {"value": 0}

    def _fake_start_http_server(_port: int) -> None:
        call_count["value"] += 1
        time.sleep(0.02)

    monkeypatch.setattr(observability, "start_http_server", _fake_start_http_server)
    threads = [threading.Thread(target=start_metrics_http_server_if_enabled) for _ in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert call_count["value"] == 1


def test_invalid_metrics_port_is_handled_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(observability, "_server_started", False)
    monkeypatch.setenv("MEDIA_MANAGER_METRICS_ENABLED", "1")
    monkeypatch.setenv("MEDIA_MANAGER_METRICS_PORT", "invalid")
    assert start_metrics_http_server_if_enabled() is False


def test_without_metrics_server_flow_behavior_is_unchanged(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MEDIA_MANAGER_METRICS_ENABLED", raising=False)
    monkeypatch.delenv("MEDIA_MANAGER_METRICS_PORT", raising=False)
    assert start_metrics_http_server_if_enabled() is False

    ingest_service = IngestService(session_factory)
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    apply_service = ApplyService(session_factory)

    noop_path = _write_file(tmp_path / "Media" / "Photos" / "2024" / "01" / "IMG_20240110.jpg", b"noop")
    move_path = _write_file(tmp_path / "inbox" / "IMG_20240111.jpg", b"dup-content")
    dup_path = _write_file(tmp_path / "inbox" / "dup_copy.jpg", b"dup-content")

    ingest_service.ingest_paths([noop_path, move_path, dup_path])
    run = run_service.create_run()
    planner.plan_run(run.id, [noop_path, move_path, dup_path], ingest_if_needed=False)
    summary = apply_service.apply_run(run.id)

    assert summary.errors_count == 0
    with session_factory() as session:
        persisted = session.scalar(select(Run).where(Run.id == run.id))
        assert persisted is not None
        assert persisted.state == RunStateDB.COMPLETED


def test_service_flows_remain_healthy_when_metric_helpers_fail(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("metrics broken")

    monkeypatch.setattr(ingest_module, "record_ingest_metrics", _raise)
    monkeypatch.setattr(planner_module, "record_planner_metrics", _raise)
    monkeypatch.setattr(apply_module, "record_apply_metrics", _raise)

    ingest_service = IngestService(session_factory)
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    apply_service = ApplyService(session_factory)

    noop_path = _write_file(tmp_path / "Media" / "Photos" / "2024" / "01" / "IMG_20240110.jpg", b"noop")
    move_path = _write_file(tmp_path / "inbox" / "IMG_20240111.jpg", b"dup-content")
    dup_path = _write_file(tmp_path / "inbox" / "dup_copy.jpg", b"dup-content")

    ingest_summary = ingest_service.ingest_paths([noop_path, move_path, dup_path])
    assert ingest_summary.files_scanned == 3

    run = run_service.create_run()
    planner_summary = planner.plan_run(run.id, [noop_path, move_path, dup_path], ingest_if_needed=False)
    assert planner_summary.run_id == run.id

    apply_summary = apply_service.apply_run(run.id)
    assert apply_summary.errors_count == 0
    with session_factory() as session:
        persisted = session.scalar(select(Run).where(Run.id == run.id))
        assert persisted is not None
        assert persisted.state == RunStateDB.COMPLETED
