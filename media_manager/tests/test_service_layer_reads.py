from __future__ import annotations

from dataclasses import dataclass

import pytest

import media_manager.app.service_layer.reads as reads_module
from media_manager.app.service_layer.reads import ReadServices


@dataclass
class _FakeCache:
    invalidations: list[tuple[str, ...]]

    def get(self, _key: str):  # type: ignore[no-untyped-def]
        return None

    def set(self, _key: str, _payload, ttl_s: int) -> None:  # type: ignore[no-untyped-def]
        _ = ttl_s


def test_duplicate_bin_items_reuses_reclaim_archive_page(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeOperatorConsoleReadService:
        def __init__(self, _session_factory) -> None:
            pass

        def get_duplicate_reclaim_archive_page(self, *, page: int, limit: int):  # type: ignore[no-untyped-def]
            assert page == 2
            assert limit == 5
            return type("Page", (), {"to_dict": lambda self: {"page": 2, "limit": 5, "items": [{"item_status": "ARCHIVED"}]}})()

    monkeypatch.setattr(reads_module, "OperatorConsoleReadService", _FakeOperatorConsoleReadService)

    services = ReadServices(session_factory=object(), cache=_FakeCache(invalidations=[]))  # type: ignore[arg-type]

    payload = services.duplicate_bin_items(page=2, limit=5)

    assert payload["page"] == 2
    assert payload["limit"] == 5
    assert payload["items"][0]["item_status"] == "ARCHIVED"
