# Observability

This guide covers three operator-facing observability layers:

- Prometheus scrape output at `/metrics`
- the Admin Observability UI in the operator console
- durable DB-backed run and failure facts exposed through `/api/admin/observability/*`

## Core Correlation Keys

- `run_id`
- `phase`
- `action_type`
- `sequence_no`
- `content_id` (when present)

Treat `run_id` as the primary handle for investigations.

## Log Signals

The structured logger emits fields including:

- lifecycle and phase: `run_id`, `phase`, `action_type`
- counts: `scanned`, `supported`, `skipped`, `moves`, `duplicates`, `noop`, `applied`, `errors`
- performance: `duration_s`, `files_count`, `batch_size`, `cache_hits`, `cache_misses`
- canonicalization: `policy_name`, `policy_version`, `recompute_mode`, `sequence_no`

## Operational Baseline

For each run, capture:

1. API request issued
2. `run_id`
3. response summary counters
4. any error payload
5. whether rerun was attempted

## Minimum Incident Record

- timestamp (UTC)
- run identifier
- phase of failure
- error message
- recovery action taken
- final outcome

## Metrics Scrape Surface

`/metrics` is the Prometheus scrape endpoint. It is intentionally machine-oriented
plain text, not a human dashboard. Use Prometheus and Grafana for long-lived
storage, charting, and alerting.

Provisioning examples live under:

- `deploy/observability/prometheus.yml`
- `deploy/observability/alert_rules.yml`
- `deploy/observability/grafana/`

Recommended setup:

1. Enable metrics with `MEDIA_MANAGER_METRICS_ENABLED=true`
2. Point Prometheus at `http://<host>:<port>/metrics`
3. Set optional UI links:
   - `MEDIA_MANAGER_PROMETHEUS_URL`
   - `MEDIA_MANAGER_GRAFANA_URL`
4. Open the Admin Observability page for operator-friendly summaries and recent failures

## Admin Observability API

The operator console uses curated read-only API endpoints instead of parsing
Prometheus output in the browser:

- `GET /api/admin/observability/summary`
- `GET /api/admin/observability/operation-runs`
- `GET /api/admin/observability/failures`
- `GET /api/admin/observability/metrics-series`

These endpoints provide:

- recent run counts and last-success snapshots
- recent durable failure facts
- chart-ready hourly series for operation volume, failures, and latency
- optional deep links to Prometheus and Grafana

## Quick Check

```bash
curl http://127.0.0.1:8000/metrics | rg canonical_read_cache
```

Expected pass signal:

1. The metrics output includes both cache hit and miss families.
2. Output includes all metric families for both `source="base"` and `source="mv"`:
   - `canonical_read_cache_hits_total`
   - `canonical_read_cache_misses_total`
   - `canonical_read_cache_hit_ratio_percent`

## Admin Benchmarking

Benchmarks are exposed only through the admin API and GUI. They are not
supported as direct scripts or CLI workflows.

API surface:

- `POST /api/admin/benchmarks/metadata`
- `POST /api/admin/benchmarks/discovery`
- `GET /api/admin/benchmarks/runs`
- `GET /api/admin/benchmarks/runs/{operation_run_id}`
- `POST /api/admin/benchmarks/runs/{operation_run_id}/cancel`

Safety rules:

- allowed only when `MEDIA_MANAGER_ENV` is `dev` or `test`
- require `MEDIA_MANAGER_BENCHMARKS_ENABLED=true`
- queue a durable benchmark record and `operation_runs` record before execution
- execute in the separate `media-manager-benchmark-worker` process
- never perform filesystem mutation
- operate only on synthetic benchmark-tagged DB rows and record cleanup outcome durably
