# Architecture Guardrails

This system is designed around failure-driven engineering.

Principles:

- Make invalid states unrepresentable.
- Make state transitions explicit.
- Make crashes survivable.
- Make drift visible.
- Prefer append-only facts to mutation.
- Prefer deterministic replay over correction logic.
- Favor explicit state machines over boolean flags.

Operational Model:

- Planner is pure.
- Apply is effectful.
- DB is source of truth.
- Filesystem is projection of truth.
- Failure produces facts.
- Facts are immutable.

Complexity is allowed in planning.
Ambiguity is not allowed in apply.