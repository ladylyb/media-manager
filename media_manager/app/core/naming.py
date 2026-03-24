from __future__ import annotations

from media_manager.app.persistence.models import NamingStrategyDB


DEFAULT_OWNER = "LL"
DEFAULT_CONTEXT = "General"
UNKNOWN_OWNER = "UNKNOWN"
UNKNOWN_CONTEXT = "UNKNOWN"


def is_unknown_owner_context_value(value: str | None) -> bool:
    return (value or "").strip().upper() == "UNKNOWN"


def normalize_naming_strategy(raw: str | None) -> str:
    value = (raw or NamingStrategyDB.SHARED_CANONICAL_NAME.value).strip().upper()
    allowed = {item.value for item in NamingStrategyDB}
    if value not in allowed:
        raise ValueError(
            "naming_strategy must be one of: "
            + ", ".join(sorted(allowed))
        )
    return value
