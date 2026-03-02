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

## Quick Check Command

Use the built-in CLI quick check to verify canonical read cache metrics wiring:

```bash
media-manager observability-quick-check --run-id qc-demo --sample-size 1000
```

Expected pass signal:

1. Command exits with status `0`.
2. Output contains `Metrics complete: True`.
3. Output includes all metric families for both `source="base"` and `source="mv"`:
   - `canonical_read_cache_hits_total`
   - `canonical_read_cache_misses_total`
   - `canonical_read_cache_hit_ratio_percent`
