from __future__ import annotations

import threading
from pathlib import Path

import pytest

import media_manager.app.observability as observability
from media_manager.app.persistence.ingest import IngestService
from operator_console.main import app as operator_console_app


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_structured_ingest_counters_and_histograms_increment_with_expected_deltas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIA_MANAGER_METRICS_ENABLED", "1")
    labels = {"run_id": "module4-unit", "dataset_id": "dataset-a", "policy_name": "default"}

    before_scanned = observability.read_counter_value("files_scanned_total", labels)
    before_contents = observability.read_counter_value("new_contents_total", labels)
    before_instances = observability.read_counter_value("new_instances_total", labels)
    before_duplicates = observability.read_counter_value("duplicates_detected_total", labels)
    before_hash_count = observability.read_counter_value("hash_time_total_ms_count", labels)
    before_db_count = observability.read_counter_value("db_write_time_total_ms_count", labels)

    observability.record_ingest_structured_metrics(
        run_id="module4-unit",
        dataset_id="dataset-a",
        policy_name="default",
        files_scanned=3,
        new_contents=2,
        new_instances=3,
        duplicates_detected=1,
        hash_latencies_ms=[1.2, 2.4, 3.6],
        db_write_latencies_ms=[5.0, 6.0, 7.0],
    )
    observability.record_ingest_structured_metrics(
        run_id="module4-unit",
        dataset_id="dataset-a",
        policy_name="default",
        files_scanned=1,
        new_contents=0,
        new_instances=1,
        duplicates_detected=1,
        hash_latencies_ms=[1.0],
        db_write_latencies_ms=[4.0],
    )

    after_scanned = observability.read_counter_value("files_scanned_total", labels)
    after_contents = observability.read_counter_value("new_contents_total", labels)
    after_instances = observability.read_counter_value("new_instances_total", labels)
    after_duplicates = observability.read_counter_value("duplicates_detected_total", labels)
    after_hash_count = observability.read_counter_value("hash_time_total_ms_count", labels)
    after_db_count = observability.read_counter_value("db_write_time_total_ms_count", labels)

    assert after_scanned - before_scanned == 4
    assert after_contents - before_contents == 2
    assert after_instances - before_instances == 4
    assert after_duplicates - before_duplicates == 2
    assert after_hash_count - before_hash_count == 4
    assert after_db_count - before_db_count == 4


def test_structured_ingest_labels_apply_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIA_MANAGER_METRICS_ENABLED", "1")
    labels = {"run_id": "none", "dataset_id": "unknown", "policy_name": "default"}
    before = observability.read_counter_value("files_scanned_total", labels)

    observability.record_ingest_structured_metrics(
        run_id=None,
        dataset_id="",
        policy_name="  ",
        files_scanned=1,
        new_contents=1,
        new_instances=1,
        duplicates_detected=0,
        hash_latencies_ms=[1.0],
        db_write_latencies_ms=[1.0],
    )

    after = observability.read_counter_value("files_scanned_total", labels)
    assert after - before == 1


def test_structured_ingest_metrics_are_fail_open_when_collector_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIA_MANAGER_METRICS_ENABLED", "1")

    class _BrokenCollector:
        def labels(self, **_kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("collector failed")

    monkeypatch.setattr(observability, "_FILES_SCANNED_TOTAL", _BrokenCollector())
    observability.record_ingest_structured_metrics(
        run_id="fail-open",
        dataset_id="dataset",
        policy_name="default",
        files_scanned=1,
        new_contents=1,
        new_instances=1,
        duplicates_detected=0,
        hash_latencies_ms=[1.0],
        db_write_latencies_ms=[1.0],
    )


def test_structured_ingest_metrics_are_noop_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIA_MANAGER_METRICS_ENABLED", "0")
    labels = {"run_id": "disabled-run", "dataset_id": "disabled", "policy_name": "default"}
    before_scanned = observability.read_counter_value("files_scanned_total", labels)
    before_hash = observability.read_counter_value("hash_time_total_ms_count", labels)

    observability.record_ingest_structured_metrics(
        run_id="disabled-run",
        dataset_id="disabled",
        policy_name="default",
        files_scanned=5,
        new_contents=5,
        new_instances=5,
        duplicates_detected=5,
        hash_latencies_ms=[1.0, 2.0, 3.0],
        db_write_latencies_ms=[1.0, 2.0, 3.0],
    )

    after_scanned = observability.read_counter_value("files_scanned_total", labels)
    after_hash = observability.read_counter_value("hash_time_total_ms_count", labels)
    assert after_scanned - before_scanned == 0
    assert after_hash - before_hash == 0


def test_structured_ingest_metrics_exposed_on_metrics_endpoint_with_ingest_flow(
    tmp_path: Path,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    testclient = pytest.importorskip("fastapi.testclient")
    monkeypatch.setenv("MEDIA_MANAGER_METRICS_ENABLED", "1")

    ingest_service = IngestService(session_factory)
    files = [
        _write_file(tmp_path / "media" / "a.jpg", b"same"),
        _write_file(tmp_path / "media" / "b.jpg", b"same"),
        _write_file(tmp_path / "media" / "c.jpg", b"unique"),
    ]
    labels = {"run_id": "none", "dataset_id": "unknown", "policy_name": "default"}

    before_scanned = observability.read_counter_value("files_scanned_total", labels)
    before_contents = observability.read_counter_value("new_contents_total", labels)
    before_instances = observability.read_counter_value("new_instances_total", labels)
    before_duplicates = observability.read_counter_value("duplicates_detected_total", labels)
    before_hash = observability.read_counter_value("hash_time_total_ms_count", labels)
    before_db = observability.read_counter_value("db_write_time_total_ms_count", labels)

    summary = ingest_service.ingest_paths(files)

    after_scanned = observability.read_counter_value("files_scanned_total", labels)
    after_contents = observability.read_counter_value("new_contents_total", labels)
    after_instances = observability.read_counter_value("new_instances_total", labels)
    after_duplicates = observability.read_counter_value("duplicates_detected_total", labels)
    after_hash = observability.read_counter_value("hash_time_total_ms_count", labels)
    after_db = observability.read_counter_value("db_write_time_total_ms_count", labels)

    assert after_scanned - before_scanned == summary.files_scanned
    assert after_contents - before_contents == summary.new_contents
    assert after_instances - before_instances == summary.new_instances
    assert after_duplicates - before_duplicates == summary.duplicates_detected
    assert after_hash - before_hash == summary.files_scanned
    assert after_db - before_db == summary.files_scanned

    response = testclient.TestClient(operator_console_app).get("/metrics/")
    assert response.status_code == 200
    text = response.text
    assert "files_scanned_total" in text
    assert "new_contents_total" in text
    assert "new_instances_total" in text
    assert "duplicates_detected_total" in text
    assert "hash_time_total_ms_bucket" in text
    assert "hash_time_total_ms_sum" in text
    assert "hash_time_total_ms_count" in text
    assert "db_write_time_total_ms_bucket" in text
    assert "db_write_time_total_ms_sum" in text
    assert "db_write_time_total_ms_count" in text


def test_structured_ingest_metric_recording_is_thread_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIA_MANAGER_METRICS_ENABLED", "1")
    labels = {"run_id": "module4-concurrency", "dataset_id": "set-a", "policy_name": "default"}
    before_scanned = observability.read_counter_value("files_scanned_total", labels)
    before_hash = observability.read_counter_value("hash_time_total_ms_count", labels)
    errors: list[BaseException] = []
    total_threads = 12
    per_thread_calls = 80

    def _worker() -> None:
        try:
            for _ in range(per_thread_calls):
                observability.record_ingest_structured_metrics(
                    run_id="module4-concurrency",
                    dataset_id="set-a",
                    policy_name="default",
                    files_scanned=1,
                    new_contents=0,
                    new_instances=1,
                    duplicates_detected=0,
                    hash_latencies_ms=[0.4],
                    db_write_latencies_ms=[0.8],
                )
        except BaseException as exc:  # pragma: no cover - guard only.
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(total_threads)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    after_scanned = observability.read_counter_value("files_scanned_total", labels)
    after_hash = observability.read_counter_value("hash_time_total_ms_count", labels)
    assert errors == []
    assert after_scanned - before_scanned == total_threads * per_thread_calls
    assert after_hash - before_hash == total_threads * per_thread_calls


def test_parallel_ingest_runs_update_structured_metrics_without_corruption(
    tmp_path: Path,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIA_MANAGER_METRICS_ENABLED", "1")
    labels = {"run_id": "none", "dataset_id": "unknown", "policy_name": "default"}
    before_scanned = observability.read_counter_value("files_scanned_total", labels)
    before_hash = observability.read_counter_value("hash_time_total_ms_count", labels)
    before_db = observability.read_counter_value("db_write_time_total_ms_count", labels)
    errors: list[BaseException] = []
    threads_total = 6
    files_per_thread = 2

    def _run(index: int) -> None:
        try:
            ingest_service = IngestService(session_factory)
            root = tmp_path / f"t{index}"
            files = [
                _write_file(root / "media" / f"a_{index}.jpg", f"payload-{index}".encode("utf-8")),
                _write_file(root / "media" / f"b_{index}.jpg", f"payload-{index}".encode("utf-8")),
            ]
            summary = ingest_service.ingest_paths(files)
            assert summary.files_scanned == files_per_thread
        except BaseException as exc:  # pragma: no cover - guard only.
            errors.append(exc)

    threads = [threading.Thread(target=_run, args=(index,)) for index in range(threads_total)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    after_scanned = observability.read_counter_value("files_scanned_total", labels)
    after_hash = observability.read_counter_value("hash_time_total_ms_count", labels)
    after_db = observability.read_counter_value("db_write_time_total_ms_count", labels)
    expected = threads_total * files_per_thread

    assert errors == []
    assert after_scanned - before_scanned >= expected
    assert after_hash - before_hash >= expected
    assert after_db - before_db >= expected
