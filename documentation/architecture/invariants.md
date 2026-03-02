# Invariants

These invariants are mandatory for all changes to this system:

1. No filesystem mutation without durable DB gating.
2. All apply operations are restart-safe.
3. All operations are idempotent.
4. Planning has zero side effects.
5. Apply consumes planned state only.
6. State transitions are explicit and validated.
7. Drift is detectable and observable.
8. Failure produces durable facts.

Primary source: repository root `AGENTS.md`.
