# Observability

This guide defines what to capture and correlate during operations.

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

1. command issued
2. `run_id`
3. summary counters
4. any error output
5. whether rerun was attempted

## Minimum Incident Record

- timestamp (UTC)
- run identifier
- phase of failure
- error message
- recovery action taken
- final outcome
