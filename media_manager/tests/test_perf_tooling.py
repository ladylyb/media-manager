from __future__ import annotations

from media_manager.app.core.metadata_cache import MetadataCache
from media_manager.app.core.metadata_extractor import MetadataItem, upsert_metadata_bulk
import media_manager.app.core.perf as perf_module
from media_manager.app.core.perf import measure_block, profile_performance
from media_manager.app.persistence.models import FileContent


def test_profile_performance_emits_metric(monkeypatch) -> None:
    calls: list[str] = []

    def _capture(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        calls.append(message)

    monkeypatch.setattr(perf_module.logger, "info", _capture)

    @profile_performance("unit-profile", phase="test", action="PERF")
    def _work(x: int) -> int:
        return x + 1

    assert _work(1) == 2
    assert "Perf metric" in calls


def test_measure_block_emits_metric(monkeypatch) -> None:
    calls: list[str] = []

    def _capture(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        calls.append(message)

    monkeypatch.setattr(perf_module.logger, "info", _capture)
    with measure_block("unit-block", phase="test", action="PERF"):
        _ = sum(i for i in range(10))
    assert "Perf metric" in calls


def test_metadata_cache_stats_are_deterministic() -> None:
    cache = MetadataCache()
    assert cache.stats().hit_rate == 0.0

    assert cache.get("h1") is None
    cache.set("h1", {"OWNER": "LL"})
    assert cache.get("h1") == {"OWNER": "LL"}
    assert cache.get("h1") == {"OWNER": "LL"}

    stats = cache.stats()
    assert stats.misses == 1
    assert stats.hits == 2
    assert stats.size == 1
    assert 0.0 < stats.hit_rate <= 1.0


def test_upsert_metadata_bulk_includes_batch_metrics(session_factory) -> None:
    with session_factory() as session:
        c1 = FileContent(sha256_hash="h1")
        c2 = FileContent(sha256_hash="h2")
        session.add_all([c1, c2])
        session.flush()
        c1_id = c1.content_id
        c2_id = c2.content_id
        session.commit()

    payload = {
        c1_id: [
            MetadataItem("OWNER", "LL"),
            MetadataItem("CONTEXT", "General"),
            MetadataItem("TAKEN_DT", "2024-01-01T00:00:00+00:00"),
        ],
        c2_id: [
            MetadataItem("OWNER", "LL"),
            MetadataItem("CONTEXT", "General"),
            MetadataItem("TAKEN_DT", "2024-01-02T00:00:00+00:00"),
        ],
    }
    with session_factory() as session:
        _, metrics = upsert_metadata_bulk(session, payload, batch_size=2, collect_batch_metrics=True)
        session.commit()

    assert metrics.code_upsert_batches >= 1
    assert metrics.metadata_upsert_batches >= 1
    assert all(size > 0 for size in metrics.rows_per_batch)
    assert sum(metrics.rows_per_batch) == metrics.rows_upserted
