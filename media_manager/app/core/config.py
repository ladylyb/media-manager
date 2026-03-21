from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_ENV_LOADED = False

REQUIRED_METADATA_CODES = ["OWNER", "CONTEXT", "TAKEN_DT"]
OPTIONAL_METADATA_CODES = ["GPS", "CAMERA_MODEL", "TAGS"]


@dataclass(frozen=True)
class StorageRoots:
    canonical_root: Path
    duplicate_root: Path

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


def _nearest_existing_parent(path: Path) -> Path | None:
    candidate = path
    while True:
        if candidate.exists():
            return candidate
        if candidate.parent == candidate:
            return None
        candidate = candidate.parent


def _validate_storage_root(env_name: str, raw: str) -> Path:
    load_environment()
    raw = raw.strip()
    if not raw:
        raise RuntimeError(f"{env_name} is required.")

    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise RuntimeError(f"{env_name} must be an absolute path: {path}")

    existing = _nearest_existing_parent(path)
    if existing is None:
        raise RuntimeError(f"{env_name} has no existing writable parent: {path}")
    if not existing.is_dir():
        raise RuntimeError(f"{env_name} must resolve under a directory path: {path}")
    if not os.access(existing, os.W_OK | os.X_OK):
        raise RuntimeError(f"{env_name} is not writable by the current runtime: {path}")

    return path


def resolve_storage_roots() -> StorageRoots:
    load_environment()
    canonical_raw = os.getenv("MEDIA_CANONICAL_STORAGE_PATH", "")
    duplicate_raw = os.getenv("MEDIA_DUPLICATE_STORAGE_PATH", "")
    return StorageRoots(
        canonical_root=_validate_storage_root("MEDIA_CANONICAL_STORAGE_PATH", canonical_raw),
        duplicate_root=_validate_storage_root("MEDIA_DUPLICATE_STORAGE_PATH", duplicate_raw),
    )
