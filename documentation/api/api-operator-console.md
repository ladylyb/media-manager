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

## Validation and Error Semantics

- `400` for validation failures:
  - missing/blank required inputs
  - invalid status
  - invalid paging bounds
- Endpoints are read-only and ledger-only.
- No canonical/duplicate decision data is inferred or mutated by these APIs.
