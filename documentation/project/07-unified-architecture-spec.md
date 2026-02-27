# Unified Architecture Specification (Canonical)

| Document Authority | Scope |
| --- | --- |
| Authoritative for | Runtime invariants, domain model, persistence schema, planner/apply semantics, failure/restart behavior |
| Not authoritative for | Product vision narrative and historical context |
| Strict supersession rule | If conflict exists, this spec overrides `00`-`06`, except `documentation/AGENTS.md` and `documentation/STATE_MACHINE.md` which remain strict authority |

This file is authoritative for runtime invariants and execution semantics.

## 1. System Overview

### Purpose
Provide a deterministic media-management engine where planner output is pure intent and apply is restart-safe, audit-complete execution.

### Non-Goals
- Hidden retries.
- Planner mutation of execution facts.
- Multiple durable truth sources.
- Best-effort apply semantics.

### Core Invariants (Testable)
1. No filesystem mutation without durable DB gating.
2. Planner is side-effect free on filesystem and execution facts.
3. Apply is restart-safe from durable boundaries.
4. Execution is idempotent by key and state contract.
5. Failure appends durable facts/events.
6. Drift is detectable and reportable.
7. Invalid state transitions hard-fail.

### Architectural Philosophy
- Invalid states are unrepresentable.
- State transitions are explicit.
- Crashes are survivable.
- Drift is visible.
- Append-only facts are preferred over mutable history.
- Deterministic replay is preferred over ad hoc correction.

## 2. Domain Model

### Media
- Responsibility: logical content identity/group.
- Lifecycle: created on discovery or canonicalization grouping, never deleted by apply.
- Invariants: identity fields immutable; updates occur via appended facts.

### File
- Responsibility: physical file observation and metadata snapshot.
- Lifecycle: discovered -> enriched -> referenced by plans/actions.
- Invariants: discovery attributes immutable per observation event.

### Intent
- Responsibility: durable request context for run operation.
- Lifecycle: created during planning; immutable after run completion.
- Invariants: never treated as execution fact.

### Run
- Responsibility: lifecycle boundary for plan/apply.
- Lifecycle states: `CREATED`, `PLANNED`, `APPLYING`, `FAILED`, `COMPLETED`, `ABORTED`.
- Invariants: transitions only allowed by state machine.

### PlannedAction
- Responsibility: executable intent unit.
- Lifecycle states: `PENDING`, `LOCKED`, `EXECUTING`, `SUCCEEDED`, `FAILED`.
- Invariants: deterministic idempotency key, explicit transition path.

### FileAction
- Responsibility: immutable execution outcome fact.
- Lifecycle: append-only rows for success/failure outcomes.
- Invariants: never rewritten; de-duplicated by unique outcome guard.

### FailureEvent
- Responsibility: immutable error/drift/validation event.
- Lifecycle: append on all error paths.
- Invariants: includes phase, reason_code, context, timestamp.

### Fact
- Responsibility: cross-cutting append-only event model for audits/reconciliation.
- Lifecycle: append-only.
- Invariants: no in-place mutation.

## 3. Canonical Persistence Schema

### 3.1 Enum Contracts
- `run_state`: `CREATED | PLANNED | APPLYING | FAILED | COMPLETED | ABORTED`
- `planned_action_state`: `PENDING | LOCKED | EXECUTING | SUCCEEDED | FAILED`
- `action_primitive`: `move | rename | delete | keep | ignore`

Invalid enum values are rejected by DB constraints and pre-write validation.

### 3.2 State Transition Contracts
Run transitions (exact):
- `CREATED -> PLANNED`
- `PLANNED -> APPLYING`
- `APPLYING -> COMPLETED`
- `APPLYING -> FAILED`
- `FAILED -> APPLYING` (resume)
- `ANY -> ABORTED` (manual)

Planned action transitions (exact):
- `PENDING -> LOCKED -> EXECUTING -> SUCCEEDED`
- `PENDING -> LOCKED -> EXECUTING -> FAILED`

Any invalid transition:
- reject transition
- append `failure_events` row with `reason_code='INVALID_STATE_TRANSITION'`

### 3.3 Tables

#### `media`
| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| id | INTEGER | NO | PK |
| media_uid | TEXT | NO | stable logical identity |
| media_type | TEXT | NO | image/video/audio/other |
| created_at | DATETIME | NO | default current timestamp |

Constraints:
- PK: `id`
- Unique: `media_uid`
Indexes:
- `idx_media_type(media_type)`

#### `files`
| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| id | INTEGER | NO | PK |
| media_id | INTEGER | YES | FK -> media.id |
| observed_path | TEXT | NO | discovered path snapshot |
| filename | TEXT | NO | basename snapshot |
| extension | TEXT | YES | normalized lower-case |
| size_bytes | INTEGER | NO | observed size |
| mtime_epoch | REAL | YES | observed mtime |
| hash_full | TEXT | YES | content hash |
| metadata_json | TEXT | YES | serialized enrichment payload |
| observed_at | DATETIME | NO | observation time |

Constraints:
- PK: `id`
- FK: `media_id` references `media(id)`
Indexes:
- `idx_files_media(media_id)`
- `idx_files_hash(hash_full)`
- `idx_files_observed_path(observed_path)`

#### `facts`
| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| id | INTEGER | NO | PK |
| run_id | INTEGER | YES | FK -> runs.id |
| fact_type | TEXT | NO | normalized event class |
| payload_json | TEXT | NO | immutable detail |
| created_at | DATETIME | NO | event timestamp |

Constraints:
- PK: `id`
Indexes:
- `idx_facts_run(run_id)`
- `idx_facts_type(fact_type)`

#### `intents`
| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| id | INTEGER | NO | PK |
| run_id | INTEGER | NO | FK -> runs.id |
| operation | TEXT | NO | organize_gallery/archive_duplicates/etc |
| config_hash | TEXT | NO | resolved config fingerprint |
| planner_version | TEXT | NO | planner code version |
| created_at | DATETIME | NO | timestamp |

Constraints:
- PK: `id`
- FK: `run_id` references `runs(id)`
- Unique: `(run_id, operation)`
Indexes:
- `idx_intents_run(run_id)`

#### `runs`
| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| id | INTEGER | NO | PK |
| run_uuid | TEXT | NO | stable external ID |
| operation | TEXT | NO | run operation |
| plan_version | TEXT | NO | plan format/version |
| planner_hash | TEXT | NO | planner code hash |
| config_hash | TEXT | NO | resolved config hash |
| state | TEXT | NO | run_state enum |
| drift_checksum | TEXT | YES | planner drift fingerprint |
| started_at | DATETIME | NO | created/start time |
| updated_at | DATETIME | NO | heartbeat/transition time |
| completed_at | DATETIME | YES | terminal completion timestamp |

Constraints:
- PK: `id`
- Unique: `run_uuid`
Indexes:
- `idx_runs_state(state)`
- `idx_runs_operation_state(operation, state)`

#### `planned_actions`
| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| id | INTEGER | NO | PK |
| run_id | INTEGER | NO | FK -> runs.id |
| file_id | INTEGER | NO | FK -> files.id |
| operation | TEXT | NO | business intent |
| action | TEXT | NO | primitive action enum |
| priority | INTEGER | NO | deterministic execution priority |
| src_path | TEXT | NO | expected source |
| target_path | TEXT | YES | expected destination |
| state | TEXT | NO | planned_action_state enum |
| idempotency_key | TEXT | NO | deterministic hash key |
| lock_owner | TEXT | YES | worker identity |
| lock_acquired_at | DATETIME | YES | lease boundary |
| lease_expires_at | DATETIME | YES | stale lock detection |
| attempt_count | INTEGER | NO | defaults 0 |
| reason | TEXT | YES | rationale |
| created_at | DATETIME | NO | timestamp |
| updated_at | DATETIME | NO | transition timestamp |

Constraints:
- PK: `id`
- FK: `run_id` references `runs(id)`
- FK: `file_id` references `files(id)`
- Unique: `(run_id, idempotency_key)`
Indexes:
- `idx_pa_run_state(run_id, state)`
- `idx_pa_lock(lease_expires_at, state)`
- `idx_pa_priority(run_id, priority, id)`

Idempotency key rule:
- deterministic digest over `{operation, action, file_id, src_path, target_path, plan_version}`

#### `file_actions`
| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| id | INTEGER | NO | PK |
| run_id | INTEGER | NO | FK -> runs.id |
| planned_action_id | INTEGER | NO | FK -> planned_actions.id |
| file_id | INTEGER | NO | FK -> files.id |
| action | TEXT | NO | primitive action |
| operation | TEXT | NO | business intent |
| outcome_kind | TEXT | NO | success/failure |
| src_path | TEXT | YES | observed source |
| target_path | TEXT | YES | observed destination |
| details_json | TEXT | YES | immutable context |
| created_at | DATETIME | NO | append timestamp |

Constraints:
- PK: `id`
- Unique: `(run_id, planned_action_id, outcome_kind)`
Indexes:
- `idx_fa_run(run_id)`
- `idx_fa_planned_action(planned_action_id)`

#### `failure_events`
| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| id | INTEGER | NO | PK |
| run_id | INTEGER | YES | FK -> runs.id |
| planned_action_id | INTEGER | YES | FK -> planned_actions.id |
| file_id | INTEGER | YES | FK -> files.id |
| phase | TEXT | NO | planner/apply/reconcile/transition |
| reason_code | TEXT | NO | normalized failure code |
| error_message | TEXT | YES | human-readable message |
| context_json | TEXT | YES | structured context |
| created_at | DATETIME | NO | timestamp |

Constraints:
- PK: `id`
Indexes:
- `idx_fe_run(run_id, created_at)`
- `idx_fe_reason(reason_code)`
- `idx_fe_action(planned_action_id)`

### 3.4 Gating Rules
- `PLANNED -> APPLYING` allowed only when schema check passes and run has eligible planned actions.
- `PENDING -> LOCKED -> EXECUTING` must be durably committed before filesystem mutation.
- If DB write fails at any critical boundary, no filesystem operation may execute.

### 3.5 Resume, Partial Execution, Drift, Reconciliation
Resume:
- Allowed only via `FAILED -> APPLYING` on same `run_id`.
- Eligible actions: `PENDING`, `FAILED`, `LOCKED` with expired lease, `EXECUTING` with expired lease.

Partial execution detection:
- `EXECUTING` + expired lease indicates interrupted action.
- Reconciliation runs before any re-execution.

Drift detection:
- Compare DB-projected effective path vs filesystem observation.
- Record `failure_events.reason_code='DRIFT_DETECTED'`.

Deterministic reconciliation classes:
- `already_applied`
- `not_applied`
- `conflict`
- `missing_source`
- `unexpected_target`

No silent correction; every reconciliation outcome appends durable facts/events.

## 4. Planning Engine

### Inputs
- canonical DB state
- resolved config snapshot
- operation parameters
- planner version/hash

### Determinism Guarantees
- stable sort by deterministic keys
- deterministic idempotency key generation
- identical inputs produce identical `planned_actions`

### Plan Versioning
- `runs.plan_version` and `planned_actions` encode version context
- planner hash and config hash persisted for replayability

### Invalidation Rules
Plan invalid if any change in:
- schema version
- config hash
- drift checksum
- planner version/hash

Invalid plan behavior:
- append failure event (`PLAN_INVALIDATED`)
- block apply until replan

### Purity Contract
Planner may write only:
- `runs`
- `intents`
- `planned_actions`

Planner must not:
- mutate filesystem
- write `file_actions`

## 5. Apply Engine

### Ordering
Deterministic queue order:
- `(priority, created_at, planned_action_id)`

### Locking
- one run-level apply lock
- per-action lease locks
- stale lease recovery is deterministic

### DB Gating Rule
Action execution boundary:
1. transition to `LOCKED`
2. transition to `EXECUTING`
3. commit
4. only then attempt filesystem operation

### Failure Semantics
If DB write fails:
- no filesystem mutation
- run transitions to `FAILED`
- append `failure_event` (`DB_GATING_FAILURE` or specific reason)
- resume requires deterministic reconciliation

If filesystem op fails:
- append `failure_event` (`FILESYSTEM_OP_FAILURE`)
- mark action `FAILED`
- run remains `APPLYING` unless failure ratio threshold exceeded, then `FAILED`

### Abort Conditions
- invalid transition
- schema mismatch
- unresolved collisions
- lock ownership loss
- failure ratio threshold exceeded

### Idempotency Enforcement
- unique `(run_id, idempotency_key)` on planned actions
- unique `(run_id, planned_action_id, outcome_kind)` on file actions
- resume re-evaluates action class before any retry

### Concurrency Boundaries
- single writer authority for run state transitions
- worker pool bounded by guardrail `max_apply_workers`
- each action requires exclusive lease ownership

## 6. Operational Guardrails
Canonical limits and policies are owned by:
- `06-operational-guardrails.md`

This section is normative summary only:
- no implicit retries
- dry-run no filesystem mutation
- safe mode read-only
- stop-the-line enforced before and during apply
- backpressure pauses lock acquisition on threshold breach

## 7. Testing Strategy

### Required Test Classes
- idempotency tests
- resume tests
- crash interruption tests
- drift detection and reconciliation tests
- schema and transition constraint tests
- DB/FS failure injection tests
- chaos tests for interrupted apply

### Quantitative Targets
- planning throughput: `>= 2,000 planned_actions/sec` on 10k synthetic set
- apply throughput: `>= 100 ops/sec` on baseline local SSD synthetic run
- max recoverable failure ratio: `<= 20%` without invariant violation
- max resume recovery time: `<= 5 minutes` on 10k synthetic dataset
- drift hard-fail threshold default: `>= 1%`

### CI Gates
- invariant suite failures block merge
- deterministic plan snapshot drift requires explicit approval note

## 8. Deployment and Migration Strategy

### Migration Rules
- forward-only migrations
- enum changes require transition mapping + backfill script
- schema compatibility statement required per migration

### Backward Compatibility
- reporting paths target N-1 read compatibility
- apply path requires exact schema compatibility

### Safe Rollout
- dry-run full library
- apply subset canary
- staged expansion after gates pass

### Rollback Philosophy
- do not delete facts
- roll forward with compensating facts and reconciliation runs

## 9. Documentation Restructure Plan

### Canonical Ownership
- `00-charter.md`: intent and business framing
- `01-roadmap.md`: narrative sequencing only
- `02-milestones.md`: milestone source of truth
- `03-test-strategy.md`: test taxonomy and references
- `04-risk-register.md`: risk inventory
- `05-release-plan.md`: rollout sequencing
- `06-operational-guardrails.md`: canonical runtime guardrails
- `07-unified-architecture-spec.md`: canonical technical execution contract

### Duplication Elimination Rules
- no guardrail defaults outside `06`
- no milestone duplication outside `02`
- schema and state semantics only in `07`

## AGENTS Checklist Compliance Mapping
- No FS mutation outside apply engine: enforced by planner/apply contracts and tests.
- Crash/retry/resume behavior: explicit in resume and failure semantics.
- State transition validation: strict transition matrix with hard failure on invalid moves.
- Idempotency: deterministic keys + unique constraints + replay tests.
- Failure events: mandatory append in all error paths.
- No dual sources of truth: canonical ownership map enforced in docs.
- Documentation updates: authority tables included across project docs.
