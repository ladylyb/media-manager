from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

import media_manager.app.persistence.ingest as ingest_module
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.models import MediaFile, MediaFileStatus


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_validate_detects_would_insert_for_unseen_file(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    target = _write_file(tmp_path / "new.jpg", b"payload")

    report = ingest.validate_paths([target]).to_dict()

    assert report["mode"] == "VALIDATION_ONLY"
    assert report["delta"]["would_insert"] == 1
    assert report["delta"]["would_update"] == 0


def test_validate_detects_would_update_for_existing_live_row(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    target = _write_file(tmp_path / "existing.jpg", b"payload")

    with session_factory.begin() as session:
        session.add(
            MediaFile(
                discovered_path=str(target.resolve(strict=False)),
                current_path=str(target.resolve(strict=False)),
                size_bytes=1,
                hash_sha256=None,
                discovered_at=datetime(2020, 1, 1, tzinfo=UTC),
                status=MediaFileStatus.PROCESSED.value,
            )
        )

    report = ingest.validate_paths([target]).to_dict()

    assert report["delta"]["would_insert"] == 0
    assert report["delta"]["would_update"] == 1


def test_validate_detects_hash_mismatch_without_mutation(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    target = _write_file(tmp_path / "mismatch.jpg", b"payload")

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

    report = ingest.validate_paths([target]).to_dict()

    assert report["delta"]["hash_mismatch_observed"] == 1
    with session_factory() as session:
        row = session.scalar(select(MediaFile).where(MediaFile.current_path == str(target.resolve(strict=False))))
        assert row is not None
        assert row.hash_sha256 == "0" * 64


def test_validate_detects_would_mark_deleted_under_authoritative_root(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    root = tmp_path / "dataset"
    present = _write_file(root / "present.jpg", b"a")
    missing = _write_file(root / "missing.jpg", b"b")

    ingest.ingest_path(root)
    missing.unlink()

    report = ingest.validate_path(root).to_dict()

    assert report["delta"]["would_mark_deleted"] == 1
    deleted_samples = report["samples"]["would_mark_deleted"]
    assert any(sample["current_path"] == str(missing.resolve(strict=False)) for sample in deleted_samples)
    with session_factory() as session:
        row = session.scalar(select(MediaFile).where(MediaFile.current_path == str(missing.resolve(strict=False))))
        assert row is not None
        assert row.status != MediaFileStatus.DELETED.value


def test_validate_detects_reappearance_after_deleted(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    root = tmp_path / "dataset"
    target = _write_file(root / "a.jpg", b"a")

    ingest.ingest_path(root)
    target.unlink()
    ingest.ingest_path(root)
    _write_file(root / "a.jpg", b"a")

    report = ingest.validate_path(root).to_dict()

    assert report["delta"]["would_reappear_after_delete"] == 1
    assert report["delta"]["would_insert"] >= 1


def test_validate_handles_disappearing_file_with_warning(tmp_path: Path, session_factory, monkeypatch) -> None:
    ingest = IngestService(session_factory)
    target = _write_file(tmp_path / "vanish.jpg", b"payload")

    def _vanishing_hash(path: Path, *_args, **_kwargs) -> str:  # type: ignore[no-untyped-def]
        path.unlink()
        raise FileNotFoundError("file disappeared")

    monkeypatch.setattr(ingest_module, "sha256_file", _vanishing_hash)

    report = ingest.validate_paths([target]).to_dict()

    assert report["scan"]["files_scanned"] == 0
    assert report["scan"]["files_missing_during_scan"] == 1
    assert len(report["warnings"]) == 1
