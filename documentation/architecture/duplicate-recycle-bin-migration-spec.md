# Duplicate Recycle Bin Migration Spec

## Status

Implementation-ready planning/specification document. This spec defines the staged migration from the current reclaim-centered duplicate-removal implementation toward the approved Recycle Bin model. It does not introduce schema changes or runtime behavior changes by itself.

Related direction document: [Duplicate Recycle Bin Lifecycle Simplification](duplicate-recycle-bin-lifecycle.md).

## Current-State Inventory

Current duplicate-removal persistence remains reclaim-centered.

### Persisted record-level state

`DuplicateReclaimRecord` currently persists group-level duplicate-removal facts:

| Field | Current meaning |
| --- | --- |
| `content_id` | Duplicate group identifier |
| `reclaim_status` | Current reclaim workflow status for the group |
| `reviewed_at` / `reviewed_by` | Latest reclaim review sync metadata |
| `archive_path` | Compatibility path field whose meaning changes across lifecycle stages |
| `reclaimed_at` | Timestamp when reclaim archive or later recycle transition was persisted |
| `expires_at` | Current retention boundary associated with the latest persisted stage |
| `restored_at` | Timestamp when restore completed |

Current allowed `reclaim_status` values:

- `UNREVIEWED`
- `REVIEWED_SAFE_TO_RECLAIM`
- `ARCHIVED`
- `SCHEDULED_FOR_DELETE`
- `RESTORED`

### Persisted item-level state

`DuplicateReclaimItem` currently persists per-file duplicate-removal facts:

| Field | Current meaning |
| --- | --- |
| `file_instance_id` | Duplicate file instance identifier |
| `content_id` | Duplicate group identifier |
| `original_path` | Restore source-of-truth destination path |
| `archive_path` | Current reclaim-stage archived location |
| `item_status` | Current item lifecycle status in reclaim-centered implementation |
| `reclaimed_at` | Timestamp when archive completed |
| `expires_at` | Archive-stage retention expiry |
| `recycle_path` | Later recycle-bin-stage path after archive expiry |
| `recycled_at` | Timestamp when later recycle move completed |
| `purge_after_at` | Later purge eligibility boundary after recycle |
| `purged_at` | Timestamp when purge completed |
| `restored_at` | Timestamp when restore completed |

Current allowed `item_status` values:

- `PENDING`
- `ARCHIVED`
- `RESTORED`
- `RECYCLED`

### Current path behavior

Current duplicate-removal paths are stage-split:

| Stage | Current root | Current persisted path field | Current path shape |
| --- | --- | --- | --- |
| Initial duplicate move | `duplicate_reclaim_archive_root` | `DuplicateReclaimItem.archive_path` | `<reclaim_root>/<content_id>/<file_instance_id>-<basename>` |
| Later recycle after expiry | `recycle_bin_root` | `DuplicateReclaimItem.recycle_path` | `<recycle_root>/duplicates/<content_id>/<file_instance_id>-<archive basename>` |

Current record-level path behavior is more ambiguous:

- `DuplicateReclaimRecord.archive_path` points at the reclaim-stage archive location after `RECLAIM_ARCHIVE`
- the same field is later overwritten to point at `recycle_path` after `RECLAIM_RECYCLE`
- this means `DuplicateReclaimRecord.archive_path` does not have one stable physical meaning today

### Current restore and expiry behavior

- Duplicate move planning currently requires `REVIEWED_SAFE_TO_RECLAIM`.
- Restore currently plans from `DuplicateReclaimItem.archive_path` while the item remains in `ARCHIVED` state.
- Later recycle currently happens only after `DuplicateReclaimItem.expires_at`.
- Later purge currently happens only after `DuplicateReclaimItem.purge_after_at`.
- The Duplicates-page workflow already treats restore as available before expiry and blocked after expiry.
- Restored groups do not automatically become move-eligible again; a new review pass is required.

### Current policy/config values

The current duplicate-removal workflow depends on these persisted policy values:

| Policy/config value | Current role |
| --- | --- |
| `duplicate_reclaim_archive_root` | Current initial duplicate move root |
| `duplicate_reclaim_default_retention_days` | Current duplicate holding/restore window |
| `recycle_bin_root` | Current later recycle-stage root |
| `recycle_purge_days` | Current later purge warning/eligibility window |

Current service-layer compatibility helpers already expose bin-centered terminology:

- `duplicate_bin_execute(...)`
- `duplicate_bin_restore(...)`
- `duplicate_bin_items(...)`
- `duplicate_bin_policy_get()`

These remain compatibility entry points over reclaim-shaped persistence and read payloads.

## Target-State Inventory

The target duplicate-removal model is a single Recycle Bin lifecycle aligned with the approved RFC.

### Target conceptual states

The target conceptual duplicate bin item lifecycle is:

- `IN_BIN`
- `EXPIRED_IN_BIN`
- `RESTORED`
- `PURGED`

Interpretation:

- `IN_BIN`: duplicate extra copy is in the operator-facing Recycle Bin and may still be restored
- `EXPIRED_IN_BIN`: duplicate extra copy remains visible but restore is blocked in the GUI
- `RESTORED`: duplicate extra copy has been moved back to `original_path`
- `PURGED`: duplicate extra copy has been deleted in a later retention action

### Derived vs persisted target concepts

- `READY_FOR_BIN` remains a derived eligibility concept based on review state and other business constraints.
- `READY_FOR_BIN` must not be introduced as a durable persisted item lifecycle state unless a later concrete need appears.
- During migration, several reclaim-centered persisted states will continue to exist as compatibility representations even when service and product layers speak in bin-centered terms.

### Target path/config model

Long-term target:

- one primary duplicate-removal root centered on `MEDIA_MANAGER_RECYCLE_BIN_ROOT`
- one primary bin path per duplicate item
- `original_path` remains the authoritative restore destination
- path layout under the target root may mirror identifiers or source names for usability, but restore correctness must continue to depend on durable metadata rather than folder layout alone

### Target restore / expiry contract

- Restore is allowed before expiry.
- After expiry, the item remains visible but restore is blocked in the GUI.
- Expired items may remain physically present until a later manual/run-based purge action.
- Restored groups do not automatically re-enter duplicate move eligibility without a fresh review decision.

## State Mapping

These mappings are migration-time semantic interpretations. They do not claim that the current reclaim-centered architecture already means the same thing cleanly in every layer.

| Current field/state | Target semantic interpretation during migration | Persisted now / derived now | Target persisted / derived | Transition note |
| --- | --- | --- | --- | --- |
| `DuplicateReclaimRecord.reclaim_status = UNREVIEWED` | Not ready for duplicate bin move | Persisted now | Derived eligibility outcome | Remains review-layer input, not bin-item state |
| `DuplicateReclaimRecord.reclaim_status = REVIEWED_SAFE_TO_RECLAIM` | Closest current signal for `READY_FOR_BIN` | Persisted now | Derived only | Transitional compatibility only; do not persist `READY_FOR_BIN` |
| `DuplicateReclaimRecord.reclaim_status = ARCHIVED` | Closest current persisted signal for `IN_BIN` | Persisted now | Persisted item/bin state | Migration interpretation only; current code still treats this as reclaim archive stage |
| `DuplicateReclaimRecord.reclaim_status = SCHEDULED_FOR_DELETE` | Closest current persisted signal for `EXPIRED_IN_BIN` or purge-eligible downstream stage | Persisted now | Persisted expired/purge-eligible state | Interpretation remains approximate during mixed archive/recycle coexistence |
| `DuplicateReclaimRecord.reclaim_status = RESTORED` | Closest current persisted signal for `RESTORED` | Persisted now | Persisted restored state | Semantically aligned enough to preserve through migration |
| `DuplicateReclaimItem.item_status = PENDING` | Planned but not yet moved into bin | Persisted now | Transitional compatibility state | Keep as compatibility state until planner/apply migration is complete |
| `DuplicateReclaimItem.item_status = ARCHIVED` | Closest current persisted signal for `IN_BIN` | Persisted now | Persisted item/bin state | Migration interpretation only; current physical path is still reclaim-root-based |
| `DuplicateReclaimItem.item_status = RECYCLED` | Closest current persisted signal for expired/purge-window stage | Persisted now | Persisted expired/purge-eligible state | Transitional downstream stage, not final operator-facing concept |
| `DuplicateReclaimItem.item_status = RESTORED` | Closest current persisted signal for `RESTORED` | Persisted now | Persisted restored state | Preserve semantics, even if names change later |

Additional mapping rules:

- Review state and bin-item lifecycle remain separate concerns.
- Future schema work may collapse or rename persisted reclaim states, but this spec does not require that yet.
- No implementation slice should treat `ARCHIVED -> IN_BIN` as proof that all current APIs, fields, or paths already carry clean bin semantics.

## Path Mapping

### Current path model

Current duplicate-removal path behavior is split across two roots:

| Current persisted field | Current physical meaning | Current source of truth |
| --- | --- | --- |
| `DuplicateReclaimItem.archive_path` | Reclaim-stage holding path under `duplicate_reclaim_archive_root` | Primary source for restore while item remains archived |
| `DuplicateReclaimItem.recycle_path` | Later recycle-stage path under `recycle_bin_root` | Primary source for later recycle/purge workflow |
| `DuplicateReclaimRecord.archive_path` | Overloaded compatibility field that may point at either reclaim-stage or recycle-stage location | Hazardous compatibility field, not a stable path contract |

Current path shapes:

| Stage | Current path shape |
| --- | --- |
| Archive | `<duplicate_reclaim_archive_root>/<content_id>/<file_instance_id>-<basename>` |
| Later recycle | `<recycle_bin_root>/duplicates/<content_id>/<file_instance_id>-<archive basename>` |

### Target path model

The long-term target is one duplicate-bin-centered root and one primary duplicate-bin path per item.

Target direction:

- the long-term duplicate-removal root becomes `MEDIA_MANAGER_RECYCLE_BIN_ROOT`
- duplicate items should eventually have one primary bin path meaning
- restore should resolve from durable item metadata, not by inferring behavior from whether a path happens to live under reclaim or recycle roots

### Mixed old/new coexistence requirements

Dual-path support is required during migration.

During coexistence:

- old rows may still have reclaim-root-backed `archive_path`
- later rows or migrated rows may have recycle-bin-root-backed primary bin locations
- some items may still also carry a downstream `recycle_path`
- restore logic must tolerate mixed physical locations across old and new representations

Restore rule during coexistence:

- the restore source must be selected from durable row state and explicit path fields
- mirrored folder structure is convenience only and must not be the sole restore lookup contract
- implementation slices should prefer item-level path facts over record-level compatibility fields when both exist

### Primary migration hazard: overloaded `archive_path`

The overloaded meaning of `DuplicateReclaimRecord.archive_path` is a primary migration hazard.

Today that field may mean:

- reclaim-stage holding location before later recycle
- recycle-bin-stage location after `RECLAIM_RECYCLE`

This creates real migration risk:

- naive backfills may misclassify the current physical stage of an item
- restore logic may choose the wrong source path if it trusts `record.archive_path` blindly
- mixed old/new rows may appear consistent at the record layer while pointing to different physical lifecycle stages

Future implementation slices must treat `DuplicateReclaimRecord.archive_path` as a compatibility field requiring explicit interpretation, not as an unambiguous bin-path contract.

## Restore / Expiry Contract

The migration must preserve these operator-facing semantics throughout:

- Restore before expiry is allowed.
- Restore after expiry is blocked in the GUI.
- Expired items remain visible until later purge.
- Manual/run-based purge remains acceptable after expiry.
- Restored groups do not automatically become eligible again; review must be repeated.

Operational interpretation during coexistence:

- before expiry, restore may target either reclaim-stage or target-bin-stage physical location depending on which representation the item currently uses
- after expiry, the item may still be physically present but should not appear restorable in GUI workflows
- purge timing should remain explicit and run-driven rather than implicit or hidden

## Migration Phases

### Phase 1: Service-Layer Compatibility Boundary

Already introduced:

- bin-centered service helpers exist
- reclaim-named service methods remain compatibility wrappers
- route shapes remain unchanged

This phase should remain in place while deeper migration proceeds.

### Phase 2: Path / Config Transition

- introduce bin-first path semantics at the service/planning boundary
- keep compatibility reads for reclaim-root-backed items
- begin treating `MEDIA_MANAGER_RECYCLE_BIN_ROOT` as the primary long-term duplicate-removal root in implementation slices
- preserve restore correctness for items still living under reclaim-root paths

### Phase 3: State / Data Migration

- backfill or reinterpret persisted duplicate-removal rows into the target bin-centered model
- separate clearly which fields are compatibility-only versus target-primary
- preserve `original_path`, restore timestamps, expiry timestamps, and purge timing facts
- do not introduce `READY_FOR_BIN` as a durable item state during this phase unless a later concrete need is proven

### Phase 4: Dual-Read / Dual-Path Coexistence

- support old reclaim-shaped rows and newer bin-centered representations together
- restore and read models must handle mixed path and mixed state representations safely
- compatibility logic should remain explicit and observable

### Phase 5: Legacy Reclaim Retirement

- retire `MEDIA_MANAGER_RECLAIM_ROOT`
- retire reclaim-first duplicate-removal assumptions
- remove reclaim-named persistence and payload shapes only after restore safety, coexistence handling, and migration validation are proven

## Risks / Deferred Items

### Primary risks

- restore correctness across mixed old/new path locations
- overloaded `archive_path` interpretation at record level
- path collisions or basename reuse under target bin layout
- old rows and new rows coexisting with different path semantics
- idempotency and resume safety for any future migration runner
- purge timing and expiry handling during coexistence

### Deferred items

- final schema/table rename plan
- exact final durable bin-item schema
- exact target wire payload shape for bin-centered reads
- whether one path field or multiple explicit stage fields survive long-term
- exact path-layout convention under `MEDIA_MANAGER_RECYCLE_BIN_ROOT`
- any migration-runner implementation details, backfill tooling, or online cutover choreography

## Acceptance Notes For Future Slices

Future implementation slices should treat this document as the migration contract.

In particular:

- preserve planner/apply as the only filesystem mutator
- keep restore metadata authoritative
- treat `READY_FOR_BIN` as derived unless later work proves durable state is necessary
- treat `DuplicateReclaimRecord.archive_path` as hazardous compatibility state until it is replaced or normalized
