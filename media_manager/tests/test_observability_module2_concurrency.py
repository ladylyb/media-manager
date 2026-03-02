from __future__ import annotations

from pathlib import Path
import threading

import media_manager.app.observability as observability
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService


def _read_histogram_stage_count(stage: str) -> float:
    total = 0.0
    payload = observability.generate_metrics_text().decode("utf-8", errors="ignore")
    for line in payload.splitlines():
        if not line.startswith("planner_stage_duration_seconds_count{"):
            continue
        if f'stage="{stage}"' not in line:
            continue
        raw = line.rsplit(" ", maxsplit=1)[-1]
        try:
            total += float(raw)
        except ValueError:
            continue
    return total


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_concurrent_histogram_recording_is_thread_safe() -> None:
    labels = {"run_id": "thread-run", "stage": "action_generation"}
    before = observability.read_counter_value("planner_stage_duration_seconds_count", labels)
    errors: list[BaseException] = []

    def _worker() -> None:
        try:
            for _ in range(100):
                observability.record_planner_stage_duration("thread-run", "action_generation", 0.001)
        except BaseException as exc:  # pragma: no cover - test guard.
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    after = observability.read_counter_value("planner_stage_duration_seconds_count", labels)
    assert errors == []
    assert after - before == 1600


def test_run_id_none_or_empty_defaults_to_none_label() -> None:
    labels = {"run_id": "none", "stage": "metadata_lookup"}
    before = observability.read_counter_value("planner_stage_duration_seconds_count", labels)

    observability.record_planner_stage_duration(None, "metadata_lookup", 0.002)
    observability.record_planner_stage_duration("", "metadata_lookup", 0.003)

    after = observability.read_counter_value("planner_stage_duration_seconds_count", labels)
    assert after - before == 2


def test_concurrent_planner_runs_record_histograms_without_threading_errors(tmp_path: Path, session_factory) -> None:
    before = _read_histogram_stage_count("action_generation")
    errors: list[BaseException] = []

    def _run(index: int) -> None:
        try:
            ingest_service = IngestService(session_factory)
            run_service = RunService(session_factory)
            planner = PlanningService(session_factory)
            root = tmp_path / f"w{index}"
            duplicate_payload = f"dup-content-{index}".encode("utf-8")
            files = [
                _write_file(root / "Media" / "Photos" / "2024" / "01" / f"IMG_2024011{index}.jpg", f"noop-{index}".encode("utf-8")),
                _write_file(root / "inbox" / f"IMG_2024012{index}.jpg", duplicate_payload),
                _write_file(root / "inbox" / f"dup_copy_{index}.jpg", duplicate_payload),
            ]
            ingest_service.ingest_paths(files)
            run = run_service.create_run()
            planner.plan_run(run.id, files, ingest_if_needed=False)
        except BaseException as exc:  # pragma: no cover - test guard.
            errors.append(exc)

    threads = [threading.Thread(target=_run, args=(i,)) for i in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    after = _read_histogram_stage_count("action_generation")
    assert errors == []
    assert after - before >= 6


def test_concurrent_canonical_cache_metric_recording_is_monotonic_and_thread_safe() -> None:
    labels = {"run_id": "thread-cache-run", "source": "mv"}
    before_hits = observability.read_counter_value("canonical_read_cache_hits_total", labels)
    before_misses = observability.read_counter_value("canonical_read_cache_misses_total", labels)
    errors: list[BaseException] = []
    call_count = {"value": 0}
    call_lock = threading.Lock()
    total_threads = 16
    calls_per_thread = 100

    def _worker() -> None:
        try:
            for _ in range(calls_per_thread):
                with call_lock:
                    call_count["value"] += 1
                    current = call_count["value"]
                observability.record_canonical_read_cache_metrics(
                    run_id="thread-cache-run",
                    source="mv",
                    cache_hits=current,
                    cache_misses=0,
                )
        except BaseException as exc:  # pragma: no cover - test guard.
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(total_threads)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    after_hits = observability.read_counter_value("canonical_read_cache_hits_total", labels)
    after_misses = observability.read_counter_value("canonical_read_cache_misses_total", labels)
    ratio_percent = observability.read_counter_value("canonical_read_cache_hit_ratio_percent", labels)

    assert errors == []
    assert after_hits - before_hits == total_threads * calls_per_thread
    assert after_misses - before_misses == 0
    assert ratio_percent == 100.0
