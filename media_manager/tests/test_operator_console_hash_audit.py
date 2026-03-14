from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from media_manager.app.core.hashing import sha256_file
from media_manager.app.persistence.models import MediaFile, MediaFileStatus
from media_manager.app.persistence.operator_console import OperatorConsoleReadService


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _add_media_file_row(
    session,
    *,
    path: str,
    status: MediaFileStatus,
    hash_sha256: str | None,
    deleted_at: datetime | None = None,
) -> None:
    discovered_at = datetime(2026, 3, 3, 12, 0, tzinfo=UTC)
    ingested_at = datetime(2026, 3, 3, 12, 1, tzinfo=UTC)
    session.add(
        MediaFile(
            discovered_path=path,
            current_path=path,
            size_bytes=10,
            hash_sha256=hash_sha256,
            discovered_at=discovered_at,
            ingested_at=ingested_at,
            status=status.value,
            deleted_at=deleted_at,
        )
    )


def test_hash_audit_counts_missing_and_mismatch(session_factory, tmp_path: Path) -> None:
    service = OperatorConsoleReadService(session_factory)
    good = _write_file(tmp_path / "good.jpg", b"good")
    mismatch = _write_file(tmp_path / "mismatch.jpg", b"mismatch")

    with session_factory.begin() as session:
        _add_media_file_row(
            session,
            path=str(good.resolve(strict=False)),
            status=MediaFileStatus.INGESTED,
            hash_sha256=sha256_file(good),
        )
        _add_media_file_row(
            session,
            path=str(mismatch.resolve(strict=False)),
            status=MediaFileStatus.PROCESSED,
            hash_sha256="0" * 64,
        )
        _add_media_file_row(
            session,
            path=str((tmp_path / "missing-hash.jpg").resolve(strict=False)),
            status=MediaFileStatus.INGESTED,
            hash_sha256=None,
        )

    payload = service.get_ledger_hash_audit().to_dict()

    assert payload["total_files"] == 3
    assert payload["missing_hash"] == 1
    assert payload["hash_mismatches"] == 1
    assert str(mismatch.resolve(strict=False)) in payload["sample_mismatch_paths"]


def test_hash_audit_excludes_deleted_and_counts_skipped(session_factory, tmp_path: Path) -> None:
    service = OperatorConsoleReadService(session_factory)
    active = _write_file(tmp_path / "active.jpg", b"active")

    with session_factory.begin() as session:
        _add_media_file_row(
            session,
            path=str(active.resolve(strict=False)),
            status=MediaFileStatus.INGESTED,
            hash_sha256=sha256_file(active),
        )
        _add_media_file_row(
            session,
            path=str((tmp_path / "deleted.jpg").resolve(strict=False)),
            status=MediaFileStatus.DELETED,
            hash_sha256="f" * 64,
            deleted_at=datetime(2026, 3, 3, 12, 5, tzinfo=UTC),
        )

    payload = service.get_ledger_hash_audit().to_dict()

    assert payload["total_files"] == 1
    assert payload["deleted_rows_skipped"] == 1


def test_hash_audit_root_path_filter(session_factory, tmp_path: Path) -> None:
    service = OperatorConsoleReadService(session_factory)
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    file_a = _write_file(root_a / "a.jpg", b"a")
    file_b = _write_file(root_b / "b.jpg", b"b")

    with session_factory.begin() as session:
        _add_media_file_row(
            session,
            path=str(file_a.resolve(strict=False)),
            status=MediaFileStatus.INGESTED,
            hash_sha256=None,
        )
        _add_media_file_row(
            session,
            path=str(file_b.resolve(strict=False)),
            status=MediaFileStatus.INGESTED,
            hash_sha256=None,
        )

    payload = service.get_ledger_hash_audit(root_path=str(root_a.resolve(strict=False))).to_dict()

    assert payload["total_files"] == 1
    assert payload["missing_hash"] == 1
    assert payload["sample_missing_hash_paths"] == [str(file_a.resolve(strict=False))]


def test_hash_audit_samples_are_deterministic_and_capped(session_factory, tmp_path: Path) -> None:
    service = OperatorConsoleReadService(session_factory)
    first = _write_file(tmp_path / "z-last.jpg", b"z")
    second = _write_file(tmp_path / "a-first.jpg", b"a")

    with session_factory.begin() as session:
        _add_media_file_row(
            session,
            path=str(first.resolve(strict=False)),
            status=MediaFileStatus.INGESTED,
            hash_sha256=None,
        )
        _add_media_file_row(
            session,
            path=str(second.resolve(strict=False)),
            status=MediaFileStatus.INGESTED,
            hash_sha256=None,
        )

    payload = service.get_ledger_hash_audit(sample_limit=1).to_dict()

    assert payload["missing_hash"] == 2
    assert payload["sample_missing_hash_paths"] == [str(second.resolve(strict=False))]


def test_hash_audit_missing_file_is_non_fatal(session_factory, tmp_path: Path) -> None:
    service = OperatorConsoleReadService(session_factory)
    missing = tmp_path / "gone.jpg"

    with session_factory.begin() as session:
        _add_media_file_row(
            session,
            path=str(missing.resolve(strict=False)),
            status=MediaFileStatus.INGESTED,
            hash_sha256="a" * 64,
        )

    payload = service.get_ledger_hash_audit().to_dict()

    assert payload["total_files"] == 1
    assert payload["hash_mismatches"] == 0


def test_hash_audit_rejects_blank_root_path(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)

    try:
        service.get_ledger_hash_audit(root_path="  ")
    except ValueError as exc:
        assert "root_path" in str(exc)
    else:
        raise AssertionError("Expected ValueError for blank root_path")
