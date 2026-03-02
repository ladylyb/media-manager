# Drift Diagnosis

Use this runbook when observed filesystem state diverges from expected run outcomes.

## Symptoms

- files moved unexpectedly
- expected moves missing after apply
- repeated NOOP where actions are expected
- duplicate marking inconsistent with recent inputs

## Diagnosis Flow

1. Confirm the exact `run_id` under investigation.
2. Reconstruct intended behavior from plan/apply summaries.
3. Compare expected action totals against observed filesystem outcomes.
4. Check for apply errors or interruption during execution.
5. Check for manual filesystem edits during or after run execution.

## Containment

- stop additional apply attempts on unrelated runs for same dataset
- avoid manual bulk moves until root cause is identified
- keep investigation scoped to one run at a time

## Recovery Direction

- if apply interrupted: follow [Resume and Recovery](resume-and-recovery.md)
- if behavior mismatch persists after clean rerun: raise incident and preserve artifacts (logs, command history, run summaries)

## Escalate When

- the same dataset drifts repeatedly across reruns
- counters indicate errors with no clear environmental cause
- canonical assignment outcomes change unexpectedly without policy change
