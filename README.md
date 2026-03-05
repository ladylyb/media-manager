# media-manager

## License

[![License: CC BY-NC-ND 4.0](https://licensebuttons.net/l/by-nc-nd/4.0/88x31.png)](https://creativecommons.org/licenses/by-nc-nd/4.0/)

This project is licensed under the **Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0)**.

- You may view and share this project for non-commercial purposes.
- Commercial use is prohibited without explicit permission from the author.
- Modifications and derivative works are not permitted without explicit permission from the author.

## Contributing

Contribution workflow and PR standards are documented in [CONTRIBUTING.md](CONTRIBUTING.md).
Always review runtime invariants in [AGENTS.md](AGENTS.md) before making changes.

## Environment Configuration

Use `.env.sample` as the runtime configuration template.

```bash
cp .env.sample .env
```

Set at least `DATABASE_URL` (and `TEST_DATABASE_URL` for tests/tooling).  
Full variable reference: `documentation/reference/environment-variables.md`.

## Observability & Metrics (Phase 11)

### Overview

Phase 11 adds Prometheus metrics for planner timing, canonical read cache behavior, and ingestion activity/latency.
Metrics are exposed at `/metrics` (Operator Console app) and can also be served by the optional standalone metrics server when enabled.

### Planner Metrics

- `planner_actions_generated_total`: total planner actions emitted.
- `apply_actions_executed_total`: total apply actions executed.
- `planner_stage_duration_seconds` (`_bucket`, `_sum`, `_count`): planner stage duration histogram by stage (`load_candidates`, `metadata_lookup`, `action_generation`, `persist_actions`).

### Cache Metrics

- `canonical_read_cache_hits_total`: total canonical read cache hits.
- `canonical_read_cache_misses_total`: total canonical read cache misses.
- `canonical_read_cache_hit_ratio_percent`: cache hit ratio gauge (0-100).

### Ingestion Metrics

Legacy counters (kept for compatibility):
- `ingest_files_scanned_total`: total files scanned by ingest.
- `ingest_new_contents_total`: total new content identities created.

Structured ingestion metrics:
- `files_scanned_total`: files scanned (labeled by `run_id`, `dataset_id`, `policy_name`).
- `new_contents_total`: new content identities discovered.
- `new_instances_total`: new file instances discovered.
- `duplicates_detected_total`: duplicate content detections.
- `hash_time_total_ms` (`_bucket`, `_sum`, `_count`): per-file hash latency histogram (ms).
- `db_write_time_total_ms` (`_bucket`, `_sum`, `_count`): per-file DB persistence-path latency histogram (ms).

### Accessing Metrics

```bash
curl http://localhost:8000/metrics
```

### Example PromQL Queries

- Planner stage p95 duration (5m window):
```promql
histogram_quantile(0.95, sum by (le, stage) (rate(planner_stage_duration_seconds_bucket[5m])))
```

- Canonical cache hit ratio from counters (5m window):
```promql
100 * sum(rate(canonical_read_cache_hits_total[5m])) / (sum(rate(canonical_read_cache_hits_total[5m])) + sum(rate(canonical_read_cache_misses_total[5m])))
```

- Ingest files scanned rate (5m window):
```promql
sum(rate(files_scanned_total[5m]))
```
