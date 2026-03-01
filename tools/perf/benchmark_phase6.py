"""Benchmark harness for Phase 6 metadata extraction and planner lookups.

Usage examples:
  python tools/perf/benchmark_phase6.py --sizes 1000 10000 100000 --batch-size 1000
  python tools/perf/benchmark_phase6.py --sizes 10000 --batch-size 500 --repeat 3
"""

from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Iterable

from sqlalchemy import select

from media_manager.app.core.metadata_cache import MetadataCache
from media_manager.app.core.metadata_extractor import MetadataItem, upsert_metadata_bulk
from media_manager.app.persistence.base import create_db_engine, create_session_factory, transactional_session
from media_manager.app.persistence.models import FileContent, MediaMetadata, MetadataCode
try:
    from tools.perf.generate_synthetic_metadata import build_synthetic_rows
except ModuleNotFoundError:  # script execution fallback
    from generate_synthetic_metadata import build_synthetic_rows


@dataclass(frozen=True)
class ScenarioResult:
    size: int
    repeat: int
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


def _ensure_contents(session, rows: Iterable[tuple[str, dict[str, str]]]) -> dict[str, uuid.UUID]:
    mapping: dict[str, uuid.UUID] = {}
    for file_hash, metadata in rows:
        content = session.scalar(select(FileContent).where(FileContent.sha256_hash == file_hash))
        if content is None:
            content = FileContent(sha256_hash=file_hash)
            session.add(content)
            session.flush()
        mapping[file_hash] = content.content_id
    return mapping


def _upsert_for_size(session, size: int, batch_size: int) -> tuple[list[uuid.UUID], float]:
    source_rows = build_synthetic_rows(size)
    content_map = _ensure_contents(session, source_rows)

    payload: dict[uuid.UUID, list[MetadataItem]] = {}
    content_ids: list[uuid.UUID] = []
    for file_hash, metadata in source_rows:
        content_id = content_map[file_hash]
        content_ids.append(content_id)
        payload[content_id] = [MetadataItem(code_type=code, decode_value=value) for code, value in metadata.items()]

    start = perf_counter()
    upsert_metadata_bulk(session, payload, batch_size=batch_size, collect_batch_metrics=True)
    duration = perf_counter() - start
    return content_ids, duration


def _lookup_metadata_rows(session, content_id) -> dict[str, str]:
    rows = session.execute(
        select(MetadataCode.code_type, MediaMetadata.decode_value)
        .join(MediaMetadata, MediaMetadata.code_id == MetadataCode.id)
        .where(MediaMetadata.content_id == content_id)
    ).all()
    return {code_type: decode_value for code_type, decode_value in rows}


def _benchmark_lookup(session, content_ids: list) -> tuple[float, float, list[float], MetadataCache]:
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
    return cold_duration, warm_duration, lookup_latencies_ms, cache


def run_benchmarks(sizes: list[int], batch_size: int, repeat: int) -> list[ScenarioResult]:
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    results: list[ScenarioResult] = []

    try:
        for size in sizes:
            for run_idx in range(1, repeat + 1):
                with transactional_session(session_factory) as session:
                    content_ids, upsert_duration = _upsert_for_size(session, size, batch_size)
                    cold_duration, warm_duration, latencies_ms, cache = _benchmark_lookup(session, content_ids)

                    throughput = size / upsert_duration if upsert_duration > 0 else 0.0
                    scenario = ScenarioResult(
                        size=size,
                        repeat=run_idx,
                        batch_size=batch_size,
                        upsert_duration_s=upsert_duration,
                        lookup_cold_duration_s=cold_duration,
                        lookup_warm_duration_s=warm_duration,
                        throughput_files_per_s=throughput,
                        p50_lookup_ms=median(latencies_ms) if latencies_ms else 0.0,
                        p95_lookup_ms=_percentile(latencies_ms, 0.95),
                        cache_hits=cache.stats().hits,
                        cache_misses=cache.stats().misses,
                    )
                    results.append(scenario)
    finally:
        engine.dispose()

    return results


def write_report(results: list[ScenarioResult], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"phase6_{stamp}.json"
    payload = [asdict(result) for result in results]
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def print_table(results: list[ScenarioResult]) -> None:
    header = (
        "size repeat batch upsert_s lookup_cold_s lookup_warm_s "
        "throughput/s p50_ms p95_ms cache_hits cache_misses"
    )
    print(header)
    for row in results:
        print(
            f"{row.size} {row.repeat} {row.batch_size} "
            f"{row.upsert_duration_s:.3f} {row.lookup_cold_duration_s:.3f} {row.lookup_warm_duration_s:.3f} "
            f"{row.throughput_files_per_s:.1f} {row.p50_lookup_ms:.3f} {row.p95_lookup_ms:.3f} "
            f"{row.cache_hits} {row.cache_misses}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 6 metadata performance benchmarks.")
    parser.add_argument("--sizes", nargs="+", type=int, default=[1000, 10000, 100000])
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--report-dir", type=Path, default=Path("artifacts/perf"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = run_benchmarks(args.sizes, args.batch_size, args.repeat)
    print_table(results)
    report_path = write_report(results, args.report_dir)
    print(f"Report written to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
