from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

import media_manager.app.persistence.discovery as discovery_module
from media_manager.app.persistence.discovery import process_discovery_paths_in_session
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.models import CanonicalAssignment, MediaFile, MediaFileStatus


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_discovery_marks_ingested_rows_processed(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    first = _write_file(tmp_path / "a.jpg", b"same")
    second = _write_file(tmp_path / "b.jpg", b"same")

    ingest.ingest_paths([first, second])
    with session_factory.begin() as session:
        processed_paths = process_discovery_paths_in_session(session, [first, second])
        assert set(processed_paths) == {str(first.resolve(strict=False)), str(second.resolve(strict=False))}

    with session_factory() as session:
        statuses = session.scalars(select(MediaFile.status)).all()
        assert len(statuses) == 2
        assert set(statuses) == {MediaFileStatus.PROCESSED.value}
        assignments = session.scalars(select(CanonicalAssignment)).all()
        assert len(assignments) >= 1


def test_discovery_only_transitions_ingested_rows(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    target = _write_file(tmp_path / "target.jpg", b"x")

    ingest.ingest_paths([target])
    with session_factory.begin() as session:
        non_ingested = MediaFile(
            discovered_path="/tmp/already-processed.jpg",
            current_path="/tmp/already-processed.jpg",
            size_bytes=10,
            hash_sha256="1" * 64,
            status=MediaFileStatus.PROCESSED.value,
        )
        session.add(non_ingested)

    with session_factory.begin() as session:
        process_discovery_paths_in_session(session, [target])

    with session_factory() as session:
        rows = session.scalars(select(MediaFile).order_by(MediaFile.current_path.asc())).all()
        by_path = {row.current_path: row.status for row in rows}
        assert by_path[str(target.resolve(strict=False))] == MediaFileStatus.PROCESSED.value
        assert by_path["/tmp/already-processed.jpg"] == MediaFileStatus.PROCESSED.value


def test_discovery_failure_rolls_back_processed_transition(tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    ingest = IngestService(session_factory)
    target = _write_file(tmp_path / "target.jpg", b"x")
    ingest.ingest_paths([target])

    def _raise(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    monkeypatch.setattr(discovery_module, "ensure_canonical_assignment", _raise)
    with pytest.raises(RuntimeError):
        with session_factory.begin() as session:
            process_discovery_paths_in_session(session, [target])

    with session_factory() as session:
        row = session.scalar(select(MediaFile).where(MediaFile.current_path == str(target.resolve(strict=False))))
        assert row is not None
        assert row.status == MediaFileStatus.INGESTED.value


def test_discovery_rerun_is_noop_for_processed_rows(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    target = _write_file(tmp_path / "target.jpg", b"x")
    ingest.ingest_paths([target])

    with session_factory.begin() as session:
        first = process_discovery_paths_in_session(session, [target, target])
        assert first == [str(target.resolve(strict=False))]

    with session_factory.begin() as session:
        second = process_discovery_paths_in_session(session, [target])
        assert second == [str(target.resolve(strict=False))]

    with session_factory() as session:
        row = session.scalar(select(MediaFile).where(MediaFile.current_path == str(target.resolve(strict=False))))
        assert row is not None
        assert row.status == MediaFileStatus.PROCESSED.value
