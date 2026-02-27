# Milestones

| Document Authority | Scope |
| --- | --- |
| Authoritative for | Milestone definitions, dependencies, deliverables, DoD |
| Not authoritative for | Canonical schema semantics, guardrail limits, release gates |
| Canonical references | `06-operational-guardrails.md`, `07-unified-architecture-spec.md` |
## Milestones (10)

> Guiding rule (applies to all milestones):
> - **Actions are stable primitives**: `move`, `rename`, `delete`, `keep`, `ignore`
> - **Business intent is an operation**: e.g. `organize_gallery`, `archive_duplicates`, `canonicalize`
> - **Plans are intent** (tracked in `planned_actions`)
> - **Facts are immutable** (recorded in `file_actions`)
> - **Plan → Apply → Record Outcome** is mandatory (no exceptions)

---

### Milestone 1 — Baseline & Safety Lockdown (S)

**Goal / Rationale:** Stop repeat damage. Establish a known-good baseline and prevent any accidental destructive execution until the engine is safe.

**Scope**
- **In:** repo structure, config conventions, “no apply” default, read-only mode tools
- **Out:** any new features, GUI work

**Deliverables**
- `documentation/project/SAFETY.md` (non-negotiables + stop-the-line rules)
- Unified config file format (YAML/TOML) and environment strategy
- Read-only `inventory` / `report` command (DB + filesystem reads only)
- Repo hygiene: formatting, linting, and pre-commit hooks

**Dependencies:** none

**Definition of Done**
- Running any command without explicit `--apply` performs **no filesystem writes**
- A single config controls roots, excludes, and output directories
- A “baseline run report” can be generated on the existing library without changes
- “Stop-the-line” checks exist and are enforced in the CLI entrypoint

---

### Milestone 2 — Data Model Alignment + Schema Versioning (M)

**Goal / Rationale:** Prevent the exact failure you hit: code and DB disagreeing at scale (mismatched columns, CHECK constraints, missing values).

**Scope**
- **In:** schema versioning, migrations, stable action vocabulary, effective-path view, plan tables
- **Out:** Postgres migration execution (design only here)

**Deliverables**
- DB migration framework (Alembic or lightweight SQL migrations)
- `schema_version` table + startup check in **all** commands
- Canonical “current effective file state” view used by the engine (no direct use of stale `files.path`)
- Action model locked in schema and docs:
  - `action` is primitive only (`move`, `rename`, `delete`, `keep`, `ignore`)
  - `operation` carries intent (e.g., `organize_gallery`)
- **Planned actions table** (authoritative intent for a run), keyed by `run_id`
- Indexes for known hotspots (actions lookup, current state resolution, candidate group lookups)

**Dependencies:** Milestone 1

**Definition of Done**
- Every command refuses to run if schema version is behind
- The effective-path view exists and is used by engine code for “current path”
- Planned action schema supports status lifecycle (`planned`, `in_progress`, `applied`, `failed`, `skipped`)
- 1,000+ action rows can be queried efficiently (validated by timings / query plans)

---

### Milestone 3 — Core Domain Library Extraction (M)

**Goal / Rationale:** Stop using scripts as architecture. Create a coherent library with a single truth for rules, state derivation, and DB access.

**Scope**
- **In:** `mm_core` package, repository layer, path resolver, media classification utilities
- **Out:** changing business logic (keep behavior equivalent where practical)

**Deliverables**
- `mm_core/db.py` (connection + pragmas + transaction helpers)
- `mm_core/repo/` (files, actions, planned_actions, runs, candidates)
- `mm_core/state.py` (effective path resolver aligned to the DB view)
- `mm_core/types.py` (dataclasses / pydantic models)
- Unit tests for resolver and classification logic

**Dependencies:** Milestone 2

**Definition of Done**
- Scripts become thin wrappers calling library functions
- No direct SQL scattered across scripts except via repository layer
- Resolver and media classification utilities are unit tested
- Engine uses one canonical “effective path” source (view/resolver), consistently

---

### Milestone 4 — Planning Engine (Plan-Only) (M)

**Goal / Rationale:** Separate decisions from execution. Produce deterministic action plans without touching the filesystem.

**Scope**
- **In:** plan generation for `organize_gallery` (and scaffolding for rename/archive); collision detection; exports
- **Out:** applying moves/renames (next milestone)

**Deliverables**
- `mm plan organize-gallery` producing a plan set under a `run_id`
- `planned_actions` table populated with:
  - `run_id`, `file_id`, `operation`, `action`, `src_path`, `target_path`,
    `status='planned'`, `reason/rationale`, `collision_key` (as needed)
- CSV/JSON export of plan + rationale + collision report
- Deterministic target path rules (no silent overwrites, consistent suffix strategy reserved for apply)

**Dependencies:** Milestone 3

**Definition of Done**
- Planning works on the full library and produces a deterministic plan
- Collisions are detected and surfaced (no silent overwrites)
- Re-running planning yields identical results (given unchanged inputs)
- Planning never performs filesystem writes (enforced and tested)

---

### Milestone 5 — Apply Engine (Transactional + Recoverable) (L)

**Goal / Rationale:** Make filesystem operations safe at scale: resumable, audited, and failure-tolerant.

**Scope**
- **In:** apply moves/renames, atomic operations, checkpointing, retries, partial failure recovery
- **Out:** physical deletion (keep quarantined for later)

**Deliverables**
- `mm apply --run-id <id>` with:
  - per-action execution logging
  - status transitions in `planned_actions` (`planned → in_progress → applied/failed/skipped`)
  - deterministic collision resolution policy (suffixing/disambiguation) that is logged
- “resume run” support (continue where it left off)
- “reconcile filesystem vs DB” command (detect drift, report, and propose remediation)
- Immutable fact recording in `file_actions` for outcomes:
  - On success: append a `file_actions` row (primitive action + paths + notes)
  - On failure: append a `file_actions` row documenting failure outcome + error context

**Dependencies:** Milestone 4

**Definition of Done**
- **No apply without durable intent:** apply requires `planned_actions` for the run
- **DB gating:** if DB write fails at any critical step, filesystem op is not executed
- If filesystem op fails, the corresponding plan item is marked `failed` with error details
- You can interrupt and resume a 10k-file run without duplicating work
- A recovery report is produced automatically (counts + failure reasons + next steps)

---

### Milestone 6 — Duplicate Detection & Canonical Decision Refactor (M)

**Goal / Rationale:** Stabilize dedupe logic in the same plan/apply framework.

**Scope**
- **In:** candidate generation, scoring, canonical selection rules, review exports
- **Out:** near-duplicate perceptual similarity research (optional later)

**Deliverables**
- `mm dedupe plan` producing:
  - groups, scores, and proposed canonicals (deterministic)
  - planned actions for `archive_duplicates` and/or `canonicalize` as operation values
- Configurable scoring weights (documented and versioned)
- Regression fixtures capturing tricky cases (false positives/negatives)

**Dependencies:** Milestone 3–5

**Definition of Done**
- Dedupe results are reproducible on repeated runs
- Canonical rules are explicit and test-covered
- “Human review pack” export exists (CSV/HTML) with sufficient context for approval

---

### Milestone 7 — Golden Fixtures + Regression Harness (M)

**Goal / Rationale:** Lock behavior; stop “works on small sample” illusions.

**Scope**
- **In:** curated test media metadata (no personal files), synthetic trees, regression suite
- **Out:** full perceptual hashing research

**Deliverables**
- `tests/fixtures/` with synthetic trees + deterministic metadata stubs
- Snapshot tests for plans (expected `planned_actions`)
- Property tests for idempotency, collision rules, and resumability

**Dependencies:** Milestone 4–6

**Definition of Done**
- CI runs unit + integration + regression on every change
- Any plan/apply behavior change requires updating explicit expected outputs
- Idempotency and resume properties are tested (not assumed)

---

### Milestone 8 — Performance & Scale Hardening (M)

**Goal / Rationale:** Make 10k–100k plausible through measured improvements.

**Scope**
- **In:** batching, concurrency limits, hash strategy, DB indexes, incremental enrichment
- **Out:** distributed compute (overkill)

**Deliverables**
- Performance benchmark script (plan + apply + dedupe plan paths)
- 10k+ synthetic dataset generator + runbook
- Measured targets (throughput, DB latency, memory ceiling) documented and tracked

**Dependencies:** Milestone 5–7

**Definition of Done**
- End-to-end run (plan + apply) completes on 10k synthetic dataset within defined thresholds
- No O(N²) query patterns in hot paths (validated by profiling / query analysis)
- Observability clearly shows where time is spent and where bottlenecks are

---

### Milestone 9 — API Layer (Thin) (M)

**Goal / Rationale:** Enable GUI without re-implementing logic or allowing unsafe execution paths.

**Scope**
- **In:** API endpoints calling the core engine; auth optional initially
- **Out:** complex permissions and enterprise auth

**Deliverables**
- Endpoints for: runs, plans, actions, apply, reports
- OpenAPI spec as contract
- API enforces the same stop-the-line rules as CLI (no bypass)

**Dependencies:** Milestone 5–8

**Definition of Done**
- GUI could be built purely on API, no direct DB access required
- API refuses unsafe operations (schema mismatch, out-of-scope paths, unresolved collisions)
- Audit trail remains complete when actions are executed via API

---

### Milestone 10 — Next.js GUI (L)

**Goal / Rationale:** Human review + safe execution UI.

**Scope**
- **In:** review duplicates, review plans, approve/apply, progress, audit explorer
- **Out:** advanced media previews (later)

**Deliverables**
- Screens: Runs, Duplicates Review, Plan Preview, Apply/Progress, Audit Timeline
- “Download review pack” and “Download run report”
- Approval workflow: explicit confirmation required before apply

**Dependencies:** Milestone 9

**Definition of Done**
- No action can be executed from UI without explicit approval
- UI surfaces conflicts, mismatches, and failed actions clearly
- Full audit trail is navigable per file and per run



# Restart Point — Media Manager Rewrite

## Status Snapshot (as of this commit)
- Legacy codebase is **archived** and the baseline is preserved via tag:
  - `v0-legacy-scripts-final`
- Repo default branch is **main**; legacy `master` branch has been removed.
- Planning docs are now the single source of truth:
  - `00-charter.md`
  - `01-roadmap.md`
  - `02-milestones.md`
- Temporary planning notes file `99-delete-this.md` has been folded into the above docs and can be deleted.

## Locked Decisions (do not revisit casually)
### 1) Execution Model (non-negotiable)
- **Plan → Apply → Record Outcome** is mandatory.
- Dry-run by default; `--apply` must be explicit.
- Tool must refuse unsafe operations (“stop-the-line”).

### 2) Data Authority
- Database is authoritative; filesystem is a projection.
- Current effective path is derived via canonical view/resolver (not stale discovery paths).

### 3) Intent vs Facts (prevents legacy failure mode)
- `planned_actions` = intent for a specific run (`run_id`) + lifecycle status
  - statuses: `planned`, `in_progress`, `applied`, `failed`, `skipped`
- `file_actions` = immutable audit facts of what happened (append-only outcomes)
- Avoid “planned noise” in `file_actions`.

### 4) Action Semantics (stable primitives)
- `action` values are stable primitives only:
  - `move`, `rename`, `delete`, `keep`, `ignore`
- Business intent goes into `operation`:
  - e.g., `organize_gallery`, `archive_duplicates`, `canonicalize`
- Do not introduce `action='organize'` (prevents schema/constraint churn).

## What “Done” Means for the Next Milestone
### Next Milestone: M1 — Baseline & Safety Lockdown
Deliverables required before any schema refactor or apply logic:
- `SAFETY.md` with hard stop-the-line rules
- Unified config format (YAML/TOML) and conventions (roots, excludes, outputs)
- Read-only command(s) to generate an inventory + baseline report (no filesystem writes)
- Repo hygiene: formatter/linter, basic pre-commit hooks

Definition of Done (M1):
- Running any command without explicit `--apply` produces **zero filesystem writes**
- Baseline report can run on the real library safely (read-only)

## Parking Lot (explicitly deferred decisions)
These are intentionally not decided yet:
- SQLite-first vs Postgres-first execution order (Postgres is “later” per charter)
- Alembic vs lightweight SQL migrations approach (must exist by M2)
- Concurrency model for hashing/enrichment (address in Performance milestone)
- UI/API details (strictly later; no GUI work until engine is safe)

## Next Action When Returning
Start **Milestone 1 only**. Do not touch apply logic, UI, or dedupe until M1 DoD is met.

