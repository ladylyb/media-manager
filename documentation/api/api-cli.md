# CLI Command Reference

This page is the operational reference for every `media-manager` CLI command.

## How This Page Is Maintained

Source of truth for options and behavior:
- `media_manager/app/cli.py` (`build_parser()` and command handlers)
- `media_manager/app/core/perf_cli.py` (perf command behavior and exit codes)
- live `--help` output from the CLI entrypoint

If this page and parser code differ, treat code as authoritative and update docs in the same change.

## Global CLI Contract

Global flags apply to all commands:

| Flag | Required | Default | Allowed values | Meaning |
|---|---|---|---|---|
| `--transport` | No | `local` | `local`, `http` | Chooses local service calls vs HTTP for commands that support it. |
| `--api` | No | `http://localhost:8000` | Any base URL | Base URL for HTTP transport and for commands with built-in HTTP calls. |
| `--timeout` | No | `30` | Integer > `0` | HTTP timeout in seconds. |

Transport support by command:

| Command | Local | HTTP | Notes |
|---|---|---|---|
| `plan` | Yes | No | Always local. |
| `ingest` | Yes | Partial | HTTP supports only `--dry-run`; non-dry-run over HTTP is rejected. |
| `apply` | Yes | No | Always local. |
| `canonical recompute` | Yes | No | Always local. |
| `perf-run` | Yes | No | Always local. |
| `perf-compare` | Yes | No | Always local. |
| `perf-refresh-baseline` | Yes | No | Always local. |
| `legacy-import` | Yes | No | Always local. |
| `explain-file` | Yes | No | Always local. |
| `refresh-mv` | Yes | No | Always local. |
| `planner-benchmark` | Yes | No | Always local. |
| `observability-quick-check` | Yes | No | Always local. |
| `tag-enrich` | Yes | Yes | Supports both transports. |
| `status` | Yes | Yes | Supports both transports. |
| `operator` | Yes | Yes | Supports both transports. |
| `operator-run` | Yes | Yes | Supports both transports. |
| `policy-get` | Yes | Yes | Supports both transports. |
| `policy-set` | Yes | Yes | Supports both transports. |
| `health-check` | N/A | HTTP | Direct REST health probe command. |
| `db-reset` | N/A | HTTP | Admin REST endpoint command. |

Common exit-code convention:
- `0`: command succeeded
- `1`: command executed but returned semantic/runtime failure
- `2`: invalid arguments or transport/request validation failure

## CLI JSON Contract (v2 Envelope)

Many commands support `--json` and emit:

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

Some commands intentionally emit command-specific JSON payloads instead of this envelope (`perf-*`, and HTTP passthrough payloads for some commands).

## Command Index

| Command | Required positional args | Required flags | Side effects | Transport |
|---|---|---|---|---|
| `plan` | `path` | None | Ingests and creates a plan run (or simulation if `--simulate-policy`) | Local |
| `ingest` | `path` | None | Writes ingest state unless `--dry-run` | Local/HTTP(`--dry-run` only) |
| `apply` | `run_id` | None | Filesystem mutations and durable apply records | Local |
| `canonical recompute` | None | `--policy` | Mutates canonical assignments only with `--apply` | Local |
| `perf-run` | None | `--dataset`, `--env-class` | Runs ingest/plan/(apply) and writes perf artifact | Local |
| `perf-compare` | None | `--dataset`, `--env-class` | Read-only comparison of artifact vs baseline | Local |
| `perf-refresh-baseline` | None | `--dataset`, `--env-class` | Baseline write unless `--dry-run` | Local |
| `legacy-import` | None | `--sqlite-path` | Imports legacy SQLite into Postgres schemas | Local |
| `explain-file` | `file_id` | None | Read-only artifact explanation | Local |
| `refresh-mv` | None | None | Refreshes materialized view | Local |
| `planner-benchmark` | None | None | Read-heavy benchmark query workload | Local |
| `observability-quick-check` | None | None | Emits cache-metric lines for a run label | Local |
| `tag-enrich` | None | One of `--all` or `--canonical-id` | Writes enrichment records | Local/HTTP |
| `status` | None | None | Read-only status read | Local/HTTP |
| `operator` | `resource` | None | Read-only operator resource read | Local/HTTP |
| `operator-run` | None | `--folder-path`, `--policy-name` | Triggers run workflow unless `--dry-run` | Local/HTTP |
| `policy-get` | None | None | Read-only policy read | Local/HTTP |
| `policy-set` | None | `--selected-policy`, `--version` | Persists policy settings | Local/HTTP |
| `health-check` | None | None | Read-only REST health check | HTTP |
| `db-reset` | None | None | Potentially destructive data reset | HTTP |

## Safety And Side Effects

High-impact commands:
- `apply`: executes planned file actions; use only after plan validation.
- `operator-run` without `--dry-run`: can ingest/plan/apply via unified run trigger.
- `db-reset` without `--dry-run`: destructive reset path; challenge word required.
- `refresh-mv`: issues materialized view refresh operations.
- `canonical recompute --apply`: appends changed canonical assignments.

Use isolated dev/test environments for destructive commands.

## Per-Command Reference

### `plan`

Purpose: build deterministic planned actions for a file/directory, or simulate policy impact.

Inputs:
- Required: `path`
- Optional: `--strict-metadata`, `--simulate-policy`, `--policy`, `--preferred-root` (repeatable), `--json`

Validation rules:
- `path` must exist.
- `--preferred-root` is meaningful for simulation with `PREFER_ROOT` policy.

State combinations:

| State | Example | Outcome |
|---|---|---|
| Normal planning | `media-manager plan /data/inbox` | Ingests files if needed, creates run, stores planned actions, prints grouped summary and run id. |
| Strict metadata | `media-manager plan /data/inbox --strict-metadata` | Same as normal planning, but fails if required metadata codes are missing. |
| Simulation default policy | `media-manager plan /data/inbox --simulate-policy` | Does not run planner/apply; simulates canonical policy delta using default policy and writes simulation artifact. |
| Simulation explicit policy | `media-manager plan /data/inbox --simulate-policy --policy PREFER_ROOT --preferred-root /data/preferred` | Simulates policy using preferred roots and prints impacted canonical changes. |
| Repeatable preferred roots | `media-manager plan /data/inbox --simulate-policy --policy PREFER_ROOT --preferred-root /data/a --preferred-root /data/b` | Same as simulation, with deterministic root-priority tie-breaking order from provided roots. |
| JSON output | `media-manager plan /data/inbox --json` | Emits JSON envelope with run id and planning summary counters. |
| Invalid path | `media-manager plan /does/not/exist` | Fails validation (`exit 2`) before planning. |

Exit behavior:
- `0` success
- `1` policy/runtime failure
- `2` argument/path validation failure

### `ingest`

Purpose: ingest media files into logical content/instance tables, or validate would-change delta.

Inputs:
- Required: `path`
- Optional: `--dry-run`, `--json`, global transport flags

Validation rules:
- Local mode: `path` must exist.
- HTTP mode: only `--dry-run` is accepted.

State combinations:

| State | Example | Outcome |
|---|---|---|
| Local ingest mutate | `media-manager ingest /data/inbox` | Scans files and writes ingest rows; prints ingest summary. |
| Local ingest dry-run | `media-manager ingest /data/inbox --dry-run` | Read-only validation report; no ingest writes. |
| Local ingest dry-run JSON | `media-manager ingest /data/inbox --dry-run --json` | JSON envelope containing validation delta report. |
| Local ingest JSON | `media-manager ingest /data/inbox --json` | JSON envelope with ingest counters/duration. |
| HTTP ingest dry-run | `media-manager --transport http ingest /data/inbox --dry-run` | Calls API validation endpoint and returns API result. |
| HTTP ingest dry-run JSON | `media-manager --transport http ingest /data/inbox --dry-run --json` | Prints raw API JSON response payload. |
| Invalid HTTP mutate request | `media-manager --transport http ingest /data/inbox` | Rejected immediately because HTTP mode only supports dry-run (`exit 2`). |

### `apply`

Purpose: execute an existing planned run.

Inputs:
- Required: `run_id` (UUID)
- Optional: `--collision-mode` (`rename`, `skip`, `fail`), `--json`

Validation rules:
- `run_id` must be a valid UUID.

State combinations:

| State | Example | Outcome |
|---|---|---|
| Default collision handling | `media-manager apply 11111111-1111-1111-1111-111111111111` | Applies run using rename-on-collision policy and prints apply summary. |
| Skip collisions | `media-manager apply 11111111-1111-1111-1111-111111111111 --collision-mode skip` | Applies run but skips actions when target path exists. |
| Fail on collision | `media-manager apply 11111111-1111-1111-1111-111111111111 --collision-mode fail` | Aborts on first path collision according to apply service behavior. |
| JSON output | `media-manager apply 11111111-1111-1111-1111-111111111111 --json` | JSON envelope with apply counters. |
| Invalid UUID | `media-manager apply not-a-uuid` | Rejected before apply starts (`exit 2`). |

### `canonical recompute`

Purpose: deterministically recompute canonical assignments for duplicate content.

Inputs:
- Required: `--policy`
- Optional: `--dry-run`, `--apply`, `--preferred-root` (repeatable), `--json`

Validation rules:
- `--dry-run` and `--apply` are mutually exclusive.
- Policy name must be valid.

State combinations:

| State | Example | Outcome |
|---|---|---|
| Default dry-run mode | `media-manager canonical recompute --policy FIRST_SEEN` | Runs recompute in dry-run mode and reports what would change. |
| Explicit dry-run | `media-manager canonical recompute --policy FIRST_SEEN --dry-run` | Same behavior as default mode. |
| Apply changes | `media-manager canonical recompute --policy FIRST_SEEN --apply` | Appends changed canonical assignments durably. |
| Preferred roots single | `media-manager canonical recompute --policy PREFER_ROOT --preferred-root /data/preferred` | Uses provided root preference for tie-breaking. |
| Preferred roots multiple | `media-manager canonical recompute --policy PREFER_ROOT --preferred-root /data/a --preferred-root /data/b --apply` | Applies recompute with deterministic root ordering from repeated flags. |
| JSON output | `media-manager canonical recompute --policy FIRST_SEEN --json` | JSON envelope with scanned/changed/applied/failed counters and ids. |
| Invalid mutual flags | `media-manager canonical recompute --policy FIRST_SEEN --dry-run --apply` | Rejected by handler (`exit 2`). |

### `perf-run`

Purpose: run perf workflow and emit a run artifact JSON file.

Inputs:
- Required: `--dataset`, `--env-class`
- Optional: `--policy` (default `FIRST_SEEN`), `--dry-run`, `--strict-metadata`

Validation rules:
- Dataset path must exist.

State combinations:

| State | Example | Outcome |
|---|---|---|
| Full perf run | `media-manager perf-run --dataset /data/inbox --env-class local` | Runs ingest, plan, apply; writes perf artifact; prints PASS/FAIL JSON summary. |
| Dry-run perf | `media-manager perf-run --dataset /data/inbox --env-class ci --dry-run` | Runs ingest+plan only; skips apply stage; still emits artifact. |
| Strict metadata | `media-manager perf-run --dataset /data/inbox --env-class ci --strict-metadata` | Fails fast if planner hits required metadata gaps. |
| Explicit policy label | `media-manager perf-run --dataset /data/inbox --env-class ci --policy PREFER_ROOT` | Same pipeline; policy label is included in perf metadata context/notes. |
| Invalid dataset path | `media-manager perf-run --dataset /missing --env-class ci` | Rejected before workflow (`exit 2`). |

### `perf-compare`

Purpose: compare current perf artifact against stored baseline.

Inputs:
- Required: `--dataset`, `--env-class`
- Optional: `--artifact`, `--policy`, `--dry-run`

Validation rules:
- If `--artifact` omitted, command resolves latest matching artifact.
- Missing artifact or baseline is a validation failure.

State combinations:

| State | Example | Outcome |
|---|---|---|
| Auto-select latest artifact | `media-manager perf-compare --dataset /data/inbox --env-class ci` | Loads latest matching run artifact and compares it to baseline. |
| Explicit artifact | `media-manager perf-compare --dataset /data/inbox --env-class ci --artifact artifacts/perf/runs/perf_artifact_20260304T120000Z.json` | Uses specific artifact file for baseline comparison. |
| With passthrough flags | `media-manager perf-compare --dataset /data/inbox --env-class ci --policy FIRST_SEEN --dry-run` | `--policy` and `--dry-run` are accepted for parity; comparison logic is unchanged. |
| Missing baseline/artifact | `media-manager perf-compare --dataset /data/inbox --env-class unknown` | Fails with lookup error (`exit 2`). |

### `perf-refresh-baseline`

Purpose: validate or store perf baseline for dataset/environment.

Inputs:
- Required: `--dataset`, `--env-class`
- Optional: `--artifact`, `--policy`, `--dry-run`

Validation rules:
- In dry-run mode, payload fields and identity must match requested dataset/env.

State combinations:

| State | Example | Outcome |
|---|---|---|
| Store baseline | `media-manager perf-refresh-baseline --dataset /data/inbox --env-class ci` | Selects artifact and stores as baseline for dataset/env. |
| Store explicit artifact | `media-manager perf-refresh-baseline --dataset /data/inbox --env-class ci --artifact artifacts/perf/runs/perf_artifact_20260304T120000Z.json` | Stores the specified artifact as baseline. |
| Dry-run validation | `media-manager perf-refresh-baseline --dataset /data/inbox --env-class ci --dry-run` | Validates write contract without persisting baseline. |
| Dry-run mismatch | `media-manager perf-refresh-baseline --dataset /data/inbox --env-class ci --artifact artifacts/perf/runs/other_env.json --dry-run` | Validation fails if dataset/env/metrics version mismatch (`exit 2`). |

### `legacy-import`

Purpose: one-off import from legacy SQLite into `legacy_raw` and `legacy_3nf`.

Inputs:
- Required: `--sqlite-path`
- Optional: `--pg-url`, `--raw-schema` (default `legacy_raw`), `--normalized-schema` (default `legacy_3nf`), `--import-run-id`, `--source-db-name`

Validation rules:
- SQLite path must exist.
- `--import-run-id` must be UUID if provided.

State combinations:

| State | Example | Outcome |
|---|---|---|
| Minimal import | `media-manager legacy-import --sqlite-path /tmp/legacy.db` | Imports using default DB URL and default schema names; prints import summary. |
| DB URL override | `media-manager legacy-import --sqlite-path /tmp/legacy.db --pg-url postgresql://user:pass@localhost/db` | Imports into explicitly provided Postgres target. |
| Schema overrides | `media-manager legacy-import --sqlite-path /tmp/legacy.db --raw-schema legacy_raw_v2 --normalized-schema legacy_3nf_v2` | Imports into custom legacy schemas. |
| Stable resume id | `media-manager legacy-import --sqlite-path /tmp/legacy.db --import-run-id 22222222-2222-2222-2222-222222222222` | Uses explicit import run id for resume/idempotency tracking. |
| With source label | `media-manager legacy-import --sqlite-path /tmp/legacy.db --source-db-name archive-2024` | Adds source DB label metadata to import records. |
| Invalid UUID | `media-manager legacy-import --sqlite-path /tmp/legacy.db --import-run-id bad-id` | Rejected before import (`exit 2`). |

### `explain-file`

Purpose: explain canonical decision for one file id from latest decision trace artifact.

Inputs:
- Required: `file_id` (UUID string expected by artifact)
- Optional: `--json`

Validation rules:
- Requires an existing latest decision trace artifact.
- Fails if file id is not found in that artifact.

State combinations:

| State | Example | Outcome |
|---|---|---|
| Human-readable explanation | `media-manager explain-file 33333333-3333-3333-3333-333333333333` | Prints decision reason, tie-breaker, rules, and candidate set. |
| JSON output | `media-manager explain-file 33333333-3333-3333-3333-333333333333 --json` | Emits JSON payload with explanation data. |
| Missing artifact | `media-manager explain-file 33333333-3333-3333-3333-333333333333` | Fails when no decision trace exists (`exit 1`). |
| Unknown file id | `media-manager explain-file 00000000-0000-0000-0000-000000000000` | Fails when file is absent in latest trace (`exit 1`). |

### `refresh-mv`

Purpose: refresh `mv_canonical_metadata` materialized view.

Inputs:
- Required: none
- Optional: `--concurrently` or `--no-concurrently` (default concurrently), `--scheduled`, `--schedule-label`, `--json`

Validation rules:
- `--concurrently` and `--no-concurrently` are opposing flag states.

State combinations:

| State | Example | Outcome |
|---|---|---|
| Default concurrent refresh | `media-manager refresh-mv` | Performs one concurrent refresh and prints summary. |
| Non-concurrent refresh | `media-manager refresh-mv --no-concurrently` | Performs standard refresh without `CONCURRENTLY`. |
| Advisory schedule mode | `media-manager refresh-mv --scheduled --schedule-label hourly` | Still performs one refresh, and marks output with schedule advisory metadata. |
| JSON output | `media-manager refresh-mv --json` | Emits JSON envelope with refresh summary. |

### `planner-benchmark`

Purpose: benchmark canonical metadata reads from base tables vs materialized view.

Inputs:
- Required: none
- Optional: `--sample-size` (default `1000`), `--repeats` (default `5`), `--seed` (default `42`), `--use-cache`, `--json`

State combinations:

| State | Example | Outcome |
|---|---|---|
| Default benchmark | `media-manager planner-benchmark` | Runs benchmark with default sample/repeat/seed and prints comparison. |
| Larger sample | `media-manager planner-benchmark --sample-size 5000 --repeats 10` | Uses higher workload to compare read latency behavior. |
| Cached MV lookup | `media-manager planner-benchmark --use-cache` | Enables optional in-memory read cache for MV path during benchmark. |
| JSON output | `media-manager planner-benchmark --json` | Emits JSON envelope with benchmark metrics. |

### `observability-quick-check`

Purpose: perform base+MV metadata reads and show matching Prometheus cache metrics.

Inputs:
- Required: none
- Optional: `--run-id`, `--sample-size` (default `1000`), `--json`

State combinations:

| State | Example | Outcome |
|---|---|---|
| Default run id generation | `media-manager observability-quick-check` | Generates run id, emits reads, and prints matching metric lines. |
| Explicit run id | `media-manager observability-quick-check --run-id obs-check-001` | Uses your run id label for metric filtering and output. |
| Custom sample size | `media-manager observability-quick-check --sample-size 250` | Reads up to 250 canonical rows per source. |
| JSON output | `media-manager observability-quick-check --json` | Emits JSON envelope; `ok=false` if expected metric families are incomplete. |

### `tag-enrich`

Purpose: run deterministic tag enrichment for all canonical items or one canonical id.

Inputs:
- Required: exactly one of `--all` or `--canonical-id`
- Optional: `--batch-size` (default `100`), `--source` (`ai|manual|import|system`, default `system`), `--json`, global transport flags

Validation rules:
- Exactly one of `--all` or `--canonical-id` must be supplied.
- `--canonical-id` must be valid UUID when used.
- `--batch-size` must be greater than `0`.

State combinations:

| State | Example | Outcome |
|---|---|---|
| All canonical records | `media-manager tag-enrich --all` | Enriches all current canonical content ids. |
| Single canonical id | `media-manager tag-enrich --canonical-id 44444444-4444-4444-4444-444444444444` | Enriches exactly one canonical id. |
| Repeat with source override | `media-manager tag-enrich --all --source ai --batch-size 50` | Runs enrichment in fixed-size batches and writes source as `ai`. |
| HTTP transport | `media-manager --transport http tag-enrich --all --api http://localhost:8000` | Sends enrichment request to API endpoint instead of local services. |
| JSON output | `media-manager tag-enrich --all --json` | Emits JSON envelope (local) or API response (HTTP). |
| Invalid both modes | `media-manager tag-enrich --all --canonical-id 44444444-4444-4444-4444-444444444444` | Rejected because exactly one mode is required (`exit 2`). |
| Invalid neither mode | `media-manager tag-enrich` | Rejected for missing selection mode (`exit 2`). |
| Invalid canonical UUID | `media-manager tag-enrich --canonical-id bad-id` | Rejected before enrichment (`exit 2`). |
| Invalid batch size | `media-manager tag-enrich --all --batch-size 0` | Rejected before enrichment (`exit 2`). |

### `status`

Purpose: read current operator status metadata.

Inputs:
- Required: none
- Optional: `--json`, global transport flags

State combinations:

| State | Example | Outcome |
|---|---|---|
| Local status | `media-manager status` | Prints active phase and summary values from local read service. |
| Local JSON | `media-manager status --json` | Emits JSON envelope with status payload. |
| HTTP status | `media-manager --transport http status --api http://localhost:8000` | Calls `/api/v2/status` and prints status summary. |
| HTTP JSON | `media-manager --transport http status --json` | Prints raw API JSON response. |

### `operator`

Purpose: read operator-console resources through local read service or HTTP.

Inputs:
- Required: `resource`
- Optional shared filters: `--limit`, `--page`, `--tags`, `--sort-by`, `--sort-order`, `--source`, `--min-confidence`, `--q`, `--hash-prefix`, `--path`, `--status`, `--root-path`, `--sample-limit`, `--start`, `--end`, `--json`, global transport flags

Validation rules:
- Resource must be one of the parser-supported names.
- Some flags are meaningful only for specific resources.

#### Operator Resource Matrix

| Resource | Typical meaning | Key filters | Pagination |
|---|---|---|---|
| `dashboard-summary` | Aggregate dashboard counters | none | No |
| `latest-metrics` | Most recent pipeline metrics | none | No |
| `runs` | Recent runs list | `--limit` | No (`limit` only) |
| `duplicates` | Duplicate summaries | none | No |
| `canonical` | Canonical records listing | `--page`, `--limit`, `--tags`, `--sort-by`, `--sort-order`, `--source`, `--min-confidence` | Yes |
| `canonical-tags` | Tag suggestion terms | `--q`, `--limit` | No |
| `media-file-by-hash` | File lookup by hash prefix | `--hash-prefix`, `--page`, `--limit` | Yes |
| `media-file-history` | File history by path | `--path`, `--page`, `--limit` | Yes |
| `media-file-by-status` | Files by status enum | `--status`, `--page`, `--limit` | Yes |
| `media-file-reappearances` | Reappearance events by path | `--path`, `--page`, `--limit` | Yes |
| `media-file-analytics` | Aggregate analytics view | none | No |
| `ledger-hash-audit` | Filesystem-vs-ledger hash audit | `--root-path`, `--sample-limit` | No |
| `media-file-dry-run-audit` | Dry-run audit history | `--start`, `--end`, `--limit` | No (`limit` only) |

State combinations:

| State | Example | Outcome |
|---|---|---|
| Basic resource read | `media-manager operator dashboard-summary` | Returns dashboard summary payload. |
| Paginated canonical read | `media-manager operator canonical --page 2 --limit 25 --sort-by created_at --sort-order desc` | Returns page 2 canonical records with chosen sort. |
| Canonical filtered | `media-manager operator canonical --tags portrait,night --source ai --min-confidence 0.8` | Returns canonical records constrained by tag/source/confidence filters. |
| Hash lookup | `media-manager operator media-file-by-hash --hash-prefix a1b2c3 --page 1 --limit 20` | Returns matching files for hash prefix. |
| Path history | `media-manager operator media-file-history --path /data/inbox/img001.jpg --page 1 --limit 20` | Returns ledger history for one path. |
| Status filter | `media-manager operator media-file-by-status --status ACTIVE --page 1 --limit 50` | Returns files with requested status. |
| Ledger hash audit scoped | `media-manager operator ledger-hash-audit --root-path /data/inbox --sample-limit 20` | Returns hash audit summary plus sampled paths. |
| Dry-run audit window | `media-manager operator media-file-dry-run-audit --start 2026-03-01T00:00:00Z --end 2026-03-04T00:00:00Z --limit 100` | Returns dry-run audit entries within ISO time range. |
| HTTP transport | `media-manager --transport http operator runs --limit 10 --api http://localhost:8000` | Uses API endpoints for same resource semantics. |
| JSON output | `media-manager operator runs --limit 10 --json` | Emits envelope (local) or API response (HTTP) in JSON form. |

### `operator-run`

Purpose: trigger an operator workflow run (composite command).

Inputs:
- Required: `--folder-path`, `--policy-name`
- Optional: `--dry-run`, `--json`, global transport flags

State combinations:

| State | Example | Outcome |
|---|---|---|
| Standard run trigger | `media-manager operator-run --folder-path /data/inbox --policy-name FIRST_SEEN` | Triggers run workflow using provided folder/policy. |
| Dry-run trigger | `media-manager operator-run --folder-path /data/inbox --policy-name FIRST_SEEN --dry-run` | Triggers read-only validation workflow mode. |
| HTTP transport | `media-manager --transport http operator-run --folder-path /data/inbox --policy-name FIRST_SEEN --api http://localhost:8000` | Sends run trigger to API endpoint. |
| JSON output | `media-manager operator-run --folder-path /data/inbox --policy-name FIRST_SEEN --json` | Prints JSON result (envelope local, API payload HTTP). |

### `policy-get`

Purpose: fetch current operator policy settings.

Inputs:
- Required: none
- Optional: `--json`, global transport flags

State combinations:

| State | Example | Outcome |
|---|---|---|
| Local read | `media-manager policy-get` | Prints current persisted policy settings object. |
| Local JSON | `media-manager policy-get --json` | Emits JSON envelope with settings. |
| HTTP read | `media-manager --transport http policy-get --api http://localhost:8000` | Reads settings via `/api/v2/policy`. |
| HTTP JSON | `media-manager --transport http policy-get --json` | Prints raw API JSON response. |

### `policy-set`

Purpose: update operator policy settings with optimistic concurrency.

Inputs:
- Required: `--selected-policy`, `--version`
- Optional: `--preferred-root` (repeatable), `--recanonicalization-enabled` or `--no-recanonicalization-enabled` (default false), `--json`, global transport flags

Validation rules:
- `--version` is required for optimistic concurrency control.

State combinations:

| State | Example | Outcome |
|---|---|---|
| Minimal update | `media-manager policy-set --selected-policy FIRST_SEEN --version 3` | Persists selected policy with current defaults. |
| Enable recanonicalization | `media-manager policy-set --selected-policy FIRST_SEEN --version 3 --recanonicalization-enabled` | Persists same policy with recanonicalization enabled. |
| Disable recanonicalization explicitly | `media-manager policy-set --selected-policy FIRST_SEEN --version 3 --no-recanonicalization-enabled` | Persists explicit false state. |
| Single preferred root | `media-manager policy-set --selected-policy PREFER_ROOT --version 3 --preferred-root /data/preferred` | Stores one preferred root for policy context. |
| Multiple preferred roots | `media-manager policy-set --selected-policy PREFER_ROOT --version 3 --preferred-root /data/a --preferred-root /data/b` | Stores ordered preferred-root list from repeated flags. |
| HTTP transport | `media-manager --transport http policy-set --selected-policy FIRST_SEEN --version 3 --api http://localhost:8000` | Sends update request to API endpoint. |
| JSON output | `media-manager policy-set --selected-policy FIRST_SEEN --version 3 --json` | Returns envelope (local) or API payload (HTTP). |

### `health-check`

Purpose: run read-only REST health checks against operator-console endpoint(s).

Inputs:
- Required by behavior: `--audit-hashes` must be present
- Optional: `--root`, `--api` (default `http://localhost:8000`), `--timeout` (default `30`), `--sample-limit` (default `20`)

Validation rules:
- `--audit-hashes` is required for this phase.
- `--timeout` must be greater than `0`.
- `--sample-limit` must be within `[1, 200]`.
- Uses explicit REST call to `/api/v1/ledger/hash-audit`.

State combinations:

| State | Example | Outcome |
|---|---|---|
| Minimal valid health check | `media-manager health-check --audit-hashes` | Calls hash-audit endpoint and prints audit summary. |
| Scoped root | `media-manager health-check --audit-hashes --root /data/inbox` | Audits hash health only under provided root path scope. |
| Custom API and timeout | `media-manager health-check --audit-hashes --api http://localhost:8000 --timeout 15 --sample-limit 50` | Runs same check against chosen endpoint/timeouts. |
| Missing required flag | `media-manager health-check` | Rejected because `--audit-hashes` is required (`exit 2`). |
| Invalid sample bounds | `media-manager health-check --audit-hashes --sample-limit 500` | Rejected before request (`exit 2`). |

Exit behavior:
- `0`: no missing hashes and no hash mismatches
- `1`: hash audit found missing hashes or mismatches
- `2`: invalid args, request failure, or invalid API response

### `db-reset`

Purpose: call admin REST endpoint to preview or perform application data reset.

Inputs:
- Required by behavior: `--challenge-word` unless `--dry-run`
- Optional: `--dry-run`, `--challenge-word`, `--json`, `--api`, `--timeout`

Validation rules:
- Non-dry-run requests require challenge word.
- Uses REST path `/api/v2/admin/db-reset`.

State combinations:

| State | Example | Outcome |
|---|---|---|
| Dry-run preview | `media-manager db-reset --dry-run` | Calls API and prints affected tables preview without deleting data. |
| Dry-run JSON | `media-manager db-reset --dry-run --json` | Prints API JSON response for preview mode. |
| Destructive reset | `media-manager db-reset --challenge-word media-manager` | Performs reset request using provided confirmation token. |
| Destructive reset JSON | `media-manager db-reset --challenge-word media-manager --json` | Prints API JSON response for destructive request. |
| Invalid missing challenge | `media-manager db-reset` | Rejected before API call because non-dry-run requires challenge word (`exit 2`). |

Safety notes:
- Endpoint enforces additional runtime guards (`MEDIA_MANAGER_ENV` and challenge checks) server-side.
- Use only in isolated dev/test databases.

## Examples And Testing Notes

Parse-only checks:
- `./.venv/bin/python -m media_manager.app.cli --help`
- `./.venv/bin/python -m media_manager.app.cli <command> --help`

Non-mutating examples:
- Prefer `ingest --dry-run`, `canonical recompute --dry-run`, and read commands for safe trial runs.

Mutating examples:
- `apply`, non-dry-run `operator-run`, non-dry-run `db-reset`, `refresh-mv`, and `canonical recompute --apply` change runtime state.

## Environment Variables

See [Environment Variables](../reference/environment-variables.md) for runtime defaults and accepted values.
