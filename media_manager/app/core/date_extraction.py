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
            for fmt in (
                "%Y:%m:%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d_%H%M%S",
            ):
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


def _from_filesystem(path: Path, stat_meta: dict | None) -> DateInfo | None:
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
