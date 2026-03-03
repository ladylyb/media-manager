"""Lightweight TTL cache with explicit invalidation for read services."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class _Entry:
    value: object
    expires_at: float


class ServiceCache:
    """Simple in-process cache for short-lived read data."""

    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> object | None:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._entries.pop(key, None)
                return None
            return entry.value

    def set(self, key: str, value: object, *, ttl_s: float) -> None:
        expires = time.monotonic() + max(float(ttl_s), 0.0)
        with self._lock:
            self._entries[key] = _Entry(value=value, expires_at=expires)

    def invalidate(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._entries.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
