# Redefined Roadmap: Phases 7-12

## Current State (After Redefined Phase 6)

Completed foundation:
- Metadata extraction backbone
- Planner integration
- Deterministic logging
- Cache with metrics
- Benchmark harness
- SQL tuning guide
- Tests and instrumentation
- Repeatable performance measurement

## Short Notes for Completed Phases (1-6)

1. Phase 1: Established the extraction and data-shaping baseline needed for consistent downstream behavior.
2. Phase 2: Integrated planner flow so decision-making moved into explicit, repeatable planning paths.
3. Phase 3: Added deterministic logging to make run behavior explainable and comparable across retries.
4. Phase 4: Introduced cache and metrics to reduce repeated work and expose performance characteristics.
5. Phase 5: Added benchmark harness and SQL tuning guidance to support measured optimization.
6. Phase 6: Closed the loop with tests, instrumentation, and repeatable performance measurement workflows.

## Disciplined Sequence

```
Phase 7  -> Identity and ingestion separation
Phase 8  -> Planner and apply hardening
Phase 8.1 -> Canonical policy governance (deterministic abstraction)
Phase 9  -> Performance governance (SLAs and regression guard)
Phase 10 -> Scaling optimizations (materialized view)
Phase 11 -> Observability integration
Phase 12 -> GUI and tagging layer
```

## Phase 7 - Identity and Ingestion Architecture

Theme: separate identity from planning.
Goal: make the system replay-safe and duplicate-aware.

Deliverables:
1. Introduce `file_contents` (unique SHA256) and `file_instances` (physical copies).
2. Move hashing out of `plan` and create an `ingest` command.
3. Define a deterministic canonical selection policy.
4. Guarantee idempotent re-runs (re-ingesting same path does not duplicate logical content).

Why now:
- The system is still scan-driven. This phase upgrades it into a content identity platform.

## Phase 8 - Planner Hardening and Apply Integrity

Theme: deterministic, safe, auditable execution.

Deliverables:
1. Enforce missing-metadata policy (required vs optional codes) with structured warnings.
2. Define collision strategy for target-path conflicts and duplicate naming.
3. Add post-apply verification and per-apply audit log entries.
4. Add end-to-end deterministic tests on a medium real dataset.

Why after Phase 7:
- Planner correctness depends on stable identity modeling.

## Phase 9 - Performance Governance

Theme: prevent regression, not just measure it.

Deliverables:
1. Define SLAs for planner runtime, cache hit ratio, and DB lookup envelope.
2. Add regression guard against baseline JSON artifacts (fail if >20% regression).
3. Add lightweight CI performance check (1k dataset).
4. Tune batch size empirically.

Why here:
- Governance is only valuable after domain architecture is stable.

## Phase 8.1 - Canonical Policy Governance

Theme: deterministic canonical selection abstraction with explicit evolution controls.

Deliverables:
1. Introduce `CanonicalPolicy` interface with `select` and structured `explain`.
2. Keep `FIRST_SEEN v1` as default behavior (no behavioral drift).
3. Add `PREFER_ROOT v1` with deterministic fallback to FIRST_SEEN.
4. Add policy factory/config mapping and determinism tests.
5. Add duplicate visibility output with explain support.

Guardrail:
- No silent recanonicalization of existing content when policy config changes.
- Any recanonicalization must be explicit (deferred to Phase 8.2+).

## Phase 10 - Scaling and Materialization Strategy

Theme: optimize read patterns for large libraries.

Deliverables:
1. Add optional materialized view `mv_canonical_metadata`.
2. Define refresh strategy (scheduled vs trigger-based).
3. Compare planner query cost (indexed tables vs MV).
4. Add optional in-memory cache layer only if needed.

Important:
- This phase is scale optimization, not a prerequisite for correctness.

## Phase 11 - Observability and Telemetry

Theme: production visibility.

Deliverables:
1. Prometheus metrics integration.
2. Planner duration histograms.
3. Cache hit ratio gauge.
4. Structured ingestion metrics.

## Phase 12 - GUI and Tagging Layer

Theme: user-facing evolution after backend stabilization.

Deliverables:
1. Tag editing workflow.
2. Metadata editing support.
3. Planner integration with user-defined tags.
4. Fast read layer for UI interactions (MV can support this).
