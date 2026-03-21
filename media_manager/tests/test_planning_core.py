from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from media_manager.app.core.date_extraction import extract_best_date
from media_manager.app.core.mime import detect_mime
from media_manager.app.core.path_resolver import duplicate_filename, resolve_canonical_path, resolve_duplicate_path


def test_date_extraction_priority_metadata_over_filename_and_fs(tmp_path: Path) -> None:
    p = tmp_path / "IMG_20200101_010101.jpg"
    p.write_bytes(b"abc")

    result = extract_best_date(
        path=p,
        mime_type="image/jpeg",
        stat_meta={"mtime": 946684800, "metadata_datetime": "2023:11:12 10:09:08"},
        filename=p.name,
    )

    assert result.source == "metadata"
    assert result.year == "2023"
    assert result.month == "11"


def test_date_extraction_priority_filename_over_fs(tmp_path: Path) -> None:
    p = tmp_path / "VID_20211231_233000.mp4"
    p.write_bytes(b"abc")

    result = extract_best_date(
        path=p,
        mime_type="video/mp4",
        stat_meta={"mtime": 946684800},
        filename=p.name,
    )

    assert result.source == "filename"
    assert result.year == "2021"
    assert result.month == "12"


def test_date_extraction_fs_over_unknown(tmp_path: Path) -> None:
    p = tmp_path / "random.bin"
    p.write_bytes(b"abc")

    result = extract_best_date(
        path=p,
        mime_type="application/octet-stream",
        stat_meta={"mtime": 1609459200},
        filename=p.name,
    )

    assert result.source == "filesystem"
    assert result.year == "2021"
    assert result.month == "01"


def test_date_extraction_filesystem_fallback_uses_path_stat_when_higher_sources_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "no-date-name.bin"
    p.write_bytes(b"abc")

    # 2022-03-01T00:00:00Z
    mocked_epoch = 1646092800
    monkeypatch.setattr(Path, "stat", lambda self: SimpleNamespace(st_mtime=mocked_epoch))

    result = extract_best_date(
        path=p,
        mime_type="application/octet-stream",
        stat_meta={},
        filename=p.name,
    )

    assert result.source == "filesystem"
    assert result.year == "2022"
    assert result.month == "03"


def test_canonical_path_resolution_and_duplicates(tmp_path: Path) -> None:
    photo = tmp_path / "IMG_20240203.jpg"
    photo.write_bytes(b"abc")
    taken = datetime(2024, 2, 3, 1, 2, 3, tzinfo=UTC)

    target = resolve_canonical_path(
        canonical_root=tmp_path / "canonical",
        media_type="IMG",
        taken_datetime=taken,
        canonical_filename=photo.name,
    )
    assert target == tmp_path / "canonical" / "Media" / "Photos" / "2024" / "02" / "IMG_20240203.jpg"

    duplicate = resolve_duplicate_path(
        duplicate_root=tmp_path / "duplicates",
        media_type="VID",
        taken_datetime=taken,
        canonical_filename="VID_20240203_010203_LL_General.mp4",
        duplicate_index=2,
    )
    assert duplicate == (
        tmp_path
        / "duplicates"
        / "Media"
        / "Videos"
        / "2024"
        / "02"
        / "VID_20240203_010203_LL_General_DUP2.mp4"
    )
    assert duplicate_filename("IMG_20240203_010203_LL_General.jpg", 3) == "IMG_20240203_010203_LL_General_DUP3.jpg"


def test_mime_detection_classifies_photo_video(tmp_path: Path) -> None:
    p1 = tmp_path / "a.jpg"
    p2 = tmp_path / "b.mp4"
    p1.write_bytes(b"x")
    p2.write_bytes(b"y")

    assert detect_mime(p1).media_kind == "photo"
    assert detect_mime(p2).media_kind == "video"


def test_mime_detection_marks_unsupported_types(tmp_path: Path) -> None:
    p = tmp_path / "unknown.customext"
    p.write_bytes(b"x")

    info = detect_mime(p)
    assert info.mime_type == "application/octet-stream"
    assert info.media_kind == "unsupported"
    assert info.is_supported is False
