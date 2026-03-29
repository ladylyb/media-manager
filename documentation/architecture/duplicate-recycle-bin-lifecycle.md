# Duplicate Recycle Bin Lifecycle Simplification

## Status

Approved direction for future slices. This document defines the target duplicate-removal architecture, but the full migration has not been implemented yet.

## Context / Problem

The current duplicate-removal architecture is over-modeled for the intended operator experience. The product wants one clear Recycle Bin concept, but the implementation currently distinguishes:

- a duplicate reclaim holding stage
- a later recycle-bin stage
- a later purge stage

That split creates translation cost between product language and backend behavior. `reclaim` is not intuitive operator language, and the `reclaim -> recycle_bin -> purge` lifecycle makes the duplicate workflow harder to explain, harder to trust, and more error-prone than the operator mental model requires.

The target operator story is simpler:

1. Review duplicates
2. Mark a group `Looks right`
3. Move extra copies to the Recycle Bin
4. Restore before expiry if needed
5. Delete later after retention

The system should converge toward an architecture that matches that story directly.

## Current Implementation Truth

Current implementation behavior must be acknowledged explicitly:

- The Duplicates-page move flow currently uses the duplicate reclaim / holding-stage implementation.
- The planner/apply path performs real file movement into the current duplicate reclaim holding root.
- Restore currently restores from that same holding stage.
- Later recycle and purge operations exist separately as downstream retention workflows.
- `SAFE_TO_RECLAIM` / `REVIEWED_SAFE_TO_RECLAIM` and reclaim statuses still exist internally.
- The operator-facing UI language has already shifted toward `Recycle Bin`, but the backend architecture has not been fully simplified to match.
- Persisted policy exists, and current runtime resolves env-backed storage settings through `PolicySettingsService` precedence rather than reading raw `.env` values directly at the move/restore call site.
- Planner/apply remains the only place where filesystem mutation occurs, and that invariant must be preserved through any migration.

In practice, this means the current backend is more complex than the operator model. The current reclaim stage is the effective first-stage Recycle Bin today, while the later recycle/purge stage remains an internal downstream lifecycle.

## Product Goals

The approved duplicate-removal product model is:

1. Review duplicates
2. Mark group `Looks right`
3. Move extra copies to Recycle Bin
4. Restore before expiry if needed
5. Delete later after retention

Key product rules:

- `Looks right` means the group is genuinely duplicate.
- Only extra copies move.
- The keep copy never moves in this workflow.
- Restore is available only before expiry.
- Expiry blocks restore in the GUI.
- Deletion may remain manual/run-based for now.

## Decision / Target Architecture

Media Manager should converge toward a single duplicate Recycle Bin lifecycle.

This means:

- the current reclaim stage is transitional implementation debt, not the target domain concept
- reclaim concepts may remain internally during migration, but they should not remain the long-term product or architectural direction
- operator-facing UX, docs, and help text should use Recycle Bin language only
- the current reclaim stage should be treated as the effective first-stage Recycle Bin until migration completes
- the later recycle/purge stage remains downstream and internal until the lifecycle is simplified

The target direction is not a big-bang rewrite. It is a staged convergence from the current reclaim/recycle split toward one duplicate-removal lifecycle that matches the product model.

## Lifecycle / State Model

Review state remains separate from duplicate bin-item lifecycle.

Move eligibility should initially remain derived from review state and later business/integrity constraints rather than becoming a heavily persisted operator-facing lifecycle state. In particular, `READY_FOR_BIN` should be treated as derived eligibility, not a required new durable enum at this stage.

The target conceptual duplicate bin lifecycle is:

- `IN_BIN`
- `EXPIRED_IN_BIN`
- `RESTORED`
- `PURGED`

Interpretation:

- `IN_BIN`: extra copy is in the Recycle Bin and may still be restored
- `EXPIRED_IN_BIN`: extra copy remains visible but is no longer restorable in the GUI
- `RESTORED`: extra copy has been moved back to its original path
- `PURGED`: extra copy has been deleted as the final state

Additional rule:

- restored groups do not automatically re-enter move eligibility unless they are reviewed again

## Storage And Config Model

Long-term target:

- one duplicate-removal root: `MEDIA_MANAGER_RECYCLE_BIN_ROOT`
- current `MEDIA_MANAGER_RECLAIM_ROOT` is legacy/transitional
- duplicate restore window remains policy-backed

Storage guidance:

- mirrored path layout under the recycle root is acceptable for usability
- durable metadata must remain the source of truth for restore
- original path must remain persisted
- restore must never rely solely on mirrored folder structure

This means any future mirrored-path implementation is a storage convenience, not the authoritative restore mechanism.

## Restore / Expiry Contract

Restore means:

- moving the file from the bin back to its original path
- marking the item restored
- removing the item from active duplicate bin surfaces

Restore is allowed only before expiry.

After expiry:

- the item remains visible
- the item is not restorable in the GUI
- the item remains pending later deletion/purge

Deletion may remain manual/run-based in later retention operations. Automatic deletion is not required by this direction.

## Current-To-Target Mapping

The following mappings define the migration direction. They are conceptual mappings only and do not imply that schema or status names have already changed.

| Current concept | Target meaning |
| --- | --- |
| `REVIEWED_SAFE_TO_RECLAIM` | Derived duplicate bin eligibility / transitional internal readiness |
| `ARCHIVED` | `IN_BIN` |
| `SCHEDULED_FOR_DELETE` | `EXPIRED_IN_BIN` or later purge-eligible state |
| `RESTORED` | `RESTORED` |
| reclaim archive root | Transitional physical implementation of the Recycle Bin |
| recycle bin root | Target long-term duplicate bin root |

Additional interpretation:

- current reclaim item rows are the closest existing durable facts for future duplicate bin items
- current recycle/purge workflow is an internal downstream stage, not the long-term primary product concept

## Migration Strategy

Migration should be staged, not big-bang.

### Phase 1: Conceptual / Product Alignment

- use Recycle Bin language only in product-facing surfaces
- stop introducing new reclaim concepts
- document reclaim as legacy/transitional

### Phase 2: Service-Layer Compatibility Abstraction

- introduce duplicate bin terminology at service/API boundaries
- keep legacy reclaim implementation behind compatibility shims initially
- preserve planner/apply as the only place where filesystem mutation occurs

### Phase 3: Path / Config Migration

- move duplicate-removal target toward `MEDIA_MANAGER_RECYCLE_BIN_ROOT`
- keep restore compatible during transition
- treat `MEDIA_MANAGER_RECLAIM_ROOT` as legacy/transitional while compatibility remains in place

### Phase 4: Data / Status Migration

- backfill or rename persisted paths and status mappings as needed
- support compatibility reads during transition
- keep existing moved items and restore behavior valid while old and new representations coexist

### Phase 5: Legacy Reclaim Retirement

- retire `MEDIA_MANAGER_RECLAIM_ROOT`
- retire active reclaim naming in duplicate-removal paths
- remove legacy reclaim-first assumptions once the single-bin lifecycle is fully in place

Schema and table renames should be deferred until compatibility layers exist and migration safety is understood.

## Risks / Tradeoffs

Main risks of simplification:

- path migration for already-moved files
- restore correctness during transition
- dual-read logic while legacy and target shapes coexist
- preserving planner/apply invariants, idempotency, and resume safety

Main tradeoff:

- keeping the current architecture avoids migration work in the short term, but it preserves operator confusion, terminology drift, and architectural misalignment with the intended product

## What Changes Now Vs Later

### Change Now

- docs, comments, help text, and architecture alignment
- product language and planning direction
- stop adding new reclaim terminology

### Defer

- backend renames
- schema/table renames
- full data migration
- collapse of all legacy statuses
- duplicate-to-integrity decisioning

## Open Questions / Deferred Items

- whether recycle-bin mirroring should preserve full relative path or use a scoped path scheme
- exact final duplicate item schema shape after the compatibility period
- how expired-but-not-yet-purged items should be surfaced in the GUI
- whether duplicate retention should remain policy-backed or gain an intentional env override later
