from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_ENV_LOADED = False

REQUIRED_METADATA_CODES = ["OWNER", "CONTEXT", "TAKEN_DT"]
OPTIONAL_METADATA_CODES = ["GPS", "CAMERA_MODEL", "TAGS"]


def load_environment() -> None:
    """Load repository .env once, without overriding existing process env vars."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    repo_root = Path(__file__).resolve().parents[3]
    load_dotenv(dotenv_path=repo_root / ".env", override=False)
    _ENV_LOADED = True


def resolve_required_metadata_codes() -> set[str]:
    load_environment()
    raw = os.getenv("MEDIA_REQUIRED_CODES")
    if not raw:
        return set(REQUIRED_METADATA_CODES)

    parsed = {item.strip().upper() for item in raw.split(",") if item.strip()}
    if not parsed:
        return set(REQUIRED_METADATA_CODES)
    return parsed
