"""Benchmark harness for Phase 12 discovery query layer.

Usage:
  python tools/perf/benchmark_phase12_discovery.py --items 10000 --output artifacts/perf/runs
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
import uuid

from sqlalchemy import inspect, text

from media_manager.app.persistence.base import create_db_engine, create_session_factory
from media_manager.app.persistence.discovery_query import DiscoveryQueryParams, DiscoveryQueryService
from media_manager.app.persistence.models import (
    CanonicalAssignment,
    CanonicalTag,
    FileContent,
    FileInstance,
    FileInstanceStatus,
    Tag,
    TagSource,
)


def _seed_synthetic(session, *, items: int, run_token: str) -> None:
    base = datetime(2026, 3, 2, 20, 0, tzinfo=UTC)
    tag_names = [f"phase12-bench-{run_token}-{i:02d}" for i in range(20)]
    tags = {}
    for idx, name in enumerate(tag_names):
        tag_id = uuid.uuid4()
        row = Tag(id=tag_id, name=name, normalized_name=name)
        session.add(row)
        tags[idx] = row

    content_rows = []
    instance_rows = []
    assignment_rows = []
    tag_rows = []

    for idx in range(items):
        content_id = uuid.uuid4()
        instance_id = uuid.uuid4()
        assignment_id = uuid.uuid4()
        first_seen = base + timedelta(seconds=idx)

        content_rows.append(
            FileContent(
                content_id=content_id,
                sha256_hash=f"{run_token}{idx:052x}",
                first_seen_at=first_seen,
            )
        )
        instance_rows.append(
            FileInstance(
                file_instance_id=instance_id,
                content_id=content_id,
                absolute_path=f"/perf/{run_token}/{idx}.jpg",
                filesystem_id="perf",
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

        # Deterministic 3-tag fanout per item.
        for offset in (0, 1, 2):
            t_idx = (idx + offset) % len(tags)
            confidence = round(0.55 + (offset * 0.15), 4)
            tag_rows.append(
                CanonicalTag(
                    canonical_id=content_id,
                    tag_id=tags[t_idx].id,
                    source=TagSource.AI.value,
                    confidence_score=confidence,
                    enrichment_version=1,
                )
            )

    session.add_all(content_rows)
    session.flush()
    session.add_all(instance_rows)
    session.add_all(assignment_rows)
    session.add_all(tag_rows)


def run_benchmark(items: int, output_dir: Path) -> Path:
    engine = create_db_engine()
    required_tables = {"tags", "canonical_tags", "file_contents", "file_instances", "canonical_assignments"}
    existing_tables = set(inspect(engine).get_table_names())
    missing = sorted(required_tables - existing_tables)
    if missing:
        raise RuntimeError(
            "Phase 12 benchmark requires migrated schema; missing tables: " + ", ".join(missing)
        )
    session_factory = create_session_factory(engine)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_token = uuid.uuid4().hex[:12]

    with session_factory.begin() as session:
        _seed_synthetic(session, items=items, run_token=run_token)

    svc = DiscoveryQueryService(session_factory)
    runs = []
    scenarios = [
        ("created_at_desc", DiscoveryQueryParams(page=1, limit=30, sort_by="created_at", sort_order="desc")),
        (
            "and_filter_tag_name",
            DiscoveryQueryParams(
                page=1,
                limit=30,
                tags=(f"phase12-bench-{run_token}-01", f"phase12-bench-{run_token}-02"),
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

    for name, params in scenarios:
        start = perf_counter()
        page = svc.query(params)
        duration_ms = round((perf_counter() - start) * 1000.0, 3)
        runs.append(
            {
                "scenario": name,
                "duration_ms": duration_ms,
                "total_count": page.total_count,
                "returned_items": len(page.items),
            }
        )

    with session_factory.begin() as session:
        session.execute(
            text("DELETE FROM file_contents WHERE sha256_hash LIKE :prefix"),
            {"prefix": f"{run_token}%"},
        )
        session.execute(
            text("DELETE FROM tags WHERE normalized_name LIKE :prefix"),
            {"prefix": f"phase12-bench-{run_token}-%"},
        )

    payload = {
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "items_seeded": items,
        "results": runs,
    }
    out_path = output_dir / f"phase12_discovery_benchmark_{items}.json"
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 12 discovery query benchmark.")
    parser.add_argument("--items", type=int, default=10000)
    parser.add_argument("--output", type=Path, default=Path("artifacts/perf/runs"))
    args = parser.parse_args()

    if args.items <= 0:
        raise ValueError("--items must be > 0")

    out = run_benchmark(args.items, args.output)
    print(f"Phase 12 discovery benchmark written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
