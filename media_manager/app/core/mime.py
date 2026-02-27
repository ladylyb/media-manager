"""MIME detection and deterministic media kind classification."""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MimeInfo:
    mime_type: str
    media_kind: str


def detect_mime(path: Path) -> MimeInfo:
    guessed, _ = mimetypes.guess_type(path.name)
    mime = guessed or "application/octet-stream"

    if mime.startswith("image/"):
        kind = "photo"
    elif mime.startswith("video/"):
        kind = "video"
    else:
        suffix = path.suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png", ".heic", ".webp", ".gif", ".bmp", ".tif", ".tiff"}:
            kind = "photo"
        elif suffix in {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mpeg", ".mpg"}:
            kind = "video"
        else:
            # Default to photo bucket for unknowns to keep deterministic canonical pathing.
            kind = "photo"

    return MimeInfo(mime_type=mime, media_kind=kind)
