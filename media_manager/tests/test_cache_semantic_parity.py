from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

import media_manager.app.persistence.materialized_reads as materialized_reads
from media_manager.app.core.ttl_cache import TTLCache
import media_manager.app.observability as observability
from media_manager.app.observability import read_counter_value
from media_manager.app.persistence.base import create_db_engine, create_session_factory
from media_manager.app.persistence.materialized_reads import fetch_canonical_metadata, refresh_materialized_view
from media_manager.app.persistence.models import PlannedAction
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _plan_struct(session_factory, paths: list[Path]) -> tuple[dict[str, int], list[tuple[str, str, str]]]:
    run = RunService(session_factory).create_run()
    summary = PlanningService(session_factory).plan_run(run.id, paths, ingest_if_needed=True)
    with session_factory() as session:
        actions = session.scalars(
            select(PlannedAction)
            .where(PlannedAction.run_id == run.id)
            .order_by(PlannedAction.action_type.asc(), PlannedAction.source_path.asc(), PlannedAction.target_path.asc())
        ).all()
    return (
        {
            "scanned": summary.scanned_count,
            "moves": summary.move_actions,
            "duplicates": summary.duplicate_actions,
            "noop": summary.noop_actions,
            "skipped": summary.skipped_count,
        },
        [(row.action_type, row.source_path, row.target_path or "") for row in actions],
    )


def test_cache_reads_and_planner_outputs_are_semantically_identical(
    tmp_path: Path,
    test_database_url: str,
    session_factory,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setattr(materialized_reads, "_READ_CACHE", TTLCache(ttl_seconds=60.0))

    dataset = tmp_path / "dataset"
    a = _write_file(dataset / "a" / "one.jpg", b"same")
    b = _write_file(dataset / "b" / "two.jpg", b"same")
    c = _write_file(dataset / "c" / "three.jpg", b"unique")

    plan_no_cache = _plan_struct(session_factory, [a, b, c])
    monkeypatch.setenv("CANONICAL_READ_CACHE_ENABLED", "true")
    plan_with_cache = _plan_struct(session_factory, [a, b, c])
    assert plan_no_cache == plan_with_cache

    engine = create_db_engine(test_database_url)
    refresh_materialized_view(engine, concurrently=False)
    with create_session_factory(engine)() as session:
        uncached = fetch_canonical_metadata(session, use_mv=True, sample_size=1000, use_cache=False)
        cached = fetch_canonical_metadata(session, use_mv=True, sample_size=1000, use_cache=True)
    assert uncached == cached


def test_planner_module_does_not_import_ttl_cache() -> None:
    planner_source = Path("media_manager/app/persistence/planner.py").read_text(encoding="utf-8").lower()
    assert "ttl_cache" not in planner_source


def test_ttl_cache_stats_hit_ratio_is_deterministic() -> None:
    cache = TTLCache[str, str](ttl_seconds=60)
    assert cache.stats().hit_ratio == 0.0

    assert cache.get("k1") is None
    cache.set("k1", "v1")
    assert cache.get("k1") == "v1"

    stats = cache.stats()
    assert stats.hits == 1
    assert stats.misses == 1
    assert stats.hit_ratio == 0.5


def test_canonical_read_cache_metrics_hit_miss_and_ratio_percent(
    tmp_path: Path,
    test_database_url: str,
    session_factory,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("CANONICAL_READ_CACHE_ENABLED", "true")
    monkeypatch.setattr(materialized_reads, "_READ_CACHE", TTLCache(ttl_seconds=60.0))

    dataset = tmp_path / "dataset-metrics-enabled"
    a = _write_file(dataset / "a" / "one.jpg", b"same")
    b = _write_file(dataset / "b" / "two.jpg", b"same")
    c = _write_file(dataset / "c" / "three.jpg", b"unique")
    _plan_struct(session_factory, [a, b, c])

    labels = {"run_id": "m3-test", "source": "base"}
    before_hits = read_counter_value("canonical_read_cache_hits_total", labels)
    before_misses = read_counter_value("canonical_read_cache_misses_total", labels)

    with session_factory() as session:
        first = fetch_canonical_metadata(
            session,
            use_mv=False,
            sample_size=1000,
            use_cache=True,
            metrics_run_id="m3-test",
        )
        second = fetch_canonical_metadata(
            session,
            use_mv=False,
            sample_size=1000,
            use_cache=True,
            metrics_run_id="m3-test",
        )
    assert first == second

    after_hits = read_counter_value("canonical_read_cache_hits_total", labels)
    after_misses = read_counter_value("canonical_read_cache_misses_total", labels)
    ratio_percent = read_counter_value("canonical_read_cache_hit_ratio_percent", labels)

    assert after_hits - before_hits == 1
    assert after_misses - before_misses == 1
    assert ratio_percent == 50.0


def test_canonical_read_cache_metrics_disabled_sets_zero_ratio(
    tmp_path: Path,
    test_database_url: str,
    session_factory,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("CANONICAL_READ_CACHE_ENABLED", "false")
    monkeypatch.setattr(materialized_reads, "_READ_CACHE", TTLCache(ttl_seconds=60.0))

    dataset = tmp_path / "dataset-metrics-disabled"
    a = _write_file(dataset / "a" / "one.jpg", b"same")
    b = _write_file(dataset / "b" / "two.jpg", b"same")
    c = _write_file(dataset / "c" / "three.jpg", b"unique")
    _plan_struct(session_factory, [a, b, c])

    labels = {"run_id": "m3-disabled", "source": "base"}
    with session_factory() as session:
        rows = fetch_canonical_metadata(
            session,
            use_mv=False,
            sample_size=1000,
            use_cache=None,
            metrics_run_id="m3-disabled",
        )
    assert len(rows) >= 1
    assert read_counter_value("canonical_read_cache_hit_ratio_percent", labels) == 0.0


def test_canonical_read_path_is_fail_open_when_metric_recording_raises(
    tmp_path: Path,
    test_database_url: str,
    session_factory,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("CANONICAL_READ_CACHE_ENABLED", "true")
    monkeypatch.setattr(materialized_reads, "_READ_CACHE", TTLCache(ttl_seconds=60.0))

    dataset = tmp_path / "dataset-fail-open"
    a = _write_file(dataset / "a" / "one.jpg", b"same")
    b = _write_file(dataset / "b" / "two.jpg", b"same")
    c = _write_file(dataset / "c" / "three.jpg", b"unique")
    _plan_struct(session_factory, [a, b, c])

    class _BrokenCollector:
        def labels(self, **_kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("metric helper failure")

    monkeypatch.setattr(observability, "_CANONICAL_READ_CACHE_HITS_TOTAL", _BrokenCollector())
    with session_factory() as session:
        rows = fetch_canonical_metadata(
            session,
            use_mv=False,
            sample_size=1000,
            use_cache=True,
            metrics_run_id="fail-open",
        )
    assert len(rows) >= 1


def test_disabled_cache_read_path_is_fail_open_when_disabled_metric_helper_raises(
    tmp_path: Path,
    test_database_url: str,
    session_factory,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("CANONICAL_READ_CACHE_ENABLED", "false")
    monkeypatch.setattr(materialized_reads, "_READ_CACHE", TTLCache(ttl_seconds=60.0))

    dataset = tmp_path / "dataset-disabled-fail-open"
    a = _write_file(dataset / "a" / "one.jpg", b"same")
    b = _write_file(dataset / "b" / "two.jpg", b"same")
    c = _write_file(dataset / "c" / "three.jpg", b"unique")
    _plan_struct(session_factory, [a, b, c])

    class _BrokenGauge:
        def labels(self, **_kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("metric disabled helper failure")

    monkeypatch.setattr(observability, "_CANONICAL_READ_CACHE_HIT_RATIO_PERCENT", _BrokenGauge())
    with session_factory() as session:
        rows = fetch_canonical_metadata(
            session,
            use_mv=False,
            sample_size=1000,
            use_cache=None,
            metrics_run_id="disabled-fail-open",
        )
    assert len(rows) >= 1
