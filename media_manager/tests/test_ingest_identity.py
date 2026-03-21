from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from time import sleep

from sqlalchemy import select

import media_manager.app.persistence.ingest as ingest_module
import media_manager.app.core.metadata_extractor as metadata_extractor
from media_manager.app.core.hashing import sha256_file
from media_manager.app.persistence.discovery import process_discovery_paths_in_session
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.models import (
    CanonicalAssignment,
    FileContent,
    FileInstance,
    MediaFile,
    MediaFileStatus,
    MediaMetadata,
    MetadataCode,
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


def test_ingest_duplicate_with_stronger_filename_evidence_upgrades_taken_dt_source(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    first = _write_file(tmp_path / "copy.jpg", b"same")
    second = _write_file(tmp_path / "IMG_20240214_235959.jpg", b"same")

    ingest.ingest_paths([first])
    ingest.ingest_paths([second])

    with session_factory() as session:
        content = session.scalar(select(FileContent))
        assert content is not None
        rows = {
            code_type: value
            for code_type, value in session.execute(
                select(MetadataCode.code_type, MediaMetadata.decode_value)
                .join(MediaMetadata, MediaMetadata.code_id == MetadataCode.id)
                .where(MediaMetadata.content_id == content.content_id)
            ).all()
        }
        assert rows["TAKEN_DT_SOURCE"] == "filename"
        assert rows["TAKEN_DT"] == "2024-02-14T23:59:59+00:00"


def test_ingest_same_digest_batch_creates_single_content_and_counts_duplicates(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    first = _write_file(tmp_path / "first.jpg", b"same")
    second = _write_file(tmp_path / "nested" / "second.jpg", b"same")
    third = _write_file(tmp_path / "nested" / "third.jpg", b"same")

    summary = ingest.ingest_paths([first, second, third])

    assert summary.files_scanned == 3
    assert summary.new_contents == 1
    assert summary.new_instances == 3
    assert summary.duplicates_detected == 2

    with session_factory() as session:
        assert len(session.scalars(select(FileContent)).all()) == 1
        assert len(session.scalars(select(FileInstance)).all()) == 3
        assert len(session.scalars(select(MediaMetadata)).all()) > 0


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
        live = next(row for row in rows if row.status == MediaFileStatus.INGESTED.value)
        assert live.hash_sha256 is not None


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


def test_ingest_preserves_processed_status_on_reingest(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    target = _write_file(tmp_path / "keep-processed.jpg", b"same")

    ingest.ingest_paths([target])
    with session_factory.begin() as session:
        process_discovery_paths_in_session(session, [target])
    ingest.ingest_paths([target])

    with session_factory() as session:
        row = session.scalar(select(MediaFile).where(MediaFile.current_path == str(target.resolve(strict=False))))
        assert row is not None
        assert row.status == MediaFileStatus.PROCESSED.value


def test_ingest_fills_missing_hash_for_existing_live_row(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    target = _write_file(tmp_path / "missing-hash.jpg", b"payload")
    expected_digest = sha256_file(target)
    discovered_at = datetime(2020, 1, 1, tzinfo=timezone.utc)

    with session_factory.begin() as session:
        session.add(
            MediaFile(
                discovered_path=str(target.resolve(strict=False)),
                current_path=str(target.resolve(strict=False)),
                size_bytes=1,
                hash_sha256=None,
                discovered_at=discovered_at,
                status=MediaFileStatus.PROCESSED.value,
            )
        )

    ingest.ingest_paths([target])
    with session_factory() as session:
        row = session.scalar(select(MediaFile).where(MediaFile.current_path == str(target.resolve(strict=False))))
        assert row is not None
        assert row.hash_sha256 == expected_digest
        assert row.status == MediaFileStatus.PROCESSED.value
        assert row.discovered_at == discovered_at
        assert row.ingested_at is not None


def test_ingest_preserves_existing_discovered_at(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    target = _write_file(tmp_path / "discovered-at.jpg", b"payload")
    expected_digest = sha256_file(target)
    discovered_at = datetime(2019, 6, 1, tzinfo=timezone.utc)

    with session_factory.begin() as session:
        session.add(
            MediaFile(
                discovered_path=str(target.resolve(strict=False)),
                current_path=str(target.resolve(strict=False)),
                size_bytes=1,
                hash_sha256=expected_digest,
                discovered_at=discovered_at,
                status=MediaFileStatus.INGESTED.value,
            )
        )

    ingest.ingest_paths([target])
    with session_factory() as session:
        row = session.scalar(select(MediaFile).where(MediaFile.current_path == str(target.resolve(strict=False))))
        assert row is not None
        assert row.hash_sha256 == expected_digest
        assert row.discovered_at == discovered_at
        assert row.ingested_at is not None


def test_ingest_hash_mismatch_logs_without_overwrite(tmp_path: Path, session_factory, monkeypatch) -> None:
    ingest = IngestService(session_factory)
    target = _write_file(tmp_path / "hash-mismatch.jpg", b"payload")
    warning_calls: list[dict[str, str]] = []

    def _capture_warning(_message: str, *, extra: dict[str, str]) -> None:
        warning_calls.append(extra)

    monkeypatch.setattr(ingest_module.logger, "warning", _capture_warning)

    with session_factory.begin() as session:
        session.add(
            MediaFile(
                discovered_path=str(target.resolve(strict=False)),
                current_path=str(target.resolve(strict=False)),
                size_bytes=1,
                hash_sha256="0" * 64,
                status=MediaFileStatus.INGESTED.value,
            )
        )

    ingest.ingest_paths([target])

    with session_factory() as session:
        row = session.scalar(select(MediaFile).where(MediaFile.current_path == str(target.resolve(strict=False))))
        assert row is not None
        assert row.hash_sha256 == "0" * 64

    mismatch_warnings = [extra for extra in warning_calls if extra.get("action") == "HASH_MISMATCH"]
    assert len(mismatch_warnings) == 1
    assert "file_size=7" in mismatch_warnings[0].get("codes_extracted", "")


def test_ingest_zero_byte_file_hash_recording(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    target = _write_file(tmp_path / "empty.jpg", b"")

    ingest.ingest_paths([target])
    with session_factory() as session:
        row = session.scalar(select(MediaFile).where(MediaFile.current_path == str(target.resolve(strict=False))))
        assert row is not None
        assert row.hash_sha256 == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_ingest_bulk_metadata_upsert_only_targets_new_content(tmp_path: Path, session_factory, monkeypatch) -> None:
    ingest = IngestService(session_factory)
    existing = _write_file(tmp_path / "existing.jpg", b"existing")
    new_file = _write_file(tmp_path / "new.jpg", b"new")

    ingest.ingest_paths([existing])

    bulk_calls: list[dict[object, object]] = []
    extracted_paths: list[str] = []

    real_extract = metadata_extractor.extract_file_metadata
    real_bulk = metadata_extractor.upsert_metadata_bulk

    def _capture_extract(path: Path, file_hash: str) -> list[metadata_extractor.MetadataItem]:
        extracted_paths.append(str(path.resolve(strict=False)))
        return real_extract(path, file_hash)

    def _capture_bulk(session, metadata_by_content, *args, **kwargs):  # type: ignore[no-untyped-def]
        bulk_calls.append(dict(metadata_by_content))
        return real_bulk(session, metadata_by_content, *args, **kwargs)

    monkeypatch.setattr(metadata_extractor, "extract_file_metadata", _capture_extract)
    monkeypatch.setattr(metadata_extractor, "upsert_metadata_bulk", _capture_bulk)

    summary = ingest.ingest_paths([existing, new_file])

    assert summary.new_contents == 1
    assert summary.duplicates_detected == 1
    assert extracted_paths == [str(new_file.resolve(strict=False))]
    assert len(bulk_calls) == 1
    assert len(bulk_calls[0]) == 1
    assert len(next(iter(bulk_calls[0].values()))) > 0


def test_ingest_file_disappears_mid_scan_is_safely_skipped(tmp_path: Path, session_factory, monkeypatch) -> None:
    ingest = IngestService(session_factory)
    target = _write_file(tmp_path / "vanish.jpg", b"payload")

    def _vanishing_hash(path: Path, *_args, **_kwargs) -> str:  # type: ignore[no-untyped-def]
        path.unlink()
        raise FileNotFoundError("file disappeared")

    monkeypatch.setattr(ingest_module, "sha256_file", _vanishing_hash)

    summary = ingest.ingest_paths([target])
    assert summary.files_scanned == 1
    assert summary.new_contents == 0
    assert summary.new_instances == 0

    with session_factory() as session:
        assert session.scalar(select(MediaFile).where(MediaFile.current_path == str(target.resolve(strict=False)))) is None
        assert session.scalars(select(FileContent)).all() == []
