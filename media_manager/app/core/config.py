from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

_ENV_LOADED = False


def load_environment() -> None:
    """Load repository .env once, without overriding existing process env vars."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    repo_root = Path(__file__).resolve().parents[3]
    load_dotenv(dotenv_path=repo_root / ".env", override=False)
    _ENV_LOADED = True
