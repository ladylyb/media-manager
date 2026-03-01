# Phase 6 Performance Guide

This guide covers profiling and tuning for metadata pre-extraction and planner metadata lookup.

## Prerequisites

1. `DATABASE_URL` must point to PostgreSQL.
2. Schema migrations must be at head.
3. Optional: install `psutil` for CPU/RSS/IO metrics.

## Synthetic Dataset Generation

Generate deterministic synthetic metadata rows:

```powershell
python tools/perf/generate_synthetic_metadata.py --count 10000
```

Output defaults to `artifacts/perf/synthetic_metadata.tsv`.

## Run Benchmarks

Run 1k/10k/100k benchmark sweep:

```powershell
python tools/perf/benchmark_phase6.py --sizes 1000 10000 100000 --batch-size 1000
```

Tune batch size and repeat runs:

```powershell
python tools/perf/benchmark_phase6.py --sizes 10000 --batch-size 500 --repeat 3
```

The harness prints a summary table and writes JSON report files under `artifacts/perf/`.

## Interpreting Results

1. `throughput/s`: files processed per second in metadata UPSERT.
2. `lookup_cold_s`: DB lookup duration without cache priming.
3. `lookup_warm_s`: lookup duration with hash cache reuse.
4. `p50_ms` / `p95_ms`: median and tail metadata read latency.
5. `cache_hits` / `cache_misses`: validates cache efficacy.

## Batch Size Comparison Workflow

Run same size with different `--batch-size` values (100, 500, 1000, 5000) and compare:

1. total UPSERT duration,
2. throughput,
3. DB lookup latency.

Choose the smallest batch size that reaches stable throughput without excessive latency spikes.

## PostgreSQL Plan Checks

Use `tools/perf/sql/phase6_tuning.sql`:

1. confirm index scans for metadata lookups,
2. inspect UPSERT execution plans,
3. refresh stats via `ANALYZE`.

If `Seq Scan` appears on large metadata tables, revisit indexes and stale statistics first.

## Bottlenecks and Escalation

Expected bottlenecks:

1. disk IO during SHA-256 computation,
2. write amplification in metadata UPSERT batches,
3. repeated DB reads when cache hit-rate is low.

Escalate architecture only after measured limits:

1. use materialized views when repeated read-heavy joins dominate latency,
2. use async workers only when single-process throughput cannot meet target,
3. consider partitioning only when table cardinality and retention justify it.

