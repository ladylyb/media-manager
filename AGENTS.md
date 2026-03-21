# AGENTS.md

This file is the single source of truth for agent operating instructions in this repository.

## Scoped Instructions

- `documentation/LOCAL_INSTRUCTIONS.md`
  - Scope: `documentation/` folder only.
  - Purpose: documentation-specific handling notes.
  - Precedence: this root `AGENTS.md` remains authoritative if any conflict exists.

## Contribution Workflow

- `CONTRIBUTING.md`
  - Scope: human and agent contribution process (branching, PR, review, merge).
  - Purpose: operational workflow guidance.
  - Precedence: this root `AGENTS.md` remains authoritative for runtime invariants and safety constraints.

## Branch Safety Guard

Before making any repository file change, agents must run:

1. `git rev-parse --abbrev-ref HEAD`
2. `git status --porcelain`

Rules:

- If the current branch is `develop`, do not edit files.
- If the current branch is `develop` and `git status --porcelain` is non-empty, warn that there are uncommitted changes on `develop` and stop.
- Require creating or switching to a non-protected branch before any edit.
- Allowed edit branches are `feature/*`, `fix/*`, `docs/*`, and `chore/*`.
- Do not commit directly to `develop` even if the worktree is clean.

---

This repository is developed using agent-driven workflows.

Agents are expected to read this file before proposing or applying changes.

This system is a failure-sensitive, stateful media management engine.
It is not a CRUD app. It is not a scripting playground.
Every change must respect runtime invariants.

---

# 1. Core System Invariants

These must NEVER be violated:

1. No filesystem mutation occurs without durable DB gating.
2. All apply operations must be restart-safe.
3. All operations must be idempotent.
4. Planning produces zero side effects.
5. Apply never invents state; it consumes planned state.
6. State transitions must be explicit and validated.
7. Drift must be detectable and observable.
8. Failure must produce durable facts.

If a proposed change weakens any invariant, it is invalid.

---

# 2. Architectural Model

The system is composed of:

- Planner
- Apply Engine
- Canonical Persistence Layer
- Drift Detection
- Failure Logging
- Run Lifecycle Controller

Agents may modify components only if they understand:

- Intent vs Fact separation
- Planned Action vs File Action distinction
- Run lifecycle semantics
- Resume semantics
- Schema gating

If uncertain, inspect schema definitions before proposing logic changes.

---

# 3. Change Discipline

Agents must follow this order:

1. Read schema definitions.
2. Read state transition rules.
3. Identify invariants impacted.
4. Propose change.
5. Define failure semantics.
6. Define idempotency behavior.
7. Define resume behavior.

No change is complete without specifying:

- What happens on crash?
- What happens on retry?
- What happens on partial completion?

---

# 4. Planning Rules

Planner:
- Is pure.
- Reads durable state.
- Emits planned_actions.
- Must be deterministic for identical inputs.
- Must not write filesystem.
- Must not mutate file_actions.

Planner output must be reproducible.

If adding a new action type:
- Define canonical shape.
- Define idempotency key.
- Define validation rules.

---

# 5. Apply Rules

Apply:
- Consumes planned_actions.
- Creates file_actions.
- Performs filesystem mutation only after DB gating.
- Must append failure_events on any error.
- Must abort run on DB write failure.

Strict rule:
If DB write fails, NO filesystem operation may execute.

Resume contract:
- A run may resume only from a durable state boundary.
- Partially completed file_actions must be detectable.
- No action may execute twice unless idempotent by design.

---

# 6. Schema Modifications

Schema changes require:

- Explicit migration plan.
- Backward compatibility statement.
- State transition updates.
- Resume safety validation.
- Drift implications analysis.

Never:
- Remove a column used in gating.
- Change enum values without transition mapping.
- Introduce nullable state columns without invariant review.

---

# 7. Testing Expectations

Any non-trivial change must include:

- Idempotency test
- Resume test
- Failure injection test
- Drift detection test (if applicable)

Tests must validate:

- Crash safety
- Partial execution recovery
- Deterministic planning

---

# 8. Observability

All long-running operations must:

- Emit structured logs
- Record run_id
- Record action_id
- Record timestamps
- Record outcome

No silent failure.
No implicit retries.

---

# 9. Forbidden Patterns

Agents must not:

- Introduce hidden side effects
- Perform filesystem ops outside apply engine
- Mutate durable state inside planner
- Add implicit retries
- Swallow exceptions
- Introduce dual sources of truth

---

# 10. When Unsure

If ambiguity exists:

- Do not guess.
- Do not "simplify".
- Propose clarification instead of implementation.

This system prioritizes safety and determinism over convenience.
