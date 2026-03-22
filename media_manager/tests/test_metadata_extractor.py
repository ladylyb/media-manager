from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

import media_manager.app.core.metadata_extractor as metadata_extractor
from media_manager.app.persistence.models import FileContent, MediaMetadata, MetadataCode


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_extract_file_metadata_uses_exif_taken_dt_when_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_file(tmp_path / "a.jpg", b"x")
    monkeypatch.setattr(
        metadata_extractor,
        "_extract_optional_exif",
        lambda _path: {"EXIF_DT_ORIGINAL": "2024-01-11T10:11:12+00:00", "CAMERA_MODEL": "Nikon"},
    )

    rows = metadata_extractor.extract_file_metadata(path, file_hash="h1")
    as_dict = {row.code_type: row.decode_value for row in rows}
    assert as_dict["EXIF_DT_ORIGINAL"] == "2024-01-11T10:11:12+00:00"
    assert as_dict["CLASSIFICATION_DT"] == "2024-01-11T10:11:12+00:00"
    assert as_dict["CLASSIFICATION_DT_SOURCE"] == "EXIF_DT_ORIGINAL"
    assert as_dict["CLASSIFICATION_DT_POLICY"] == "EARLIEST_TRUSTWORTHY_V1"
    assert as_dict["TAKEN_DT"] == "2024-01-11T10:11:12+00:00"
    assert as_dict["TAKEN_DT_SOURCE"] == "metadata"
    assert as_dict["OWNER"] == "LL"
    assert as_dict["CONTEXT"] == "General"
    assert as_dict["CAMERA_MODEL"] == "Nikon"


def test_extract_file_metadata_uses_filename_date_when_exif_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_file(tmp_path / "IMG_20240214_235959.jpg", b"x")
    monkeypatch.setattr(metadata_extractor, "_extract_optional_exif", lambda _path: {})
    fixed = datetime(2024, 1, 1, 1, 2, 3, tzinfo=UTC).timestamp()
    monkeypatch.setattr(
        metadata_extractor,
        "_read_file_stat",
        lambda _path: type("S", (), {"st_ctime": fixed, "st_mtime": fixed})(),
    )

    rows = metadata_extractor.extract_file_metadata(path, file_hash="h1")
    as_dict = {row.code_type: row.decode_value for row in rows}
    assert as_dict["FILENAME_DT"] == "2024-02-14T23:59:59+00:00"
    assert as_dict["CLASSIFICATION_DT"] == "2024-01-01T01:02:03+00:00"
    assert as_dict["CLASSIFICATION_DT_SOURCE"] == "FS_MTIME"
    assert as_dict["TAKEN_DT"] == "2024-01-01T01:02:03+00:00"
    assert as_dict["TAKEN_DT_SOURCE"] == "filesystem"


def test_extract_file_metadata_uses_earliest_mtime_when_ctime_is_newer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_file(tmp_path / "a.jpg", b"x")
    monkeypatch.setattr(metadata_extractor, "_extract_optional_exif", lambda _path: {})
    mtime = datetime(2024, 1, 1, 1, 2, 3, tzinfo=UTC).timestamp()
    ctime = datetime(2026, 3, 22, 8, 23, 5, tzinfo=UTC).timestamp()
    monkeypatch.setattr(
        metadata_extractor,
        "_read_file_stat",
        lambda _path: type("S", (), {"st_ctime": ctime, "st_mtime": mtime})(),
    )

    rows = metadata_extractor.extract_file_metadata(path, file_hash="h1")
    as_dict = {row.code_type: row.decode_value for row in rows}
    assert as_dict["CLASSIFICATION_DT"] == datetime.fromtimestamp(mtime, tz=UTC).isoformat()
    assert as_dict["CLASSIFICATION_DT_SOURCE"] == "FS_MTIME"
    assert as_dict["TAKEN_DT"] == datetime.fromtimestamp(mtime, tz=UTC).isoformat()
    assert as_dict["TAKEN_DT_SOURCE"] == "filesystem"
    assert as_dict["FS_CTIME"] == datetime.fromtimestamp(ctime, tz=UTC).isoformat()
    assert as_dict["FS_MTIME"] == datetime.fromtimestamp(mtime, tz=UTC).isoformat()


def test_extract_file_metadata_uses_only_ctime_when_no_other_timestamp_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_file(tmp_path / "a.jpg", b"x")
    monkeypatch.setattr(metadata_extractor, "_extract_optional_exif", lambda _path: {})
    fixed = datetime(2024, 1, 1, 1, 2, 3, tzinfo=UTC).timestamp()
    rejected_future = datetime(2100, 1, 1, 0, 0, 0, tzinfo=UTC).timestamp()
    monkeypatch.setattr(
        metadata_extractor,
        "_read_file_stat",
        lambda _path: type("S", (), {"st_ctime": fixed, "st_mtime": rejected_future})(),
    )

    rows = metadata_extractor.extract_file_metadata(path, file_hash="h1")
    as_dict = {row.code_type: row.decode_value for row in rows}
    assert as_dict["CLASSIFICATION_DT"] == datetime.fromtimestamp(fixed, tz=UTC).isoformat()
    assert as_dict["CLASSIFICATION_DT_SOURCE"] == "FS_CTIME"
    assert as_dict["TAKEN_DT"] == datetime.fromtimestamp(fixed, tz=UTC).isoformat()
    assert as_dict["TAKEN_DT_SOURCE"] == "filesystem"
    assert "FS_MTIME" in as_dict["CLASSIFICATION_DT_REJECTED_SOURCES"]


def test_extract_file_metadata_rejects_invalid_early_exif_and_uses_next_earliest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_file(tmp_path / "IMG_20240214_235959.jpg", b"x")
    monkeypatch.setattr(
        metadata_extractor,
        "_extract_optional_exif",
        lambda _path: {"EXIF_DT_ORIGINAL": "1970-01-01T00:00:00+00:00"},
    )
    mtime = datetime(2024, 2, 20, 1, 2, 3, tzinfo=UTC).timestamp()
    ctime = datetime(2026, 3, 22, 8, 23, 5, tzinfo=UTC).timestamp()
    monkeypatch.setattr(
        metadata_extractor,
        "_read_file_stat",
        lambda _path: type("S", (), {"st_ctime": ctime, "st_mtime": mtime})(),
    )

    rows = metadata_extractor.extract_file_metadata(path, file_hash="h1")
    as_dict = {row.code_type: row.decode_value for row in rows}
    assert as_dict["CLASSIFICATION_DT"] == "2024-02-14T23:59:59+00:00"
    assert as_dict["CLASSIFICATION_DT_SOURCE"] == "FILENAME_DT"
    assert as_dict["CLASSIFICATION_DT_REJECTED_SOURCES"] == "EXIF_DT_ORIGINAL"
    assert as_dict["TAKEN_DT"] == "2024-02-14T23:59:59+00:00"


def test_extract_file_metadata_rejects_future_timestamp_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_file(tmp_path / "a.jpg", b"x")
    monkeypatch.setattr(metadata_extractor, "_extract_optional_exif", lambda _path: {})
    future = datetime(2100, 3, 4, 0, 0, 0, tzinfo=UTC).timestamp()
    ctime = datetime(2024, 2, 1, 12, 0, 0, tzinfo=UTC).timestamp()
    monkeypatch.setattr(
        metadata_extractor,
        "_read_file_stat",
        lambda _path: type("S", (), {"st_ctime": ctime, "st_mtime": future})(),
    )

    rows = metadata_extractor.extract_file_metadata(path, file_hash="h1")
    as_dict = {row.code_type: row.decode_value for row in rows}
    assert as_dict["CLASSIFICATION_DT"] == "2024-02-01T12:00:00+00:00"
    assert as_dict["CLASSIFICATION_DT_SOURCE"] == "FS_CTIME"
    assert "FS_MTIME" in as_dict["CLASSIFICATION_DT_REJECTED_SOURCES"]


def test_upsert_metadata_for_content_prevents_duplicates(session_factory) -> None:
    with session_factory() as session:
        content = FileContent(sha256_hash="h1")
        session.add(content)
        session.flush()
        content_id = content.content_id
        session.commit()

    rows = [
        metadata_extractor.MetadataItem(code_type="OWNER", decode_value="LL"),
        metadata_extractor.MetadataItem(code_type="CONTEXT", decode_value="General"),
    ]
    with session_factory() as session:
        metadata_extractor.upsert_metadata_for_content(session, rows, content_id)
        session.commit()
    with session_factory() as session:
        metadata_extractor.upsert_metadata_for_content(session, rows, content_id)
        session.commit()

    with session_factory() as session:
        codes = session.scalars(select(MetadataCode)).all()
        data = session.scalars(select(MediaMetadata)).all()
        assert len(codes) == 2
        assert len(data) == 2


def test_pre_extract_logs_structured_fields(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict] = []

    def _capture(_message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        calls.append(kwargs.get("extra", {}))

    monkeypatch.setattr(metadata_extractor.logger, "info", _capture)
    path = _write_file(tmp_path / "a.jpg", b"x")
    file_hash = metadata_extractor.sha256_file(path)
    with session_factory() as session:
        metadata_extractor.pre_extract_for_paths(session, [path], run_id="run-1")
        session.commit()

    assert len(calls) >= 1
    assert any(call.get("file_hash") == file_hash for call in calls)
    assert any(call.get("action") in {"EXTRACTED", "DEFAULT_USED"} for call in calls)
    assert any(call.get("codes_extracted") for call in calls)
