from __future__ import annotations

from pathlib import Path
from time import sleep

from sqlalchemy import select

from media_manager.app.persistence.discovery import process_discovery_paths_in_session
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.models import (
    CanonicalAssignment,
    FileContent,
    FileInstance,
    MediaFile,
    MediaFileStatus,
    MediaMetadata,
)


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
        ledger_rows = session.scalars(select(MediaFile)).all()
        assert len(ledger_rows) == 1
        assert ledger_rows[0].status == MediaFileStatus.INGESTED.value


def test_ingest_copy_new_path_creates_second_instance(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    first = _write_file(tmp_path / "a.jpg", b"same")
    second = _write_file(tmp_path / "copy" / "a_copy.jpg", b"same")

    ingest.ingest_paths([first, second])
    with session_factory() as session:
        contents = session.scalars(select(FileContent)).all()
        instances = session.scalars(select(FileInstance)).all()
        ledgers = session.scalars(select(MediaFile)).all()
        assert len(contents) == 1
        assert len(instances) == 2
        assert len(ledgers) == 2
        assert {row.status for row in ledgers} == {MediaFileStatus.INGESTED.value}


def test_canonical_selection_first_seen_wins(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    first = _write_file(tmp_path / "a.jpg", b"same")
    second = _write_file(tmp_path / "b.jpg", b"same")

    ingest.ingest_paths([first])
    sleep(0.01)
    ingest.ingest_paths([second])
    with session_factory.begin() as session:
        process_discovery_paths_in_session(session, [first, second])
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
        processed = session.scalars(select(MediaFile.status)).all()
        assert len(processed) == 2
        assert set(processed) == {MediaFileStatus.PROCESSED.value}


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


def test_ingest_does_not_append_canonical_assignments(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    first = _write_file(tmp_path / "a.jpg", b"same")
    second = _write_file(tmp_path / "b.jpg", b"same")

    ingest.ingest_paths([first, second])
    with session_factory() as session:
        assignments = session.scalars(select(CanonicalAssignment)).all()
        assert assignments == []


def test_authoritative_root_scan_marks_missing_paths_deleted(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    root = tmp_path / "dataset"
    first = _write_file(root / "a.jpg", b"a")
    second = _write_file(root / "b.jpg", b"b")

    ingest.ingest_path(root)
    second.unlink()
    ingest.ingest_path(root)

    with session_factory() as session:
        rows = session.scalars(select(MediaFile).order_by(MediaFile.current_path.asc())).all()
        by_path = {row.current_path: row for row in rows}
        assert by_path[str(first.resolve(strict=False))].status == MediaFileStatus.INGESTED.value
        deleted = by_path[str(second.resolve(strict=False))]
        assert deleted.status == MediaFileStatus.DELETED.value
        assert deleted.deleted_at is not None


def test_reappearance_after_deleted_inserts_new_row(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    root = tmp_path / "dataset"
    target = _write_file(root / "a.jpg", b"a")

    ingest.ingest_path(root)
    target.unlink()
    ingest.ingest_path(root)
    _write_file(root / "a.jpg", b"a")
    ingest.ingest_path(root)

    with session_factory() as session:
        rows = session.scalars(select(MediaFile).where(MediaFile.current_path == str(target.resolve(strict=False)))).all()
        assert len(rows) == 2
        assert {row.status for row in rows} == {MediaFileStatus.DELETED.value, MediaFileStatus.INGESTED.value}


def test_incremental_ingest_paths_does_not_mark_deleted(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    root = tmp_path / "dataset"
    first = _write_file(root / "a.jpg", b"a")
    second = _write_file(root / "b.jpg", b"b")

    ingest.ingest_path(root)
    second.unlink()
    ingest.ingest_paths([first])

    with session_factory() as session:
        row = session.scalar(select(MediaFile).where(MediaFile.current_path == str(second.resolve(strict=False))))
        assert row is not None
        assert row.status != MediaFileStatus.DELETED.value

