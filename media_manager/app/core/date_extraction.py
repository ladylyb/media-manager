"""Deterministic date extraction with explicit source precedence.

Priority:
1) metadata
2) filename
3) filesystem stat timestamps
4) unknown
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


_DATE_PATTERNS = [
    re.compile(r"(?P<y>19\d{2}|20\d{2})[-_]?((?P<m>0[1-9]|1[0-2]))[-_]?((?P<d>0[1-9]|[12]\d|3[01]))"),
]


@dataclass(frozen=True)
class DateInfo:
    year: str | None
    month: str | None
    source: str


def _from_metadata(stat_meta: dict | None) -> DateInfo | None:
    if not stat_meta:
        return None

    for key in ("metadata_datetime", "exif_datetime", "captured_at"):
        value = stat_meta.get(key)
        if not value:
            continue

        if isinstance(value, datetime):
            dt = value.astimezone(UTC)
        else:
            parsed: datetime | None = None
            try:
                parsed = datetime.fromisoformat(str(value))
            except ValueError:
                parsed = None
            if parsed is not None:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                else:
                    parsed = parsed.astimezone(UTC)
            for fmt in (
                "%Y:%m:%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d_%H%M%S",
            ):
                if parsed is not None:
                    break
                try:
                    parsed = datetime.strptime(str(value), fmt)
                    break
                except ValueError:
                    continue
            if parsed is None:
                continue
            dt = parsed.replace(tzinfo=UTC)

        return DateInfo(year=f"{dt.year:04}", month=f"{dt.month:02}", source="metadata")

    return None


def _from_filename(filename: str) -> DateInfo | None:
    for pattern in _DATE_PATTERNS:
        match = pattern.search(filename)
        if not match:
            continue
        year = match.group("y")
        month = match.group("m")
        return DateInfo(year=year, month=month, source="filename")
    return None


def filename_has_date(filename: str) -> bool:
    return _from_filename(filename) is not None


def _from_filesystem(path: Path, stat_meta: dict | None) -> DateInfo | None:
    # Platform semantics note:
    # - `st_mtime` is modification time across platforms and is the most portable
    #   timestamp for deterministic fallback.
    # - `st_ctime` differs by OS: inode metadata change time on Unix-like systems
    #   and creation time on Windows. We only use it when explicitly supplied in
    #   `stat_meta` and `mtime` is absent.
    # - `st_birthtime` is not universally available, so it is intentionally not
    #   part of this fallback path.
    # This fallback is acceptable because filesystem timestamps are only used
    # after metadata and filename extraction fail, and provide a stable,
    # deterministic ordering source for unknown-date assets.
    epoch = None
    if stat_meta:
        epoch = stat_meta.get("mtime") or stat_meta.get("ctime")
    if epoch is None:
        try:
            stat = path.stat()
            epoch = stat.st_mtime
        except FileNotFoundError:
            return None

    dt = datetime.fromtimestamp(float(epoch), tz=UTC)
    return DateInfo(year=f"{dt.year:04}", month=f"{dt.month:02}", source="filesystem")


def extract_best_date(
    path: Path,
    mime_type: str,
    stat_meta: dict | None = None,
    filename: str | None = None,
) -> DateInfo:
    # mime_type is accepted to keep stable API for future media-specific metadata extraction.
    _ = mime_type

    from_metadata = _from_metadata(stat_meta)
    if from_metadata is not None:
        return from_metadata

    name = filename or path.name
    from_name = _from_filename(name)
    if from_name is not None:
        return from_name

    from_fs = _from_filesystem(path, stat_meta)
    if from_fs is not None:
        return from_fs

    return DateInfo(year=None, month=None, source="unknown")
