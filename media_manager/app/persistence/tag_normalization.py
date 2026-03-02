from __future__ import annotations

import os
import re
import unicodedata

from media_manager.app.core.config import load_environment

_TRUTHY_VALUES = {"1", "true", "yes", "on"}


def _resolve_remove_punctuation(remove_punctuation: bool | None) -> bool:
    if remove_punctuation is not None:
        return remove_punctuation
    load_environment()
    raw = os.getenv("MEDIA_MANAGER_TAG_NORMALIZATION_REMOVE_PUNCTUATION", "0").strip().lower()
    return raw in _TRUTHY_VALUES


def normalize_tag_name(name: str, *, remove_punctuation: bool | None = None) -> str:
    normalized = unicodedata.normalize("NFKC", name).strip().lower()
    if _resolve_remove_punctuation(remove_punctuation):
        normalized = "".join(ch for ch in normalized if not unicodedata.category(ch).startswith("P"))
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        raise ValueError("Tag name must not be empty after normalization.")
    return normalized


def normalize_tag_list(tags: list[str], *, remove_punctuation: bool | None = None) -> list[str]:
    normalized = {
        normalize_tag_name(tag, remove_punctuation=remove_punctuation)
        for tag in tags
    }
    return sorted(normalized)
