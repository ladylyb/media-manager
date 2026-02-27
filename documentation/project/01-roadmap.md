# Roadmap (Narrative)

| Document Authority | Scope |
| --- | --- |
| Authoritative for | Phase narrative, dependency storyline, sequencing rationale |
| Not authoritative for | Milestone definitions, schema/state contracts, guardrail defaults |
| Canonical references | `02-milestones.md`, `06-operational-guardrails.md`, `07-unified-architecture-spec.md` |

## Purpose
This roadmap explains delivery flow and rationale. Detailed milestone requirements are owned by `02-milestones.md`.

## Phase Narrative

### Phase A: Safety Foundation
Establish read-only defaults, stop-the-line checks, and deterministic reporting before effectful execution.

### Phase B: Contracted Persistence and State
Introduce strict schema versioning, canonical state views, and state-machine enforcement so invalid states are rejected.

### Phase C: Deterministic Planning
Ship a pure planner that produces reproducible `planned_actions` under a run boundary with explicit invalidation rules.

### Phase D: Restart-Safe Apply
Implement gated apply with durable lock/state boundaries, failure event append rules, and deterministic resume/reconciliation.

### Phase E: Dedupe + Hardening
Move duplicate/canonical workflows into the same plan/apply contract. Add regression harnesses and scale benchmarks.

### Phase F: API and UI Enablement
Expose engine behavior through thin API and then UI, without bypassing engine invariants.

## Dependency Map
- Safety Foundation -> Contracted Persistence -> Planning -> Apply -> Dedupe Hardening -> API -> UI
- No downstream phase may start if upstream invariant tests fail.

## Release Progression
- Canary 100 -> 1,000 -> 10,000 files.
- Expansion only after deterministic-plan stability, resume safety, and drift checks pass.

## Out of Scope for this Document
- Table-level schema details.
- Runtime state transition mechanics.
- Operational thresholds and retry/timeout policy.
