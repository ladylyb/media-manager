# Duplicate Recycle Bin Persistence / Schema Migration Spec

## Status

Implementation-ready planning/specification document. This spec defines the staged migration from reclaim-shaped duplicate-removal persistence toward bin-centered persisted storage without changing live behavior by itself.

Related documents:

- [Duplicate Recycle Bin Lifecycle Simplification](duplicate-recycle-bin-lifecycle.md)
- [Duplicate Recycle Bin Migration Spec](duplicate-recycle-bin-migration-spec.md)
- [Duplicate Recycle Bin Contract Migration Spec](duplicate-recycle-bin-contract-migration-spec.md)

## Purpose

Duplicate-removal runtime behavior is already partially bin-centered, but durable persistence remains reclaim-shaped. This document defines the persistence/schema migration path for introducing bin-native authoritative storage while preserving restore correctness, migration safety, and compatibility for legacy rows.

Core rules:

- item-level duplicate bin fields become the authoritative source for physical location, restore-source selection, and expiry/retention truth
- `duplicate_reclaim_records` remains review/compatibility-oriented during migration
- planner/apply invariants, idempotency, resume safety, and DB-gated filesystem mutation remain unchanged

This is a persistence/storage migration spec, not an API contract migration spec.

## Current-State Inventory

This inventory is grounded in the current implementation:

- [media_manager/app/persistence/models.py](/home/harish/projects/media-manager/media_manager/app/persistence/models.py)
- [media_manager/app/persistence/phase3_actions.py](/home/harish/projects/media-manager/media_manager/app/persistence/phase3_actions.py)
- [media_manager/app/persistence/apply.py](/home/harish/projects/media-manager/media_manager/app/persistence/apply.py)
- [media_manager/app/persistence/policy_settings.py](/home/harish/projects/media-manager/media_manager/app/persistence/policy_settings.py)
- [media_manager/app/persistence/operator_console.py](/home/harish/projects/media-manager/media_manager/app/persistence/operator_console.py)
- [migrations/versions/0024_integrity_and_duplicate_reclaim.py](/home/harish/projects/media-manager/migrations/versions/0024_integrity_and_duplicate_reclaim.py)
- [migrations/versions/0025_phase3_reclaim_and_quarantine_records.py](/home/harish/projects/media-manager/migrations/versions/0025_phase3_reclaim_and_quarantine_records.py)
- [migrations/versions/0026_recycle_bin_soft_delete.py](/home/harish/projects/media-manager/migrations/versions/0026_recycle_bin_soft_delete.py)
- [migrations/versions/0028_phase5_integrity_reclaim_policy_controls.py](/home/harish/projects/media-manager/migrations/versions/0028_phase5_integrity_reclaim_policy_controls.py)

### Current persisted duplicate-removal entities

`duplicate_reclaim_records` is a group-level table keyed by `content_id`.

Current columns:

- `content_id`
- `reclaim_status`
- `reviewed_at`
- `reviewed_by`
- `archive_path`
- `reclaimed_at`
- `expires_at`
- `restored_at`
- `created_at`
- `updated_at`

Current allowed `reclaim_status` values:

- `UNREVIEWED`
- `REVIEWED_SAFE_TO_RECLAIM`
- `ARCHIVED`
- `SCHEDULED_FOR_DELETE`
- `RESTORED`

`duplicate_reclaim_items` is the per-file workflow table keyed by `file_instance_id`.

Current columns:

- `file_instance_id`
- `content_id`
- `original_path`
- `archive_path`
- `item_status`
- `reclaimed_at`
- `expires_at`
- `recycle_path`
- `recycled_at`
- `purge_after_at`
- `purged_at`
- `restored_at`
- `created_at`
- `updated_at`

Current allowed `item_status` values:

- `PENDING`
- `ARCHIVED`
- `RESTORED`
- `RECYCLED`

### Current path field meanings

Current duplicate-removal storage is stage-split:

| Stage | Current physical root | Current persisted path field | Current behavior |
| --- | --- | --- | --- |
| Initial duplicate move | `recycle_bin_root` | `DuplicateReclaimItem.archive_path` | Planner now targets `recycle_bin_root/duplicates/...` for new moves |
| Later recycle after expiry | `recycle_bin_root` | `DuplicateReclaimItem.recycle_path` | Later retention recycle may move or may remain under the same root |

Important current path facts:

- `DuplicateReclaimItem.original_path` is the authoritative restore destination.
- `DuplicateReclaimItem.archive_path` currently carries both planned-target and active-source semantics.
- `DuplicateReclaimItem.recycle_path` carries the later recycle-stage location after expiry.
- `DuplicateReclaimRecord.archive_path` is overwritten across lifecycle stages and does not have one stable meaning.

### Current timestamp meanings

Current timestamp usage is mixed between item-level authority and record-level compatibility:

- `reclaimed_at` records when archive/bin entry was persisted
- `expires_at` is currently the restore/retention boundary on archived items
- `recycled_at` records later recycle execution
- `purge_after_at` records later purge eligibility
- `purged_at` records final purge completion
- `restored_at` records restore completion

Record-level timestamps exist, but current record-level usage is compatibility-shaped rather than cleanly authoritative for lifecycle truth.

### Current restore dependence

Current restore planning depends on:

- `DuplicateReclaimItem.item_status == ARCHIVED`
- `DuplicateReclaimItem.archive_path` as the restore source
- `DuplicateReclaimItem.original_path` as the restore destination

Current restore logic does not have a bin-native authoritative path field yet. `DuplicateReclaimRecord.archive_path` is not a safe authoritative restore source.

### Current policy/config persistence dependencies

Current persisted policy/config values used by duplicate-removal include:

- `recycle_bin_root`
- `duplicate_reclaim_archive_root`
- `duplicate_reclaim_default_retention_days`
- `duplicate_reclaim_notify_on_reviewed_safe`
- `recycle_purge_days`

Current implementation facts:

- `recycle_bin_root` is already the current duplicate move root
- `duplicate_reclaim_archive_root` still exists in persisted policy and env overrides but is no longer the active duplicate move target
- `duplicate_reclaim_default_retention_days` still drives the duplicate restore window

### Current group-record role

`duplicate_reclaim_records` currently mixes:

- review/eligibility compatibility
- coarse group lifecycle projection
- a path field that no longer has one stable meaning

This makes it unsuitable as the long-term operational source of truth for physical location or restore source selection.

## Target Persistence Model

Review state and bin-item state remain separate concerns.

### Authoritative item-level target fields

Add new authoritative item-level fields:

- `planned_bin_path`: planned destination before apply
- `bin_path`: single authoritative current physical location of the duplicate for every non-restored, non-purged stage
- `bin_entered_at`: timestamp when the item first became physically located in the bin
- `restore_expires_at`: restore cutoff timestamp
- `bin_state`: persisted coarse containment/workflow state

Recommended `bin_state` values:

- `PENDING_MOVE`
- `IN_BIN`
- `RESTORED`
- `PURGED`

### Explicit `bin_state` semantics

`bin_state` is intentionally coarse physical-containment state only.

Decision:

- do not introduce a separate persisted `RECYCLED_PENDING_PURGE`-style state
- post-expiry / recycled-but-not-purged items remain `bin_state = IN_BIN`
- restore eligibility is governed separately by `restore_expires_at`
- purge readiness is governed separately by `purge_after_at` and `purged_at`

Reason:

- `bin_state` should answer only where the item sits in the broad containment lifecycle
- restore and purge timing should remain explicit timestamp-based facts
- this avoids recreating the same overloaded lifecycle problem where one enum tries to express physical location, restore eligibility, and purge stage at once

### Explicit `recycle_path` target posture

`bin_path` becomes the single authoritative current-location field across all non-restored stages.

Target decision:

- `recycle_path` is legacy-only during coexistence
- `recycle_path` is a backfill/compatibility input, not a future authority field
- there is no distinct long-term canonical post-expiry path concept that still justifies a separate persisted field once `bin_path` exists

### Group-record authority boundary

During migration, `duplicate_reclaim_records` remains review/compatibility-oriented only.

It must not be authoritative for:

- physical location
- restore source selection
- restore eligibility truth
- expiry / retention truth
- recycle timing
- purge timing

Group-level rows may continue to project review compatibility and aggregate status, but item rows hold the operational source of truth.

## Rename vs Compatibility Strategy

### Option 1: rename in place

Reject.

Why weaker:

- current reclaim-shaped fields do not carry stable enough meanings, especially `archive_path`
- rename-in-place would hide semantic debt rather than remove it
- current runtime already contains mixed reclaim/bin semantics, so in-place rename would increase ambiguity during coexistence

### Option 2: introduce new bin-native fields and migrate gradually

Recommend.

Why stronger:

- preserves restore correctness by shifting authority explicitly rather than implicitly
- supports deterministic backfill without filesystem mutation
- keeps rollback practical while coexistence remains active
- allows legacy rows to remain operable while new writes populate clear bin-native authority fields

### Option 3: compatibility layer only over existing schema

Reject.

Why weaker:

- preserves `archive_path` overload indefinitely
- leaves restore correctness dependent on legacy interpretation rules
- makes later retirement of reclaim terminology and fields harder, not easier

## Current-to-Target Data Mapping

### Item-level mapping

Current row mapping:

- `item_status = PENDING`
  - `planned_bin_path = archive_path`
  - `bin_path = NULL`
  - `bin_entered_at = NULL`
  - `restore_expires_at = expires_at`
  - `bin_state = PENDING_MOVE`
- `item_status = ARCHIVED`
  - `planned_bin_path = NULL`
  - `bin_path = archive_path`
  - `bin_entered_at = reclaimed_at`
  - `restore_expires_at = expires_at`
  - `bin_state = IN_BIN`
- `item_status = RECYCLED`
  - `planned_bin_path = NULL`
  - `bin_path = recycle_path if present else archive_path`
  - `bin_entered_at = reclaimed_at`
  - `restore_expires_at = expires_at`
  - `bin_state = IN_BIN`
  - purge progression remains represented by `purge_after_at` and `purged_at`
- `item_status = RESTORED`
  - `planned_bin_path = NULL`
  - `bin_path = NULL`
  - `bin_entered_at = reclaimed_at`
  - `restore_expires_at = expires_at`
  - `bin_state = RESTORED`

Final-purge mapping:

- once an item is actually purged, `bin_state = PURGED`
- `purged_at` remains the timestamp fact for when purge completed

### Record-level posture

`DuplicateReclaimRecord.reclaim_status` remains compatibility/review-oriented during migration.

Record-level `archive_path` is compatibility-only and is not a target authority field.

## Restore-Source and Runtime-Behavior Rules

### Clarification on runtime behavior

This document is a planning/specification artifact. It does not itself change runtime behavior.

Later implementation phases may change internal restore-reader precedence for coexistence safety. That is allowed if it preserves the same intended product behavior:

- restore before expiry remains allowed
- restore after expiry remains blocked
- restore must never proceed from an ambiguous or guessed source

### Restore-source precedence during coexistence

Restore source selection must follow this order:

1. Use `bin_path` when `bin_state = IN_BIN` and `bin_path` is non-null.
2. Otherwise, for legacy rows still in a restorable pre-cutover state, use item-level `archive_path` only when the row indicates the legacy archived stage and the value is non-null.
3. Do not use `recycle_path` as an independent authority once `bin_path` exists. `recycle_path` is only a backfill input and legacy compatibility field.
4. Never use `DuplicateReclaimRecord.archive_path` as an authoritative restore source.

### Fail-safe posture

If neither authoritative new fields nor an acceptable item-level legacy path can provide a valid restore source:

- planning must not emit a restore filesystem action
- the run must record a durable failure fact or explicit non-planned reason
- no fallback may guess from folder layout
- no fallback may promote group-record compatibility fields into restore authority

## `archive_path` Retirement Strategy

### Current meaning in practice

On `DuplicateReclaimItem`, `archive_path` currently means both:

- planned destination before apply
- current restore source while the item is still in the legacy archived stage

On `DuplicateReclaimRecord`, `archive_path` currently means:

- some latest reclaim/recycle path associated with the group

That is not a stable lifecycle fact.

### Why current meaning is overloaded

`archive_path` is unsafe because it combines:

- plan-time and apply-time semantics
- item-level and record-level path projection
- different physical lifecycle stages under one name

This ambiguity creates real restore and migration risk.

### Retirement plan

Replace its responsibilities rather than renaming it:

- `planned_bin_path` takes over planned-target responsibility
- `bin_path` takes over actual current-location responsibility
- `archive_path` remains compatibility-only during coexistence

Legacy restore compatibility:

- existing rows remain restorable through deterministic backfill where possible
- until full cutover, item-level `archive_path` remains an allowed fallback only under the explicit restore precedence rules in this document
- record-level `archive_path` is never promoted into restore authority

## Data Migration Strategy

### Overall migration posture

Use phased one-time backfill plus dual-read/dual-write coexistence.

This is not a lazy-only migration.

### Required migration mechanics

Backfill:

- required
- one deterministic database-only backfill for existing `duplicate_reclaim_items`
- no filesystem mutation

Dual-read:

- required during coexistence
- readers prefer new authoritative fields first, then explicit legacy fallback only where allowed

Dual-write:

- required during coexistence
- planner/apply writes both new and legacy fields until cutover is complete

Restore correctness during coexistence:

- restore source comes from item-level authoritative fields first
- item-level legacy fallback is tightly constrained
- record-level compatibility fields are excluded from restore authority

Path coexistence:

- legacy rows may still have only `archive_path`
- some rows may also carry `recycle_path`
- new rows will carry `planned_bin_path` and/or `bin_path`
- `bin_path` is the long-term current-location authority across all non-restored stages

Reversibility posture:

- additive schema and backfill phases are rollback-friendly
- destructive retirement phases are only reversible until legacy fields are dropped
- after destructive drops, rollback posture becomes forward-fix only

## Migration Phases

### Phase 1: additive schema foundation

Entry conditions:

- current mixed reclaim/bin schema is live
- no runtime cutover has happened yet

Work performed:

- add nullable bin-native item fields
- keep legacy columns, enums, and tables unchanged
- do not rename models or tables

Exit conditions:

- schema can represent both legacy and target facts

Rollback posture:

- ignore new columns

### Phase 2: dual-write planner/apply slice

Entry conditions:

- additive fields exist

Work performed:

- planner writes `planned_bin_path`, `restore_expires_at`, and `bin_state = PENDING_MOVE`
- apply writes `bin_path`, `bin_entered_at`, and `bin_state`
- legacy fields are still maintained for coexistence

Exit conditions:

- all newly written rows carry target authoritative item-level facts

Rollback posture:

- legacy readers remain available

### Phase 3: deterministic historical backfill

Entry conditions:

- dual-write is live

Work performed:

- run a database-only backfill for existing item rows
- map legacy item states into new fields using this spec’s rules
- do not mutate files

Exit conditions:

- historical rows have coherent item-level bin authority

Rollback posture:

- dual-read continues to support legacy interpretation

### Phase 4: authority cutover

Entry conditions:

- backfill is complete
- coexistence behavior is validated

Work performed:

- restore, expiry, retention, and operator projections prefer new item-level authority
- legacy fields remain compatibility-only
- group records stay review/compatibility-oriented

Exit conditions:

- operational correctness no longer depends on overloaded legacy path fields

Rollback posture:

- limited reader fallback remains possible while destructive drops have not happened

### Phase 5: legacy narrowing and cleanup

Entry conditions:

- runtime is fully off legacy authority

Work performed:

- retire `archive_path` and `recycle_path`
- retire record-level path authority entirely
- evaluate physical table/model renames only if still justified later

Exit conditions:

- bin-centered persistence exists without overloaded path fields

Rollback posture:

- only safe before destructive drops

## Test Plan

Required implementation coverage:

- additive schema migration tests for new nullable item fields
- deterministic backfill of legacy `ARCHIVED` rows into `bin_path`
- deterministic backfill of legacy `RECYCLED` rows into coarse `bin_state = IN_BIN` plus purge timestamps
- restore from new authoritative `bin_path`
- restore from acceptable item-level legacy fallback rows
- refusal to plan restore when no authoritative or acceptable legacy source exists
- mixed old/new datasets in one run
- no filesystem mutation before durable DB gating
- resume/idempotency across move, restore, recycle, and purge

## Risks, Compatibility Hazards, Deferred Items

Major risks:

- accidental dual authority between legacy and new item fields
- misclassifying `RECYCLED` rows if backfill treats purge-stage timing as a new enum instead of separate timestamps
- allowing group-record fields back into operational authority
- hidden restore fallback that guesses from path layout

Compatibility hazards:

- old rows may appear superficially complete at the group-record layer while still lacking safe item-level restore authority
- transitional reads must not treat `archive_path` and `recycle_path` as equal-authority peers once `bin_path` exists

Deferred items:

- physical table/model renames
- API contract cleanup
- policy contract renames
- operation-type renames

## Non-Goals

- no schema implementation in this document
- no Alembic migration in this document
- no model rename in this document
- no immediate runtime behavior change from this planning document alone
- no restore product-behavior change; only later coexistence-safe internal precedence changes are in scope for implementation

## Assumptions

- this persistence spec remains a dedicated sibling document
- `recycle_bin_root` remains the intended duplicate move root
- `EXPIRED_IN_BIN` remains a projection derived from timestamps, not a persisted enum
- `bin_path` is the final single authoritative current-location field across all in-bin stages
