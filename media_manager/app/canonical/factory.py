from __future__ import annotations

import os

from media_manager.app.canonical.policies import (
    CanonicalPolicy,
    ExifFilenameFallbackPolicy,
    FirstSeenPolicy,
    PreferRootPolicy,
    ShortestPathPolicy,
)
from media_manager.app.core.config import load_environment
from media_manager.app.core.errors import CanonicalPolicyException


def resolve_default_policy_name() -> str:
    load_environment()
    return os.getenv("MEDIA_CANONICAL_POLICY", "FIRST_SEEN").strip().upper()


def build_canonical_policy(policy_name: str) -> CanonicalPolicy:
    normalized = policy_name.strip().upper()
    if normalized == "FIRST_SEEN":
        return FirstSeenPolicy()
    if normalized == "PREFER_ROOT":
        return PreferRootPolicy()
    if normalized == "SHORTEST_PATH":
        return ShortestPathPolicy()
    if normalized == "EXIF_FILENAME_FALLBACK":
        return ExifFilenameFallbackPolicy()
    raise CanonicalPolicyException(f"Unknown canonical policy: {policy_name}")

