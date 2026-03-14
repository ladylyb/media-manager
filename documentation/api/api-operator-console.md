# Operator Console API

HTTP API reference for the supported application interface.

The operator console GUI and first-party automation in this repository are expected to consume these endpoints over HTTP. They are clients of the API, not alternate logic layers.

## Canonical Service-Layer Endpoints

The `/api/*` family is the supported application surface and is sourced from an in-process shared service layer.
`/api/v1/*` has been removed.

Standard envelope:

```json
{
  "ok": true,
  "workflow_version": "v2-service-layer",
  "schema_version": "string",
  "generated_at": "iso8601",
  "data": {},
  "errors": []
}
```

Available canonical endpoints:
- `GET /api/status`
- `GET /api/dashboard-summary`
- `GET /api/latest-metrics`
- `GET /api/runs?limit=50&operation_type=INGEST&status=COMPLETED`
- `GET /api/operation-runs?limit=50&operation_type=PLAN&status=FAILED`
- `GET /api/internal-runs?limit=50`
- `GET /api/operations/catalog`
- `GET /api/policy`
- `POST /api/policy`
- `POST /api/ingest`
- `POST /api/plan`
- `POST /api/apply`
- `POST /api/canonical/recompute`
- `POST /api/run`
- `POST /api/tag-enrichment`
- `POST /api/media-file/validate`
- `GET /api/admin/hash-audit`
- `GET /api/admin/observability/summary`
- `GET /api/admin/observability/operation-runs`
- `GET /api/admin/observability/failures`
- `GET /api/admin/observability/metrics-series`
- `POST /api/admin/benchmarks/metadata`
- `POST /api/admin/benchmarks/discovery`
- `GET /api/admin/benchmarks/runs`
- `GET /api/admin/benchmarks/runs/{operation_run_id}`
- `POST /api/admin/benchmarks/runs/{operation_run_id}/cancel`
- `POST /api/admin/db-reset`

Error mapping:
- `400` validation/domain/state errors (`ok=false`, populated `errors[]`)
- `500` runtime failures
- `503` mutation concurrency saturation

### `POST /api/admin/db-reset`

Safe dev/test data reset endpoint (destructive). Truncates app data tables only, preserving schema and Alembic migration state.

Request:

```json
{
  "dry_run": true,
  "challenge_word": "media-manager"
}
```

Rules:
- `dry_run=true`: preview only, no data deletion.
- `dry_run=false`: `challenge_word` must match exactly.
- hard blocked unless `MEDIA_MANAGER_ENV` is `dev` or `test`.
- optional server-side challenge override: `MEDIA_MANAGER_DB_RESET_CHALLENGE_WORD`.
- optional destructive scope expansion: `MEDIA_MANAGER_DB_RESET_INCLUDE_DYNAMIC=true`.

Result payload in envelope `data.result`:

```json
{
  "success": true,
  "dry_run": true,
  "affected_tables": ["media_file", "file_instances"],
  "message": "Dry-run only. No data deleted."
}
```

### `GET /api/admin/observability/summary`

Read-only operator snapshot with:

- metrics enabled flag
- optional Prometheus and Grafana links
- recent run counts by status and type
- last successful operation timestamps
- recent failure count
- selected latest metrics

### `GET /api/admin/observability/operation-runs`

Read-only operation history feed for the Admin Observability UI. Supports the
same `limit`, `operation_type`, and `status` filters as `GET /api/operation-runs`.

### `GET /api/admin/observability/failures`

Read-only recent failure view combining durable `failure_events` and failed
`operation_runs`. Query params:

- `limit` (default `20`, max `200`)

### `GET /api/admin/observability/metrics-series`

Read-only chart-ready metrics series for the Admin Observability UI.

Query params:

- `hours` (default `24`, max `168`)

This endpoint intentionally exposes a fixed allowlist of curated series rather
than arbitrary Prometheus queries.

### Benchmark Endpoints

Benchmarks are admin-only and are supported only in `dev` and `test`.

Supported operations:

- `POST /api/admin/benchmarks/metadata`
- `POST /api/admin/benchmarks/discovery`
- `GET /api/admin/benchmarks/runs`
- `GET /api/admin/benchmarks/runs/{operation_run_id}`
- `POST /api/admin/benchmarks/runs/{operation_run_id}/cancel`

Execution contract:

- requires `MEDIA_MANAGER_BENCHMARKS_ENABLED=true`
- queue requests require the admin challenge word
- creates durable `operation_runs` and benchmark records before execution
- executes in the separate `media-manager-benchmark-worker` process
- never performs filesystem mutation
- operates only on synthetic benchmark-tagged DB data and records cleanup results durably

## Binary And HTML Routes

- `GET /ledger`
  - Renders the MediaFile ledger explorer page.
- `GET /operations`
  - Renders explicit operation controls for the API-backed workflows.

## First-Party Client Notes

- `operator_console/gui_app/` is the supported GUI integration layer and uses the shared API client under `src/lib/api/`.
- `operator_console/gui_upstream/` is an upstream snapshot only and may not reflect the live repository contract.
- lovable-driven upstream changes are expected to be selectively adapted into `gui_app`, not merged as a second runtime truth.
- the current `gui_app` API client, endpoint adapters, types, and admin flows are repository-owned integration code and should be treated as canonical unless intentionally redesigned alongside backend changes.
- `tools/e2e_workflow_sanity.sh` is the supported API-client smoke harness for workflow verification.
- `media-manager-benchmark-worker` is the supported benchmark execution process for queued admin benchmarks.

### Composite Run Note

`POST /api/run` is the canonical composite compatibility trigger (ingest + canonical recompute + plan + apply, or validation-only when `dry_run=true`).

## Unified Run History

`GET /api/runs` is now backed by the unified `operation_runs` log and is the
default operator-facing history feed.

Supported filters:
- `limit` (1..200)
- `operation_type` (`INGEST|PLAN|APPLY|OPERATOR_RUN|CANONICAL_RECOMPUTE|TAG_ENRICHMENT|DB_RESET`)
- `status` (`STARTED|COMPLETED|FAILED`)

Each row includes:
- `operation_run_id` (primary history id for GUI and automation operations)
- `operation_type`
- `status`
- `started_at`
- `completed_at`
- `duration_ms`
- `linked_run_id` (legacy planner/apply `runs.id` when available)
- `context`
- `error_message`

`GET /api/internal-runs` remains available for planner/apply lifecycle
records from the original `runs` table.

## Ledger Endpoints

Canonical ledger endpoints return paginated envelopes:

```json
{
  "total_count": 0,
  "page": 1,
  "limit": 30,
  "total_pages": 0,
  "items": []
}
```

Each item contains:

- `id`
- `current_path`
- `discovered_path`
- `size_bytes`
- `hash_sha256`
- `status`
- `discovered_at`
- `ingested_at`
- `deleted_at`

### `GET /api/media-file/by-hash`

Query params:
- `hash_prefix` (required)
- `page` (default `1`)
- `limit` (default `30`, max `100`)

### `GET /api/media-file/history`

Query params:
- `path` (required)
- `page` (default `1`)
- `limit` (default `30`, max `100`)

### `GET /api/media-file/by-status`

Query params:
- `status` (required): `INGESTED`, `PROCESSED`, `DELETED`
- `page` (default `1`)
- `limit` (default `30`, max `100`)

### `GET /api/media-file/reappearances`

Query params:
- `path` (required)
- `page` (default `1`)
- `limit` (default `30`, max `100`)

### `GET /api/admin/hash-audit`

Run a read-only ledger hash health audit (Phase 13 compliant; no row mutation).

Query params:
- `root_path` (optional, non-empty when provided)
- `sample_limit` (default `20`, max `200`)

Response:

```json
{
  "total_files": 1234,
  "missing_hash": 12,
  "hash_mismatches": 0,
  "deleted_rows_skipped": 3,
  "sample_missing_hash_paths": ["/dataset/a.jpg"],
  "sample_mismatch_paths": ["/dataset/b.jpg"]
}
```

### `GET /api/media-file/analytics`

Returns all-time, read-only Phase 13 ledger analytics for the `/ledger` page.

Response:

```json
{
  "totals": {
    "files_tracked": 0,
    "duplicate_hash_groups": 0
  },
  "by_status": {
    "INGESTED": 0,
    "PROCESSED": 0,
    "DELETED": 0
  },
  "ingested_per_day": [
    { "day": "2026-03-01", "count": 0 }
  ],
  "deleted_per_day": [
    { "day": "2026-03-01", "count": 0 }
  ],
  "reappearances_per_day": [
    { "day": "2026-03-01", "count": 0 }
  ],
  "window": {
    "mode": "all_time"
  }
}
```

Notes:
- `duplicate_hash_groups` counts hash values shared across more than one distinct ledger path.
- `reappearances_per_day` counts non-`DELETED` rows with a prior `DELETED` tombstone for the same path history (`current_path`/`discovered_path`).
- This endpoint is analytics-only and does not perform canonical inference or row mutation.

### `POST /api/media-file/validate`

Run ingest validation in read-only mode (no DB writes) and return a would-change delta report.

Request:

```json
{
  "folder_path": "/path/to/dataset",
  "policy_name": "FIRST_SEEN"
}
```

Response:

```json
{
  "mode": "VALIDATION_ONLY",
  "root_path": "/path/to/dataset",
  "generated_at": "2026-03-03T12:00:00+00:00",
  "scan": { "files_scanned": 10, "files_missing_during_scan": 0 },
  "delta": {
    "would_insert": 3,
    "would_update": 4,
    "would_mark_deleted": 1,
    "hash_mismatch_observed": 0,
    "would_reappear_after_delete": 1
  },
  "samples": {
    "would_insert": [],
    "would_update": [],
    "would_mark_deleted": [],
    "hash_mismatch_observed": []
  },
  "warnings": []
}
```

### `GET /api/media-file/dry-run-audit`

Return a best-effort historical audit of likely dry-run side effects.

Query params:
- `start` (optional ISO-8601 timestamp)
- `end` (optional ISO-8601 timestamp)
- `limit` (default `50`, max `200`)

Response fields:
- `coverage`: always `BEST_EFFORT`
- `method`: heuristic method description
- `window`: requested time window
- `candidates[]`: inferred windows with `confidence` (`LOW|MEDIUM`)
- `limitations[]`: explicit uncertainty caveats

### `POST /api/run` compatibility behavior

`POST /api/run` remains a feature-frozen compatibility alias. It returns a
validation-only payload when `dry_run=true`:

## Environment Variables

See [Environment Variables](../reference/environment-variables.md) for all Operator Console/runtime env flags, including metrics and admin safety controls.

```json
{
  "mode": "VALIDATION_ONLY",
  "validation_report": { "...": "same contract as /api/media-file/validate" }
}
```

When `dry_run=false`, behavior remains execution-oriented and returns:

```json
{
  "mode": "EXECUTION",
  "run_id": "...",
  "summary_metrics": { "...": "..." },
  "duplicates_found": 0,
  "canonical_changes": 0
}
```

## Validation and Error Semantics

- `400` for validation failures:
  - missing/blank required inputs
  - invalid status
  - invalid paging bounds
- Endpoints are read-only and ledger-only.
- No canonical/duplicate decision data is inferred or mutated by these APIs.
