from __future__ import annotations

import time

from media_manager.app.service_layer.cache import ServiceCache


def test_service_cache_set_get_and_invalidate() -> None:
    cache = ServiceCache()
    cache.set("dashboard_summary", {"total_files": 1}, ttl_s=10)
    assert cache.get("dashboard_summary") == {"total_files": 1}
    cache.invalidate("dashboard_summary")
    assert cache.get("dashboard_summary") is None


def test_service_cache_expires_entries() -> None:
    cache = ServiceCache()
    cache.set("status", {"active_phase": "phase13"}, ttl_s=0.01)
    time.sleep(0.02)
    assert cache.get("status") is None
