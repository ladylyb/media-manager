# Release Plan

| Document Authority | Scope |
| --- | --- |
| Authoritative for | Rollout sequence, canary stages, release gates |
| Not authoritative for | Guardrail defaults, schema/state contracts, milestone definitions |
| Canonical references | `02-milestones.md`, `06-operational-guardrails.md`, `07-unified-architecture-spec.md` |

## Release Strategy

### Phase 1 — Refactor-in-place (CLI only)
- Stabilize core, persistence contract, and planner/apply engine.
- No UI delivery in this phase.

### Phase 2 — Harden + Scale
- Golden fixtures, performance harness, chaos/recovery validation.
- Canary progression: 100 -> 1,000 -> 10,000.

### Phase 3 — API Layer
- Thin API exposing run/plan/apply/report surfaces.
- API may not bypass engine guards.

### Phase 4 — UI
- Review, approval, apply progress, audit navigation.

## Rollout Gates (Must Pass Before Promotion)
- deterministic planning snapshots stable
- state-machine transition tests pass
- DB-gating failure injection passes (no FS mutation)
- crash/resume test passes for interrupted apply
- drift detection/reconciliation checks pass

## Rollback Philosophy
- No destructive rollback of facts.
- Roll forward with compensating facts and reconciliation runs.

## References
- Operational limits and stop-the-line policy: `06-operational-guardrails.md`
- Milestone commitments and DoD: `02-milestones.md`
- Canonical technical contract: `07-unified-architecture-spec.md`
