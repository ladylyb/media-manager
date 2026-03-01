from __future__ import annotations

from pathlib import Path
from time import sleep

from sqlalchemy import select

from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.models import CanonicalAssignment, FileContent, FileInstance, MediaMetadata


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_ingest_same_file_twice_is_idempotent(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    f = _write_file(tmp_path / "a.jpg", b"same")

    first = ingest.ingest_paths([f])
    second = ingest.ingest_paths([f])
    assert first.files_scanned == 1
    assert second.files_scanned == 1

    with session_factory() as session:
        assert len(session.scalars(select(FileContent)).all()) == 1
        assert len(session.scalars(select(FileInstance)).all()) == 1
        content = session.scalar(select(FileContent))
        assert content is not None
        rows = session.scalars(select(MediaMetadata).where(MediaMetadata.content_id == content.content_id)).all()
        assert len(rows) > 0


def test_ingest_copy_new_path_creates_second_instance(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    first = _write_file(tmp_path / "a.jpg", b"same")
    second = _write_file(tmp_path / "copy" / "a_copy.jpg", b"same")

    ingest.ingest_paths([first, second])
    with session_factory() as session:
        contents = session.scalars(select(FileContent)).all()
        instances = session.scalars(select(FileInstance)).all()
        assert len(contents) == 1
        assert len(instances) == 2


def test_canonical_selection_first_seen_wins(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    first = _write_file(tmp_path / "a.jpg", b"same")
    second = _write_file(tmp_path / "b.jpg", b"same")

    ingest.ingest_paths([first])
    sleep(0.01)
    ingest.ingest_paths([second])
    with session_factory() as session:
        content = session.scalar(select(FileContent))
        first_instance = session.scalar(select(FileInstance).where(FileInstance.absolute_path == str(first)))
        assignment = session.scalar(
            select(CanonicalAssignment)
            .where(CanonicalAssignment.content_id == content.content_id)  # type: ignore[union-attr]
            .order_by(CanonicalAssignment.assigned_at.desc(), CanonicalAssignment.assignment_id.desc())
        )
        assert content is not None
        assert first_instance is not None
        assert assignment is not None
        assert assignment.canonical_instance_id == first_instance.file_instance_id


def test_ingest_rerun_updates_last_seen_without_duplicate_instance(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    file_path = _write_file(tmp_path / "seen.jpg", b"same")
    ingest.ingest_paths([file_path])

    with session_factory() as session:
        before = session.scalar(select(FileInstance).where(FileInstance.absolute_path == str(file_path)))
        assert before is not None
        before_seen = before.last_seen_at

    sleep(0.01)
    ingest.ingest_paths([file_path])
    with session_factory() as session:
        after = session.scalar(select(FileInstance).where(FileInstance.absolute_path == str(file_path)))
        assert after is not None
        assert after.last_seen_at >= before_seen
        assert len(session.scalars(select(FileInstance)).all()) == 1

