# Operational Guardrails (Canonical)

| Document Authority | Scope |
| --- | --- |
| Authoritative for | Runtime limits, stop-the-line criteria, retry/timeout policy, safe mode, backpressure |
| Not authoritative for | Milestone scope, schema design details, narrative roadmap |
| Canonical technical source | `07-unified-architecture-spec.md` |

## Hard Runtime Limits (Defaults)
- `max_batch_size`: 500 planned actions per apply scheduling batch.
- `max_apply_workers`: 4 concurrent workers per run.
- `max_lock_lease_seconds`: 120 seconds before stale-lock reconciliation.
- `run_heartbeat_seconds`: 15 seconds.
- `max_action_exec_seconds`: 60 seconds per action before timeout classification.

## Retry Policy
- No implicit retries in planner or apply.
- Retry requires explicit `resume` for same `run_id`.
- Resume performs reconciliation before any re-execution.

## Dry-Run Contract
- Dry-run must not mutate filesystem.
- Dry-run must not append `file_actions`.
- Dry-run may persist `runs`, `intents`, `planned_actions` and report artifacts.

## Safe Mode
Safe mode is read-only diagnostics:
- inventory and drift scans
- schema/version validation
- run and failure reporting

Safe mode forbids:
- `apply`
- lock acquisition for execution
- any filesystem mutation

## Stop-the-Line Criteria
Execution must fail-fast when any condition holds:
- schema version mismatch
- invalid run/action state transition
- unresolved collisions without explicit policy
- target path outside configured allowlist
- DB write path unavailable during apply
- lock ownership lost
- drift ratio >= configured threshold (default 1%)
- failure ratio >= configured threshold (default 20%)
- pending actions from another run unless explicit resume intent is supplied

## Backpressure Policy
When `p95 action latency` or failure ratio breaches threshold:
- pause new action locking
- allow executing actions to finish or timeout
- append run-level `failure_event` with reason code
- require operator resume/retry decision

## Logging and Audit Minimums
Structured logs must include:
- `run_id`, `planned_action_id`, `stage`, `action`, `operation`, `src_path`, `target_path`, `status`, `error_code`, `timestamp`

Every physical mutation attempt must produce durable outcome records:
- success -> `file_actions` + optional `facts`
- failure -> `failure_events` + `planned_actions.state=FAILED`

## Configuration Guardrails
- single resolved config snapshot per run
- mandatory root allowlist
- explicit exclude patterns
- immutable config hash stored on `runs`
