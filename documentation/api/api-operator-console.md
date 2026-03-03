# Operator Console API

Read-only ledger endpoints introduced for Phase 13 GUI-first diagnostics.

## HTML Route

- `GET /ledger`
  - Renders the MediaFile ledger explorer page.

## Ledger Endpoints

All endpoints return paginated envelopes:

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

### `POST /api/run` dry-run behavior

`POST /api/run` now returns a validation-only payload when `dry_run=true`:

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
