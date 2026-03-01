from __future__ import annotations

import json
from pathlib import Path

from tools.perf.benchmark_phase6 import ScenarioResult, write_report
from tools.perf.generate_synthetic_metadata import build_synthetic_rows


def test_synthetic_generator_count_is_deterministic() -> None:
    rows = build_synthetic_rows(100)
    assert len(rows) == 100
    assert len({file_hash for file_hash, _ in rows}) == 100
    assert rows[0][1]["OWNER"] == "LL"
    assert rows[0][1]["CONTEXT"] == "General"


def test_benchmark_report_schema(tmp_path: Path) -> None:
    sample = [
        ScenarioResult(
            size=1000,
            repeat=1,
            batch_size=500,
            upsert_duration_s=1.2,
            lookup_cold_duration_s=0.8,
            lookup_warm_duration_s=0.3,
            throughput_files_per_s=833.3,
            p50_lookup_ms=0.5,
            p95_lookup_ms=1.2,
            cache_hits=1000,
            cache_misses=1000,
        )
    ]
    report = write_report(sample, tmp_path / "artifacts")
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert payload[0]["size"] == 1000
    assert payload[0]["throughput_files_per_s"] >= 0
    assert payload[0]["p95_lookup_ms"] >= 0
    assert payload[0]["cache_hits"] >= 0
    assert payload[0]["cache_misses"] >= 0

