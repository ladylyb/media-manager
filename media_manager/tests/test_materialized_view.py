from __future__ import annotations

from pathlib import Path

from media_manager.app.persistence.base import create_db_engine, create_session_factory
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.materialized_reads import fetch_canonical_metadata, refresh_materialized_view


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _seed_library(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    root = tmp_path / "library"
    _write_file(root / "a" / "one.jpg", b"same")
    _write_file(root / "b" / "two.jpg", b"same")
    _write_file(root / "c" / "three.jpg", b"unique")
    ingest.ingest_path(root)


def test_mv_returns_identical_results_to_base_query(tmp_path: Path, test_database_url: str, session_factory, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    _seed_library(tmp_path, session_factory)

    engine = create_db_engine(test_database_url)
    refresh_materialized_view(engine, concurrently=False)

    with create_session_factory(engine)() as session:
        base_rows = fetch_canonical_metadata(session, use_mv=False, sample_size=1000, use_cache=False)
        mv_rows = fetch_canonical_metadata(session, use_mv=True, sample_size=1000, use_cache=False)

    assert base_rows == mv_rows


def test_mv_refresh_works_and_preserves_integrity(tmp_path: Path, test_database_url: str, session_factory, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    _seed_library(tmp_path, session_factory)

    engine = create_db_engine(test_database_url)
    refresh_materialized_view(engine, concurrently=False)

    ingest = IngestService(session_factory)
    _write_file(tmp_path / "library" / "d" / "four.jpg", b"fresh")
    ingest.ingest_path(tmp_path / "library")

    refresh_materialized_view(engine, concurrently=False)

    with create_session_factory(engine)() as session:
        base_rows = fetch_canonical_metadata(session, use_mv=False, sample_size=1000, use_cache=False)
        mv_rows = fetch_canonical_metadata(session, use_mv=True, sample_size=1000, use_cache=False)

    assert base_rows == mv_rows


def test_mv_refresh_concurrently_callable(tmp_path: Path, test_database_url: str, session_factory, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    _seed_library(tmp_path, session_factory)

    engine = create_db_engine(test_database_url)
    refresh_materialized_view(engine, concurrently=False)
    summary = refresh_materialized_view(engine, concurrently=True)

    assert summary.concurrently is True
