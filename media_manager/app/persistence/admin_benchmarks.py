"""Safe database-only benchmark execution helpers for admin workflows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from statistics import median
from time import perf_counter
import uuid

from sqlalchemy import delete, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.core.metadata_cache import MetadataCache
from media_manager.app.core.metadata_extractor import MetadataItem, upsert_metadata_bulk
from media_manager.app.persistence.discovery_query import DiscoveryQueryParams, DiscoveryQueryService
from media_manager.app.persistence.models import (
    CanonicalAssignment,
    CanonicalTag,
    FileContent,
    FileInstance,
    FileInstanceStatus,
    MediaMetadata,
    MetadataCode,
    Tag,
    TagSource,
)


@dataclass(frozen=True)
class BenchmarkExecutionResult:
    summary: dict[str, object]
    report: dict[str, object]
    cleanup_status: str
    cleanup_error: str | None


@dataclass(frozen=True)
class _MetadataScenarioResult:
    size: int
    batch_size: int
    upsert_duration_s: float
    lookup_cold_duration_s: float
    lookup_warm_duration_s: float
    throughput_files_per_s: float
    p50_lookup_ms: float
    p95_lookup_ms: float
    cache_hits: int
    cache_misses: int


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * q))
    return ordered[idx]


def _build_metadata_rows(*, count: int, run_token: str) -> list[tuple[str, dict[str, str]]]:
    rows: list[tuple[str, dict[str, str]]] = []
    for idx in range(count):
        digest = f"bench-{run_token}-{idx:09d}"
        rows.append(
            (
                digest,
                {
                    "OWNER": "BENCH",
                    "CONTEXT": "Synthetic",
                    "TAKEN_DT": f"2024-01-{(idx % 28) + 1:02d}T12:00:00+00:00",
                    "FS_CTIME": "2024-01-01T00:00:00+00:00",
                    "FS_MTIME": "2024-01-01T00:00:00+00:00",
                    "CAMERA_MODEL": f"BENCH-CAM-{idx % 5}",
                },
            )
        )
    return rows


def _ensure_contents(session: Session, rows: list[tuple[str, dict[str, str]]]) -> dict[str, uuid.UUID]:
    mapping: dict[str, uuid.UUID] = {}
    for file_hash, _ in rows:
        content = session.scalar(select(FileContent).where(FileContent.sha256_hash == file_hash))
        if content is None:
            content = FileContent(sha256_hash=file_hash)
            session.add(content)
            session.flush()
        mapping[file_hash] = content.content_id
    return mapping


def _lookup_metadata_rows(session: Session, content_id: uuid.UUID) -> dict[str, str]:
    rows = session.execute(
        select(MetadataCode.code_type, MediaMetadata.decode_value)
        .select_from(MediaMetadata)
        .join(MetadataCode, MediaMetadata.code_id == MetadataCode.id)
        .where(MediaMetadata.content_id == content_id)
    ).all()
    return {str(code_type): str(decode_value) for code_type, decode_value in rows}


def _cleanup_metadata_rows(session: Session, *, content_ids: list[uuid.UUID]) -> None:
    if not content_ids:
        return
    session.execute(delete(MediaMetadata).where(MediaMetadata.content_id.in_(content_ids)))
    session.execute(delete(FileContent).where(FileContent.content_id.in_(content_ids)))


def run_metadata_benchmark(
    session_factory: sessionmaker[Session],
    *,
    items: int,
    batch_size: int,
    operation_run_id: str,
) -> BenchmarkExecutionResult:
    run_token = uuid.uuid4().hex[:12]
    cleanup_error: str | None = None
    cleanup_status = "COMPLETED"
    content_ids: list[uuid.UUID] = []
    scenario: _MetadataScenarioResult | None = None
    try:
        with session_factory.begin() as session:
            source_rows = _build_metadata_rows(count=items, run_token=run_token)
            content_map = _ensure_contents(session, source_rows)
            payload: dict[uuid.UUID, list[MetadataItem]] = {}
            for file_hash, metadata in source_rows:
                content_id = content_map[file_hash]
                content_ids.append(content_id)
                payload[content_id] = [
                    MetadataItem(code_type=code_type, decode_value=value) for code_type, value in metadata.items()
                ]
            start = perf_counter()
            upsert_metadata_bulk(session, payload, batch_size=batch_size, collect_batch_metrics=True)
            upsert_duration = perf_counter() - start

            cache = MetadataCache()
            lookup_latencies_ms: list[float] = []

            cold_start = perf_counter()
            for content_id in content_ids:
                t0 = perf_counter()
                _lookup_metadata_rows(session, content_id)
                lookup_latencies_ms.append((perf_counter() - t0) * 1000.0)
            cold_duration = perf_counter() - cold_start

            warm_start = perf_counter()
            for content_id in content_ids:
                key = str(content_id)
                cached = cache.get(key)
                if cached is None:
                    cache.set(key, _lookup_metadata_rows(session, content_id))
            for content_id in content_ids:
                _ = cache.get(str(content_id))
            warm_duration = perf_counter() - warm_start
            stats = cache.stats()
            scenario = _MetadataScenarioResult(
                size=items,
                batch_size=batch_size,
                upsert_duration_s=upsert_duration,
                lookup_cold_duration_s=cold_duration,
                lookup_warm_duration_s=warm_duration,
                throughput_files_per_s=(items / upsert_duration) if upsert_duration > 0 else 0.0,
                p50_lookup_ms=median(lookup_latencies_ms) if lookup_latencies_ms else 0.0,
                p95_lookup_ms=_percentile(lookup_latencies_ms, 0.95),
                cache_hits=stats.hits,
                cache_misses=stats.misses,
            )
            _cleanup_metadata_rows(session, content_ids=content_ids)
    except Exception as exc:
        cleanup_status = "FAILED"
        cleanup_error = str(exc)
        raise

    if scenario is None:
        raise RuntimeError("metadata benchmark did not produce a scenario result")

    report = {
        "benchmark_type": "METADATA",
        "operation_run_id": operation_run_id,
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "results": [asdict(scenario)],
    }
    summary = {
        "items": items,
        "batch_size": batch_size,
        "throughput_files_per_s": round(scenario.throughput_files_per_s, 3),
        "upsert_duration_s": round(scenario.upsert_duration_s, 6),
        "lookup_cold_duration_s": round(scenario.lookup_cold_duration_s, 6),
        "lookup_warm_duration_s": round(scenario.lookup_warm_duration_s, 6),
        "cache_hit_rate": round(
            (scenario.cache_hits / max(1, scenario.cache_hits + scenario.cache_misses)) * 100.0,
            3,
        ),
    }
    return BenchmarkExecutionResult(
        summary=summary,
        report=report,
        cleanup_status=cleanup_status,
        cleanup_error=cleanup_error,
    )


def _seed_discovery_rows(session: Session, *, items: int, run_token: str) -> None:
    base = datetime(2026, 3, 2, 20, 0, tzinfo=UTC)
    tag_names = [f"bench-tag-{run_token}-{i:02d}" for i in range(20)]
    tags: dict[int, Tag] = {}
    for idx, name in enumerate(tag_names):
        row = Tag(id=uuid.uuid4(), name=name, normalized_name=name)
        session.add(row)
        tags[idx] = row

    content_rows: list[FileContent] = []
    instance_rows: list[FileInstance] = []
    assignment_rows: list[CanonicalAssignment] = []
    tag_rows: list[CanonicalTag] = []
    for idx in range(items):
        content_id = uuid.uuid4()
        instance_id = uuid.uuid4()
        assignment_id = uuid.uuid4()
        first_seen = base + timedelta(seconds=idx)
        content_rows.append(
            FileContent(
                content_id=content_id,
                sha256_hash=f"bench-discovery-{run_token}-{idx:08d}",
                first_seen_at=first_seen,
            )
        )
        instance_rows.append(
            FileInstance(
                file_instance_id=instance_id,
                content_id=content_id,
                absolute_path=f"/bench/{run_token}/{idx}.jpg",
                filesystem_id="bench",
                first_seen_at=first_seen,
                last_seen_at=first_seen,
                status=FileInstanceStatus.ACTIVE.value,
            )
        )
        assignment_rows.append(
            CanonicalAssignment(
                assignment_id=assignment_id,
                content_id=content_id,
                canonical_instance_id=instance_id,
                policy_name="FIRST_SEEN",
                policy_version="v1",
                assigned_at=first_seen,
            )
        )
        for offset in (0, 1, 2):
            tag_idx = (idx + offset) % len(tags)
            tag_rows.append(
                CanonicalTag(
                    canonical_id=content_id,
                    tag_id=tags[tag_idx].id,
                    source=TagSource.AI.value,
                    confidence_score=round(0.55 + (offset * 0.15), 4),
                    enrichment_version=1,
                )
            )
    session.add_all(content_rows)
    session.flush()
    session.add_all(instance_rows)
    session.add_all(assignment_rows)
    session.add_all(tag_rows)


def _cleanup_discovery_rows(session: Session, *, run_token: str) -> None:
    session.execute(
        text("DELETE FROM file_contents WHERE sha256_hash LIKE :prefix"),
        {"prefix": f"bench-discovery-{run_token}-%"},
    )
    session.execute(
        text("DELETE FROM tags WHERE normalized_name LIKE :prefix"),
        {"prefix": f"bench-tag-{run_token}-%"},
    )


def run_discovery_benchmark(
    session_factory: sessionmaker[Session],
    *,
    items: int,
    operation_run_id: str,
) -> BenchmarkExecutionResult:
    required_tables = {"tags", "canonical_tags", "file_contents", "file_instances", "canonical_assignments"}
    with session_factory() as session:
        existing_tables = set(inspect(session.get_bind()).get_table_names())
    missing = sorted(required_tables - existing_tables)
    if missing:
        raise RuntimeError("Discovery benchmark requires migrated schema; missing tables: " + ", ".join(missing))

    run_token = uuid.uuid4().hex[:12]
    cleanup_status = "COMPLETED"
    cleanup_error: str | None = None
    scenarios: list[dict[str, object]] = []
    seeded = False
    try:
        with session_factory.begin() as session:
            _seed_discovery_rows(session, items=items, run_token=run_token)
        seeded = True

        svc = DiscoveryQueryService(session_factory)
        benchmark_scenarios = [
            ("created_at_desc", DiscoveryQueryParams(page=1, limit=30, sort_by="created_at", sort_order="desc")),
            (
                "and_filter_tag_name",
                DiscoveryQueryParams(
                    page=1,
                    limit=30,
                    tags=(f"bench-tag-{run_token}-01", f"bench-tag-{run_token}-02"),
                    sort_by="tag_name",
                    sort_order="asc",
                ),
            ),
            (
                "confidence_filtered",
                DiscoveryQueryParams(
                    page=1,
                    limit=30,
                    sort_by="confidence_score",
                    sort_order="desc",
                    min_confidence=0.7,
                ),
            ),
        ]
        for name, params in benchmark_scenarios:
            start = perf_counter()
            page = svc.query(params)
            duration_ms = round((perf_counter() - start) * 1000.0, 3)
            scenarios.append(
                {
                    "scenario": name,
                    "duration_ms": duration_ms,
                    "total_count": page.total_count,
                    "returned_items": len(page.items),
                }
            )
    except Exception as exc:
        cleanup_status = "FAILED"
        cleanup_error = str(exc)
        raise
    finally:
        if seeded:
            try:
                with session_factory.begin() as session:
                    _cleanup_discovery_rows(session, run_token=run_token)
            except Exception as cleanup_exc:
                cleanup_status = "FAILED"
                cleanup_error = str(cleanup_exc)
                raise RuntimeError(f"Discovery benchmark cleanup failed: {cleanup_exc}") from cleanup_exc

    report = {
        "benchmark_type": "DISCOVERY",
        "operation_run_id": operation_run_id,
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "items_seeded": items,
        "results": scenarios,
    }
    summary = {
        "items_seeded": items,
        "scenario_count": len(scenarios),
        "slowest_duration_ms": max((float(item["duration_ms"]) for item in scenarios), default=0.0),
        "fastest_duration_ms": min((float(item["duration_ms"]) for item in scenarios), default=0.0),
    }
    return BenchmarkExecutionResult(
        summary=summary,
        report=report,
        cleanup_status=cleanup_status,
        cleanup_error=cleanup_error,
    )
