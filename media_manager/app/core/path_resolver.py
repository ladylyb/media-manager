"""Pure storage path resolution helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def _media_folder(media_type: str) -> str:
    if media_type == "VID":
        return "Videos"
    return "Photos"


def duplicate_filename(canonical_filename: str, duplicate_index: int) -> str:
    if duplicate_index < 1:
        raise ValueError("duplicate_index must be >= 1")
    path = Path(canonical_filename)
    return f"{path.stem}_DUP{duplicate_index}{path.suffix}"


def reserve_planned_path(
    source_path: Path,
    desired_path: Path,
    reserved_paths: set[str],
) -> tuple[Path, bool]:
    desired_key = str(desired_path.resolve(strict=False))
    source_key = str(source_path.resolve(strict=False))
    if source_key == desired_key:
        reserved_paths.add(desired_key)
        return desired_path, False
    if desired_key not in reserved_paths:
        reserved_paths.add(desired_key)
        return desired_path, False

    stem = desired_path.stem
    suffix = desired_path.suffix
    idx = 1
    while True:
        candidate = desired_path.with_name(f"{stem}_{idx}{suffix}")
        candidate_key = str(candidate.resolve(strict=False))
        if source_key == candidate_key:
            reserved_paths.add(candidate_key)
            return candidate, False
        if candidate_key not in reserved_paths:
            reserved_paths.add(candidate_key)
            return candidate, True
        idx += 1


def resolve_canonical_path(
    *,
    canonical_root: Path,
    media_type: str,
    taken_datetime: datetime,
    canonical_filename: str,
) -> Path:
    return (
        canonical_root
        / "Media"
        / _media_folder(media_type)
        / taken_datetime.strftime("%Y")
        / taken_datetime.strftime("%m")
        / canonical_filename
    )


def resolve_duplicate_path(
    *,
    duplicate_root: Path,
    media_type: str,
    taken_datetime: datetime,
    canonical_filename: str,
    duplicate_index: int,
) -> Path:
    return (
        duplicate_root
        / "Media"
        / _media_folder(media_type)
        / taken_datetime.strftime("%Y")
        / taken_datetime.strftime("%m")
        / duplicate_filename(canonical_filename, duplicate_index)
    )
