"""Deterministic in-memory metadata cache keyed by file hash."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetadataCacheStats:
    hits: int
    misses: int
    size: int

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total


class MetadataCache:
    """Simple deterministic cache for metadata lookups.

    The cache is intentionally simple: no TTL, no random eviction, and no async
    behavior. This keeps repeated planning runs deterministic and measurable.
    """

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, str]] = {}
        self._hits = 0
        self._misses = 0

    def get(self, file_hash: str) -> dict[str, str] | None:
        value = self._cache.get(file_hash)
        if value is None:
            self._misses += 1
            return None
        self._hits += 1
        return value

    def set(self, file_hash: str, metadata: dict[str, str]) -> None:
        self._cache[file_hash] = metadata

    def clear(self) -> None:
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> MetadataCacheStats:
        return MetadataCacheStats(hits=self._hits, misses=self._misses, size=len(self._cache))

