# CLI API

::: media_manager.app.cli

## Ingest Dry-Run Validation

`media-manager ingest <path> --dry-run` runs read-only ingest validation and returns a would-change report.

- No DB writes occur in this mode.
- `--json` emits the standard CLI v2 envelope:
  - `media-manager ingest <path> --dry-run --json`
  - `media-manager ingest <path> --json`

## CLI JSON Contract (v2 service layer)

Mutating and selected read commands support `--json` and return:

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

Operator-facing commands:
- `media-manager status --json`
- `media-manager operator <dashboard-summary|latest-metrics|runs> --json [--limit N]`
- `media-manager operator-run --folder-path <path> --policy-name <name> [--dry-run] --json`
- `media-manager policy-get --json`
- `media-manager policy-set --selected-policy <name> --version <n> [--preferred-root <path> ...] --json`

Optional remote transport for supported commands:
- `--transport local|http` (default `local`)
- `--api http://localhost:8000` (used with `--transport http`)
- `--timeout 30`

## GUI Operations Parity

The Operator Console `/operations` page maps directly to CLI-equivalent flows:

- Ingest: `media-manager ingest <path> [--dry-run]`
- Plan: `media-manager plan <path> [--strict-metadata]`
- Apply: `media-manager apply <run_id> [--collision-mode rename|skip|fail]`
- Canonical recompute: `media-manager canonical recompute --policy <name> [--dry-run|--apply]`
- Tag enrichment: `media-manager tag-enrich --all|--canonical-id <uuid> [--batch-size N]`
- Composite run (legacy): `media-manager operator-run --folder-path <path> --policy-name <name> [--dry-run]`

## Ledger Hash Audit Health Check

`media-manager health-check --audit-hashes` calls Operator Console REST API and reports ledger hash health.

Examples:
- `media-manager health-check --audit-hashes`
- `media-manager health-check --audit-hashes --root /dataset --api http://localhost:8000 --sample-limit 20`

Exit codes:
- `0`: no missing hashes or mismatches
- `1`: missing hashes and/or mismatches found
- `2`: invalid CLI args or API/transport failure

## Database Reset (Dev/Test Only)

`media-manager db-reset` calls the admin REST endpoint to preview or perform a destructive data reset.

Examples:
- `media-manager db-reset --dry-run`
- `media-manager db-reset --challenge-word media-manager`
- `media-manager db-reset --dry-run --json`

Safety:
- hard-blocked unless `MEDIA_MANAGER_ENV` is `dev` or `test`
- `--challenge-word` required unless `--dry-run`
- truncates data tables only; does not modify Alembic migration state
- optional override: `MEDIA_MANAGER_DB_RESET_CHALLENGE_WORD` (default `media-manager`)
- optional scope expansion: `MEDIA_MANAGER_DB_RESET_INCLUDE_DYNAMIC=true` (destructive, use only in isolated dev/test DBs)

Exit codes:
- `0`: success
- `1`: semantic failure from API response
- `2`: invalid CLI args or transport/parse failure

## Environment Variables

See [Environment Variables](../reference/environment-variables.md) for complete CLI/runtime configuration defaults and accepted values.
