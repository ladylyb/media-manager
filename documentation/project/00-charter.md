# Project Charter — Media Manager Rewrite

| Document Authority | Scope |
| --- | --- |
| Authoritative for | Problem framing, goals, non-goals, high-level invariants, success criteria |
| Not authoritative for | Canonical schema, state transition mechanics, apply failure semantics, operational limits |
| Canonical technical source | `documentation/project/07-unified-architecture-spec.md` |

## Purpose
Rewrite the legacy Python + SQLite media-manager scripts into a coherent, safe, and scalable application with an audit-first execution model. The system must support large libraries (10k+ files) without losing lineage or creating partial, unrecoverable states.

## Problem Statement
The legacy system worked on small samples but failed at scale due to:
- schema drift between code and database (mismatched columns / CHECK constraints)
- filesystem operations occurring when audit writes failed
- inconsistent current-path logic (`files.path` vs action-derived path)

This created partial execution and unreliable state.

## Goals (Must Achieve)
1. Safety by default.
2. Idempotent and resumable execution.
3. Audit-first lineage.
4. Measured scale.
5. Separation of concerns.

## Non-Goals (Explicitly Out)
- Full catalog UI parity with PhotoPrism/Jellyfin.
- Replacing media server product features.
- Automatic physical delete in initial phases.
- ML near-duplicate matching in first release.

## Non-Negotiable Invariants
- Plan -> Apply -> Record Outcome is mandatory.
- Database is authoritative; filesystem is a projection.
- Facts are append-only.
- Schema/version gate blocks incompatible execution.
- No silent overwrite.

## Scope (Initial Releases)
Phase 1: Engine + CLI (scan -> enrich -> plan -> apply -> report)
Phase 2: Duplicate workflow
Phase 3: API/UI

## Success Metrics
- Zero unaudited filesystem mutations during apply.
- Resume works after interruption.
- Organize-gallery apply has <1% explainable failures on 10k synthetic dataset.
- Run report includes planned/applied/failed/skipped counts and reasons.

## Key Risks and Controls
- Data loss: no-overwrite policy, collision controls, quarantine, stop-the-line.
- Schema drift: migrations + strict schema gate.
- Path drift: canonical effective-path resolver/view.
- Performance drift: indexes, batching, benchmarks.

## Deliverables
- Versioned schema + migrations + canonical views.
- Engine library + CLI/API.
- Test harness (unit/integration/regression/scale).
- Run reports and audit explorer (UI later).

## Decision Record
- Default branch: `develop`
- Legacy baseline tag: `v0-legacy-scripts-final`
- Primitive action vocabulary remains stable (`move`, `rename`, `delete`, `keep`, `ignore`); business intent belongs to `operation`.
