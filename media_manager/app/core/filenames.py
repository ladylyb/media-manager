"""Deterministic canonical filename helpers for apply-stage enforcement."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".wmv", ".3gp", ".webm"}
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_]+$")


def infer_media_type_from_extension(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in _IMAGE_EXTENSIONS:
        return "IMG"
    if suffix in _VIDEO_EXTENSIONS:
        return "VID"
    return None


def _parse_exif_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC)


def extract_taken_datetime(path: Path) -> datetime:
    """Extract capture datetime from EXIF when possible, else file creation timestamp."""
    try:
        from PIL import Image, UnidentifiedImageError
    except Exception:
        Image = None  # type: ignore[assignment]
        UnidentifiedImageError = Exception  # type: ignore[assignment]

    if Image is not None:
        try:
            with Image.open(path) as image:
                exif = image.getexif()
            for tag_code in (36867, 36868, 306):  # DateTimeOriginal, DateTimeDigitized, DateTime
                dt = _parse_exif_datetime(exif.get(tag_code) if exif else None)
                if dt is not None:
                    return dt
        except (FileNotFoundError, OSError, UnidentifiedImageError):
            pass

    stat = path.stat()
    return datetime.fromtimestamp(float(stat.st_ctime), tz=UTC)


def _normalize_extension(extension: str) -> str:
    ext = extension.lower()
    if not ext:
        raise ValueError("extension is required")
    if ext.startswith("."):
        ext = ext[1:]
    return ext


def _validate_token(name: str, value: str, max_len: int | None = None) -> None:
    if not value:
        raise ValueError(f"{name} is required")
    if max_len is not None and len(value) > max_len:
        raise ValueError(f"{name} must be <= {max_len} characters")
    if not _TOKEN_RE.fullmatch(value):
        raise ValueError(f"{name} must contain only alphanumeric characters or underscore")


def generate_canonical_filename(
    media_type: str,
    taken_datetime: datetime,
    extension: str,
    owner: str = "LL",
    context: str = "General",
) -> str:
    """Return deterministic canonical filename: [Type]_[YYYYMMDD]_[HHMMSS]_[Owner]_[Context].[ext]."""
    media = media_type.upper()
    if media not in {"IMG", "VID"}:
        raise ValueError("media_type must be IMG or VID")

    _validate_token("owner", owner)
    _validate_token("context", context, max_len=20)

    dt_utc = taken_datetime.astimezone(UTC)
    date_part = dt_utc.strftime("%Y%m%d")
    time_part = dt_utc.strftime("%H%M%S")
    ext = _normalize_extension(extension)
    return f"{media}_{date_part}_{time_part}_{owner}_{context}.{ext}"
