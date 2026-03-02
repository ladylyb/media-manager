"""Deterministic TTL cache for optional read-optimization paths only.

This cache is intentionally lightweight and is used only for read-side optimization.
It must never be used for planner/apply write semantics.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


@dataclass(frozen=True)
class TTLCacheStats:
    hits: int
    misses: int
    size: int


class TTLCache(Generic[K, V]):
    def __init__(
        self,
        *,
        ttl_seconds: float,
        time_source: Callable[[], float] | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")
        self._ttl_seconds = float(ttl_seconds)
        self._time_source = time_source or time.monotonic
        self._entries: dict[K, tuple[float, V]] = {}
        self._hits = 0
        self._misses = 0

    def get(self, key: K) -> V | None:
        now = self._time_source()
        entry = self._entries.get(key)
        if entry is None:
            self._misses += 1
            return None

        expires_at, value = entry
        if now >= expires_at:
            self._entries.pop(key, None)
            self._misses += 1
            return None

        self._hits += 1
        return value

    def set(self, key: K, value: V) -> None:
        expires_at = self._time_source() + self._ttl_seconds
        self._entries[key] = (expires_at, value)

    def clear(self) -> None:
        self._entries.clear()

    def stats(self) -> TTLCacheStats:
        return TTLCacheStats(hits=self._hits, misses=self._misses, size=len(self._entries))
