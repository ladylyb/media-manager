# CLI API

::: media_manager.app.cli

## Ingest Dry-Run Validation

`media-manager ingest <path> --dry-run` runs read-only ingest validation and returns a would-change report.

- No DB writes occur in this mode.
- `--json` is supported only with `--dry-run`:
  - `media-manager ingest <path> --dry-run --json`

## Ledger Hash Audit Health Check

`media-manager health-check --audit-hashes` calls Operator Console REST API and reports ledger hash health.

Examples:
- `media-manager health-check --audit-hashes`
- `media-manager health-check --audit-hashes --root /dataset --api http://localhost:8000 --sample-limit 20`

Exit codes:
- `0`: no missing hashes or mismatches
- `1`: missing hashes and/or mismatches found
- `2`: invalid CLI args or API/transport failure
