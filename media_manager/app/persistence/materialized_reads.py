"""Read-side optimization helpers for Phase 10.1.

Optimization-only path:
- No canonical selection logic changes.
- No planner/apply write semantics changes.
- Default behavior remains base-table reads.
- MV is eventually consistent and must not be used for correctness-sensitive
  planner/apply logic.
"""

from __future__ import annotations

import inspect
import os
import random
import uuid
from dataclasses import dataclass
from time import perf_counter
from typing import Any
from statistics import pstdev

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.core.ttl_cache import TTLCache


@dataclass(frozen=True)
class CanonicalMetadataRow:
    content_id: uuid.UUID
    canonical_instance_id: uuid.UUID
    hash_identity: str
    file_path: str
    file_size: int | None
    created_at: str


@dataclass(frozen=True)
class RefreshMVSummary:
    concurrently: bool
    scheduled: bool
    schedule_label: str | None


@dataclass(frozen=True)
class PlannerBenchmarkSummary:
    base_mean_ms: float
    mv_mean_ms: float
    stddev_ms: float
    improvement_pct: float
    sample_size: int
    repeats: int
    sampled_content_ids: tuple[uuid.UUID, ...]
    query_order_pattern: tuple[str, ...]


_BASE_QUERY = """
WITH latest AS (
    SELECT
        ca.content_id,
        ca.canonical_instance_id,
        ca.assigned_at,
        ca.assignment_id,
        ROW_NUMBER() OVER (
            PARTITION BY ca.content_id
            ORDER BY ca.assigned_at DESC, ca.assignment_id DESC
        ) AS rn
    FROM canonical_assignments ca
)
SELECT
    l.content_id,
    l.canonical_instance_id,
    fc.sha256_hash AS hash_identity,
    fi.absolute_path AS file_path,
    legacy.size_bytes AS file_size,
    l.assigned_at AS created_at
FROM latest l
JOIN file_contents fc
  ON fc.content_id = l.content_id
JOIN file_instances fi
  ON fi.file_instance_id = l.canonical_instance_id
LEFT JOIN files legacy
  ON legacy.path = fi.absolute_path
WHERE l.rn = 1
"""

_MV_QUERY = """
SELECT
    content_id,
    canonical_instance_id,
    hash_identity,
    file_path,
    file_size,
    created_at
FROM mv_canonical_metadata
"""


def _env_cache_enabled() -> bool:
    return os.getenv("CANONICAL_READ_CACHE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _env_cache_ttl() -> float:
    raw = os.getenv("CANONICAL_READ_CACHE_TTL_SECONDS", "30")
    try:
        value = float(raw)
    except ValueError:
        return 30.0
    if value <= 0:
        return 30.0
    return value


# optimization-only path: disabled by default, read results only.
_READ_CACHE = TTLCache[str, list[CanonicalMetadataRow]](ttl_seconds=_env_cache_ttl())


def _rows_to_dataclass(rows: list[dict[str, Any]]) -> list[CanonicalMetadataRow]:
    return [
        CanonicalMetadataRow(
            content_id=row["content_id"],
            canonical_instance_id=row["canonical_instance_id"],
            hash_identity=str(row["hash_identity"]),
            file_path=str(row["file_path"]),
            file_size=row["file_size"],
            created_at=str(row["created_at"]),
        )
        for row in rows
    ]


def _planner_mv_opt_in_enabled() -> bool:
    return (
        os.getenv("MEDIA_MANAGER_ALLOW_PLANNER_MV_READS", "false").strip().lower() in {"1", "true", "yes", "on"}
    )


def _assert_mv_guard_for_planner_callers() -> None:
    # Safety guard: planner/apply correctness paths must not rely on eventually
    # consistent MV reads unless explicitly opted in for experiments.
    if _planner_mv_opt_in_enabled():
        return
    for frame_info in inspect.stack(context=0):
        filename = frame_info.filename.replace("\\", "/")
        if filename.endswith("/media_manager/app/persistence/planner.py") or filename.endswith(
            "media_manager/app/persistence/planner.py"
        ):
            raise RuntimeError(
                "MV reads from planner path are blocked by default. "
                "Use base-table reads or explicitly set MEDIA_MANAGER_ALLOW_PLANNER_MV_READS=true."
            )


def _query_rows(
    session: Session,
    *,
    use_mv: bool,
    sample_size: int,
) -> list[CanonicalMetadataRow]:
    if use_mv:
        _assert_mv_guard_for_planner_callers()

    base_sql = _MV_QUERY if use_mv else _BASE_QUERY
    sql = (
        f"{base_sql} ORDER BY content_id ASC, canonical_instance_id ASC LIMIT :limit"
        if sample_size > 0
        else f"{base_sql} ORDER BY content_id ASC, canonical_instance_id ASC"
    )
    params: dict[str, Any] = {"limit": sample_size} if sample_size > 0 else {}
    rows = session.execute(text(sql), params).mappings().all()
    return _rows_to_dataclass([dict(row) for row in rows])


def fetch_canonical_metadata(
    session: Session,
    *,
    use_mv: bool,
    sample_size: int,
    use_cache: bool | None = None,
) -> list[CanonicalMetadataRow]:
    cache_enabled = _env_cache_enabled() if use_cache is None else bool(use_cache)
    cache_key = f"source={'mv' if use_mv else 'base'}|sample_size={sample_size}"

    # optimization-only path: read cache never affects decision semantics.
    if cache_enabled:
        cached = _READ_CACHE.get(cache_key)
        if cached is not None:
            return cached

    rows = _query_rows(session, use_mv=use_mv, sample_size=sample_size)
    if cache_enabled:
        _READ_CACHE.set(cache_key, rows)
    return rows


def refresh_materialized_view(
    engine: Engine,
    *,
    concurrently: bool = True,
    scheduled: bool = False,
    schedule_label: str | None = None,
) -> RefreshMVSummary:
    statement = (
        "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_canonical_metadata"
        if concurrently
        else "REFRESH MATERIALIZED VIEW mv_canonical_metadata"
    )

    # REFRESH ... CONCURRENTLY requires autocommit and unique index on the MV.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(statement))

    return RefreshMVSummary(
        concurrently=concurrently,
        scheduled=scheduled,
        schedule_label=schedule_label,
    )


def benchmark_planner_lookup(
    session_factory: sessionmaker[Session],
    *,
    sample_size: int,
    repeats: int,
    use_cache: bool,
    seed: int = 42,
) -> PlannerBenchmarkSummary:
    bounded_sample = max(1, int(sample_size))
    bounded_repeats = max(1, int(repeats))

    _READ_CACHE.clear()
    with session_factory() as session:
        full_base_rows = fetch_canonical_metadata(
            session,
            use_mv=False,
            sample_size=0,
            use_cache=False,
        )

    all_content_ids = [row.content_id for row in full_base_rows]
    if not all_content_ids:
        return PlannerBenchmarkSummary(
            base_mean_ms=0.0,
            mv_mean_ms=0.0,
            stddev_ms=0.0,
            improvement_pct=0.0,
            sample_size=0,
            repeats=bounded_repeats,
            sampled_content_ids=tuple(),
            query_order_pattern=tuple(),
        )

    effective_sample = min(bounded_sample, len(all_content_ids))
    randomizer = random.Random(seed)
    sampled_content_ids = tuple(sorted(randomizer.sample(all_content_ids, k=effective_sample), key=str))
    sampled_set = set(sampled_content_ids)

    base_samples = [row for row in full_base_rows if row.content_id in sampled_set]
    base_timings_ms: list[float] = []
    mv_timings_ms: list[float] = []
    delta_timings_ms: list[float] = []
    query_order_pattern: list[str] = []

    for _ in range(bounded_repeats):
        order = ["base", "mv"]
        randomizer.shuffle(order)
        query_order_pattern.append(",".join(order))

        measured: dict[str, tuple[float, list[CanonicalMetadataRow]]] = {}
        with session_factory() as session:
            for source in order:
                use_mv_path = source == "mv"
                t0 = perf_counter()
                rows = fetch_canonical_metadata(
                    session,
                    use_mv=use_mv_path,
                    sample_size=0,
                    use_cache=use_cache if use_mv_path else False,
                )
                duration_ms = (perf_counter() - t0) * 1000.0
                filtered_rows = [row for row in rows if row.content_id in sampled_set]
                measured[source] = (duration_ms, filtered_rows)

        base_ms, base_rows = measured["base"]
        mv_ms, mv_rows = measured["mv"]
        if base_rows != mv_rows or base_rows != base_samples:
            raise RuntimeError("MV lookup diverged from base-table lookup")

        base_timings_ms.append(base_ms)
        mv_timings_ms.append(mv_ms)
        delta_timings_ms.append(base_ms - mv_ms)

    base_lookup_ms = sum(base_timings_ms) / bounded_repeats
    mv_lookup_ms = sum(mv_timings_ms) / bounded_repeats
    stddev_ms = pstdev(delta_timings_ms) if len(delta_timings_ms) > 1 else 0.0
    improvement_pct = 0.0
    if base_lookup_ms > 0:
        improvement_pct = ((base_lookup_ms - mv_lookup_ms) / base_lookup_ms) * 100.0

    return PlannerBenchmarkSummary(
        base_mean_ms=base_lookup_ms,
        mv_mean_ms=mv_lookup_ms,
        stddev_ms=stddev_ms,
        improvement_pct=improvement_pct,
        sample_size=effective_sample,
        repeats=bounded_repeats,
        sampled_content_ids=sampled_content_ids,
        query_order_pattern=tuple(query_order_pattern),
    )
