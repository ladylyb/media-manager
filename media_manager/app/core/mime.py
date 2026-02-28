"""MIME detection and deterministic media kind classification.

Deterministic classification rules:
- If `mimetypes.guess_type()` returns `None`, MIME is normalized to
  `application/octet-stream`.
- Only `image/*` and `video/*` MIME values are considered supported media.
- Unsupported MIME values (including `application/octet-stream`) are marked
  unsupported so the planner can deterministically skip them.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MimeInfo:
    mime_type: str
    media_kind: str
    is_supported: bool


def detect_mime(path: Path) -> MimeInfo:
    guessed, _ = mimetypes.guess_type(path.name)
    mime = guessed or "application/octet-stream"

    if mime.startswith("image/"):
        return MimeInfo(mime_type=mime, media_kind="photo", is_supported=True)
    elif mime.startswith("video/"):
        return MimeInfo(mime_type=mime, media_kind="video", is_supported=True)

    return MimeInfo(mime_type=mime, media_kind="unsupported", is_supported=False)
