# Integrity And Duplicate Reclaim Rollout

This note defines the first implementation slice for integrity review and duplicate reclaim.

## Boundaries

- `media_file` remains an ingest ledger only.
- Integrity diagnosis is stored as separate durable facts tied to existing file identity.
- Duplicate reclaim review is a durable operator decision layer tied to duplicate groups.
- No filesystem mutation is introduced in this slice.

## Crash / Retry / Partial Completion

- Integrity scan is read-only. A crash during scan may leave a partially completed run row, but it does not mutate managed files.
- A retry creates a new integrity run and refreshes the latest integrity snapshot per file instance.
- Duplicate reclaim review updates a single durable record per duplicate group and is safe to retry because the latest status fully replaces the prior status.

## Current Scope

- Read-only integrity scan, issue listing, file detail, and review decisions (`MARK_OK`, `IGNORE`)
- Duplicate reclaim readiness (`REVIEWED_SAFE_TO_RECLAIM`) and read-model metrics
- Operator Console UI for integrity review and duplicate reclaim preparation

## Deferred Phases

- Quarantine, archive, restore, and retention-expiry actions
- Planned-action and apply-engine support for reversible reclaim and quarantine moves
- Auto-actions and policy-driven execution

## Invariant Notes

- Planner/apply remains the only place where future filesystem mutation may occur.
- Review decisions do not change canonical assignments.
- Reclaim readiness does not delete, archive, or rename files in this phase.
