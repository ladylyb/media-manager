"""Canonical path resolution for planning-only workflow."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from media_manager.app.core.date_extraction import DateInfo


def _to_posix_path(*parts: str) -> str:
    return str(PurePosixPath(*parts))


def resolve_canonical_path(path: Path, media_kind: str, date_info: DateInfo, hash_value: str) -> str:
    filename = path.name
    kind = media_kind.lower()

    if kind not in {"photo", "video"}:
        kind = "photo"

    if date_info.source == "unknown" or not date_info.year or not date_info.month:
        if kind == "video":
            return _to_posix_path("Media", "Videos", "unknown", filename)
        return _to_posix_path("Media", "Photos", "unknown", filename)

    if kind == "video":
        return _to_posix_path("Media", "Videos", date_info.year, date_info.month, filename)

    return _to_posix_path("Media", "Photos", date_info.year, date_info.month, filename)


def resolve_duplicate_path(path: Path, hash_value: str, prefix_len: int = 8) -> str:
    filename = path.name
    prefix = hash_value[:prefix_len]
    return _to_posix_path("Media", "duplicates", prefix, filename)
