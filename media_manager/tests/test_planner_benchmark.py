from __future__ import annotations

import time
from pathlib import Path

from sqlalchemy import text

from media_manager.app.cli import main
from media_manager.app.persistence.base import create_db_engine, create_session_factory
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.materialized_reads import benchmark_planner_lookup, fetch_canonical_metadata


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _seed_library(tmp_path: Path, session_factory) -> Path:
    ingest = IngestService(session_factory)
    root = tmp_path / "library"
    _write_file(root / "a" / "one.jpg", b"same")
    _write_file(root / "b" / "two.jpg", b"same")
    _write_file(root / "c" / "three.jpg", b"unique")
    ingest.ingest_path(root)
    return root


def _counts(db_url: str) -> dict[str, int]:
    engine = create_db_engine(db_url)
    with engine.begin() as conn:
        return {
            "runs": conn.execute(text("SELECT COUNT(*) FROM runs")).scalar_one(),
            "planned_actions": conn.execute(text("SELECT COUNT(*) FROM planned_actions")).scalar_one(),
            "apply_audit_runs": conn.execute(text("SELECT COUNT(*) FROM apply_audit_runs")).scalar_one(),
            "apply_audit_items": conn.execute(text("SELECT COUNT(*) FROM apply_audit_items")).scalar_one(),
        }


def test_benchmark_runs_without_planner_mutation(
    tmp_path: Path,
    test_database_url: str,
    session_factory,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    _seed_library(tmp_path, session_factory)
    assert main(["refresh-mv", "--no-concurrently"]) == 0

    before = _counts(test_database_url)
    assert main(["planner-benchmark", "--sample-size", "100", "--repeats", "2"]) == 0
    after = _counts(test_database_url)

    assert before == after
    out = capsys.readouterr().out
    assert "Base mean:" in out
    assert "MV mean:" in out
    assert "StdDev:" in out
    assert "Improvement:" in out


def test_cache_disabled_identical_behavior(
    tmp_path: Path,
    test_database_url: str,
    session_factory,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("CANONICAL_READ_CACHE_ENABLED", "false")

    _seed_library(tmp_path, session_factory)
    assert main(["refresh-mv", "--no-concurrently"]) == 0

    engine = create_db_engine(test_database_url)
    with create_session_factory(engine)() as session:
        uncached = fetch_canonical_metadata(session, use_mv=True, sample_size=1000, use_cache=False)
        default_disabled = fetch_canonical_metadata(session, use_mv=True, sample_size=1000, use_cache=None)

    assert uncached == default_disabled


def test_cache_enabled_benchmark_improvement_mocked(
    tmp_path: Path,
    test_database_url: str,
    session_factory,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    _seed_library(tmp_path, session_factory)
    assert main(["refresh-mv", "--no-concurrently"]) == 0

    import media_manager.app.persistence.materialized_reads as reads

    real_fetch = reads.fetch_canonical_metadata
    seen_cached_mv = {"hit": False}

    def _slow_fetch(session, *, use_mv, sample_size, use_cache=None):  # type: ignore[no-untyped-def]
        if use_mv:
            if use_cache:
                if not seen_cached_mv["hit"]:
                    time.sleep(0.03)
                    seen_cached_mv["hit"] = True
            else:
                time.sleep(0.03)
        return real_fetch(session, use_mv=use_mv, sample_size=sample_size, use_cache=use_cache)

    monkeypatch.setattr(reads, "fetch_canonical_metadata", _slow_fetch)

    uncached = benchmark_planner_lookup(
        create_session_factory(create_db_engine(test_database_url)),
        sample_size=100,
        repeats=2,
        use_cache=False,
        seed=42,
    )

    seen_cached_mv["hit"] = False
    cached = benchmark_planner_lookup(
        create_session_factory(create_db_engine(test_database_url)),
        sample_size=100,
        repeats=2,
        use_cache=True,
        seed=42,
    )

    assert cached.mv_mean_ms < uncached.mv_mean_ms
