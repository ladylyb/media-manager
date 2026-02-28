from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

import media_manager.app.core.metadata_extractor as metadata_extractor
from media_manager.app.persistence.models import ContentObject, MediaMetadata, MetadataCode


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
        lambda _path: {"TAKEN_DT": "2024-01-11T10:11:12+00:00", "CAMERA_MODEL": "Nikon"},
    )

    rows = metadata_extractor.extract_file_metadata(path, file_hash="h1")
    as_dict = {row.code_type: row.decode_value for row in rows}
    assert as_dict["TAKEN_DT"] == "2024-01-11T10:11:12+00:00"
    assert as_dict["OWNER"] == "LL"
    assert as_dict["CONTEXT"] == "General"
    assert as_dict["CAMERA_MODEL"] == "Nikon"


def test_extract_file_metadata_falls_back_to_filesystem_timestamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_file(tmp_path / "a.jpg", b"x")
    monkeypatch.setattr(metadata_extractor, "_extract_optional_exif", lambda _path: {})
    fixed = datetime(2024, 1, 1, 1, 2, 3, tzinfo=UTC).timestamp()
    monkeypatch.setattr(Path, "stat", lambda self: type("S", (), {"st_ctime": fixed, "st_mtime": fixed})())

    rows = metadata_extractor.extract_file_metadata(path, file_hash="h1")
    as_dict = {row.code_type: row.decode_value for row in rows}
    assert as_dict["TAKEN_DT"] == datetime.fromtimestamp(fixed, tz=UTC).isoformat()
    assert as_dict["FS_CTIME"] == datetime.fromtimestamp(fixed, tz=UTC).isoformat()
    assert as_dict["FS_MTIME"] == datetime.fromtimestamp(fixed, tz=UTC).isoformat()


def test_upsert_metadata_batch_prevents_duplicates(session_factory) -> None:
    with session_factory() as session:
        session.add(ContentObject(hash="h1", size_bytes=100))
        session.commit()

    rows = [
        metadata_extractor.MetadataItem(code_type="OWNER", decode_value="LL"),
        metadata_extractor.MetadataItem(code_type="CONTEXT", decode_value="General"),
    ]
    with session_factory() as session:
        metadata_extractor.upsert_metadata_batch(session, rows, "h1")
        session.commit()
    with session_factory() as session:
        metadata_extractor.upsert_metadata_batch(session, rows, "h1")
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
        session.add(ContentObject(hash=file_hash, size_bytes=1))
        session.commit()

    with session_factory() as session:
        metadata_extractor.pre_extract_for_paths(session, [path], run_id="run-1")
        session.commit()

    assert len(calls) >= 1
    assert any(call.get("file_hash") == file_hash for call in calls)
    assert any(call.get("action") in {"EXTRACTED", "DEFAULT_USED"} for call in calls)
    assert any(call.get("codes_extracted") for call in calls)
