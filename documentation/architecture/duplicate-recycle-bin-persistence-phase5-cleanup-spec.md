# Duplicate Recycle Bin Persistence Phase 5 Cleanup Spec

## Status

Implementation-ready planning/specification document. This spec defines the legacy narrowing and cleanup plan after Phases 1 through 4 of the duplicate bin persistence migration.

Related documents:

- [Duplicate Recycle Bin Lifecycle Simplification](duplicate-recycle-bin-lifecycle.md)
- [Duplicate Recycle Bin Migration Spec](duplicate-recycle-bin-migration-spec.md)
- [Duplicate Recycle Bin Persistence Migration Spec](duplicate-recycle-bin-persistence-migration-spec.md)
- [Duplicate Recycle Bin Contract Migration Spec](duplicate-recycle-bin-contract-migration-spec.md)

## Purpose

Post-Phase-4, duplicate-removal persistence now carries bin-native item-level fields and read-side authority has moved to those fields for restore source selection, restore timing truth, and operator projections. This phase is about deciding which legacy reclaim-shaped fields can stop mattering operationally, which ones still need to remain as compatibility baggage, and which cleanup steps are actually worth the churn.

This is a cleanup/narrowing spec only.

Non-goals:

- no destructive migration yet
- no legacy column drop yet
- no model/table rename yet
- no API contract change yet
- no policy contract change yet

## Grounding

This plan is grounded in the current post-Phase-4 implementation:

- [media_manager/app/persistence/models.py](/home/harish/projects/media-manager/media_manager/app/persistence/models.py)
- [media_manager/app/persistence/phase3_actions.py](/home/harish/projects/media-manager/media_manager/app/persistence/phase3_actions.py)
- [media_manager/app/persistence/apply.py](/home/harish/projects/media-manager/media_manager/app/persistence/apply.py)
- [media_manager/app/persistence/operator_console.py](/home/harish/projects/media-manager/media_manager/app/persistence/operator_console.py)
- [migrations/versions/0030_duplicate_bin_item_fields.py](/home/harish/projects/media-manager/migrations/versions/0030_duplicate_bin_item_fields.py)
- [migrations/versions/0031_duplicate_bin_item_backfill.py](/home/harish/projects/media-manager/migrations/versions/0031_duplicate_bin_item_backfill.py)
- [media_manager/tests/test_phase3_duplicate_reclaim.py](/home/harish/projects/media-manager/media_manager/tests/test_phase3_duplicate_reclaim.py)
- [media_manager/tests/test_migration_duplicate_bin_item_backfill.py](/home/harish/projects/media-manager/media_manager/tests/test_migration_duplicate_bin_item_backfill.py)
- [media_manager/tests/test_operator_console_duplicates.py](/home/harish/projects/media-manager/media_manager/tests/test_operator_console_duplicates.py)

## A. Current Post-Phase-4 Authority Inventory

### Item-level paths

Current authoritative item-level fields:

- `DuplicateReclaimItem.original_path`
  - authoritative restore destination
- `DuplicateReclaimItem.bin_path`
  - authoritative current restore source when `bin_state = IN_BIN`
- `DuplicateReclaimItem.planned_bin_path`
  - authoritative planned destination before apply for new pending rows

Current compatibility-only item-level fields:

- `DuplicateReclaimItem.archive_path`
  - still dual-written
  - still used as constrained fallback for legacy archived rows in restore planning
  - still used by some write-side paths as a compatibility carrier
- `DuplicateReclaimItem.recycle_path`
  - still written during recycle planning
  - not used as independent restore authority
  - still exposed in operator retention projections

### Restore/recycle timing

Current authoritative timing field:

- `DuplicateReclaimItem.restore_expires_at`
  - used by restore planning and retention/operator projection as first-read timing truth

Current compatibility timing field:

- `DuplicateReclaimItem.expires_at`
  - still dual-written
  - still used as fallback by `_duplicate_restore_expiry(...)`
  - still copied into record-level compatibility state

Current purge-stage timing fields that remain real operational truth:

- `purge_after_at`
- `purged_at`
- `recycled_at`
- `restored_at`

### Record-level fields

`DuplicateReclaimRecord` is now compatibility/review-oriented, not operational authority.

Operationally non-authoritative fields include:

- `DuplicateReclaimRecord.archive_path`
- `DuplicateReclaimRecord.reclaimed_at`
- `DuplicateReclaimRecord.expires_at`

Still meaningful as review/aggregate compatibility:

- `reclaim_status`
- `reviewed_at`
- `reviewed_by`
- `restored_at`

### Legacy reclaim-shaped statuses

Item-level reality:

- `item_status` still drives write-side workflow selection:
  - planner restore candidates query `ARCHIVED`
  - planner recycle candidates query `ARCHIVED`
  - apply transitions still update `ARCHIVED`, `RESTORED`, `RECYCLED`
- `bin_state` now carries the authoritative coarse containment semantics

Record-level reality:

- `reclaim_status` still drives review/group workflow compatibility and operator-facing actionable decisions
- it is not used as restore source or expiry authority

### Operator projections

Current operator projections already read item-level bin-native authority where needed:

- duplicate archive page projects current location from `bin_path` first
- retention/recycle page projects:
  - current location from `bin_path` first
  - retention timing from `restore_expires_at` first

Contract shape is still reclaim-shaped, but the projected values are already item-native.

## B. Legacy Narrowing Candidates

### Safe to narrow from operational authority now

#### `DuplicateReclaimRecord.archive_path`

Recommendation:

- treat as compatibility-only immediately
- stop treating it as meaningful operational state in any future implementation slice

Reason:

- it is already excluded from restore authority
- it is overwritten across stages
- Phase 4 proved item-level fields can carry the needed location truth

#### `DuplicateReclaimItem.archive_path`

Recommendation:

- narrow from general operational authority now
- preserve only as constrained legacy restore fallback plus temporary write-side compatibility field

Reason:

- `bin_path` now owns active current-location truth
- `planned_bin_path` now owns planned-destination truth
- `archive_path` still serves one useful coexistence job: legacy archived-row fallback

#### `DuplicateReclaimItem.expires_at`

Recommendation:

- narrow from authority now
- keep as compatibility mirror while coexistence continues

Reason:

- `restore_expires_at` already owns read-side restore eligibility truth
- write-side paths still keep them aligned
- drop should wait until no remaining path depends on fallback semantics

### Compatibility-only but keep for longer

#### `DuplicateReclaimItem.recycle_path`

Recommendation:

- keep for at least one more cleanup slice
- treat as compatibility/reporting field, not restore authority

Reason:

- recycle planning still writes it
- apply recycle still copies record-level compatibility from it
- retention page still exposes it directly
- removing it too early would widen the Phase 5 slice from narrowing into workflow redesign

#### `DuplicateReclaimItem.item_status`

Recommendation:

- do not narrow aggressively in Phase 5
- keep as the workflow transition field for now

Reason:

- current planner/apply code still queries and mutates it directly
- replacing it with `bin_state` would require a larger runtime transition mapping change, not just cleanup

#### `DuplicateReclaimRecord.reclaim_status`

Recommendation:

- keep

Reason:

- still used in duplicate review/actionability flows
- still meaningful at the group-review layer even if it is not path/timing authority

### Not safe to touch yet

#### Table/model names

- `DuplicateReclaimItem`
- `DuplicateReclaimRecord`
- table names `duplicate_reclaim_items` and `duplicate_reclaim_records`

Not safe to touch in the first cleanup slice because:

- semantics are already separated without rename
- runtime and tests still intentionally speak reclaim at the review/group layer
- rename churn would touch persistence models, migrations, test fixtures, and admin references with limited behavioral payoff

## C. Destructive Cleanup Candidates

### Recommended eventual drops

Drop later, not in initial Phase 5 implementation slice:

- `DuplicateReclaimRecord.archive_path`
  - strongest drop candidate
  - already semantically dead as operational authority
- `DuplicateReclaimItem.archive_path`
  - only after legacy restore fallback is removed and all rows are guaranteed to have acceptable `bin_path`
- `DuplicateReclaimItem.expires_at`
  - only after all planner/operator/read paths stop using fallback semantics

### Recommended eventual retention

Retain longer, possibly indefinitely unless a later refactor justifies removal:

- `DuplicateReclaimRecord.reclaim_status`
- `DuplicateReclaimItem.item_status`

Reason:

- both still encode meaningful workflow compatibility that has not been replaced one-for-one by `bin_state`

### Recommended against for now

Do not prioritize:

- dropping `DuplicateReclaimItem.recycle_path` in the first destructive cleanup slice
- collapsing `item_status` into `bin_state`
- collapsing `reclaim_status` into an item-derived group projection only

These are possible future simplifications, but they are not low-risk cleanup. They are behavioral model changes.

## D. Rename-Worthiness Analysis

### `DuplicateReclaimItem`

Recommendation:

- do not rename

Reason:

- the semantic cleanup already happened at the field-authority level
- the class still legitimately represents a duplicate-removal workflow row in a reclaim/review subsystem
- a rename would create widespread churn across migrations, tests, and repository code for limited maintenance value

### `DuplicateReclaimRecord`

Recommendation:

- do not rename

Reason:

- it still represents the review/group compatibility layer, which remains reclaim-shaped
- renaming it to a bin term would actually make the code less precise because the record is not the bin authority record

### Table names

Recommendation:

- leave table names alone

Reason:

- storage semantics can be made clean without physical rename
- table rename would add migration complexity, downgrade risk, and operational churn
- there is no concrete product or maintenance win large enough to justify that cost post-Phase-4

Bottom line:

- physical renames are not worth the churn
- spend cleanup budget on removing overloaded meanings, not on renaming stable tables

## E. Recommended Cleanup Strategy

Recommended Phase 5 strategy:

1. narrow authority first
2. remove dead compatibility writes next
3. only then consider destructive column cleanup
4. defer rename work entirely

This should be implemented as multiple small slices, not one destructive sweep.

## F. Cleanup Sequencing

### Phase 5A: Legacy authority freeze

Entry conditions:

- Phase 4 read-side authority cutover is live
- Phase 4 tests prove `bin_path` / `restore_expires_at` authority and legacy fallback behavior

Work:

- audit remaining planner/apply/operator code and remove any accidental read-side use of:
  - record-level `archive_path`
  - record-level `expires_at`
  - `recycle_path` as restore authority
- document `archive_path`, record-level path/timing fields, and `expires_at` as compatibility-only in code comments where still present

Exit conditions:

- no read path depends on record-level path/timing fields
- no restore path depends on `archive_path` except explicit legacy fallback

Rollback posture:

- code-only rollback is straightforward because no destructive schema change occurs

### Phase 5B: Compatibility write narrowing

Entry conditions:

- 5A complete
- telemetry/tests confirm no read-side dependence on narrowed fields

Work:

- stop updating `DuplicateReclaimRecord.archive_path` as if it were meaningful operational state
- stop updating record-level `expires_at` / `reclaimed_at` except where still needed for explicit review/admin projection
- consider stopping new writes to `DuplicateReclaimItem.archive_path` for rows created after the cleanup cut line if legacy fallback is no longer required for new rows

Exit conditions:

- legacy fields are clearly passive compatibility baggage, not active mirrored truth

Rollback posture:

- rollback is still code-only if schema remains unchanged

### Phase 5C: Destructive column cleanup

Entry conditions:

- no active read path depends on the target columns
- compatibility window for legacy restore fallback has ended
- production data audit confirms target columns are no longer needed for old rows

Work:

- drop `DuplicateReclaimRecord.archive_path`
- drop `DuplicateReclaimItem.archive_path`
- drop `DuplicateReclaimItem.expires_at`

Possible same-slice or later:

- reevaluate `DuplicateReclaimItem.recycle_path` separately

Exit conditions:

- item-level bin-native fields are the only remaining location/restore-expiry truth for duplicate-removal persistence

Rollback posture:

- destructive rollback is data-lossy
- rollback after drop is forward-fix only unless a compatibility snapshot/backfill plan exists

### Still deferred after Phase 5

- table/model renames
- policy contract rename
- API contract rename
- replacing `item_status` with `bin_state` as the sole workflow state field
- removing `reclaim_status` from the group-review model

## Compatibility Boundaries

### Must remain for old-row compatibility during cleanup

- item-level `archive_path` until legacy restore fallback is formally removed
- item-level `expires_at` until all fallback timing reads are eliminated

### Must remain because of operator/admin/reporting expectations

- `item_status`
- `reclaim_status`
- likely `recycle_path` until retention/reporting projections are redesigned to rely only on current-location plus purge timestamps

### Can be retired from authority before physical drop

- `DuplicateReclaimRecord.archive_path`
- `DuplicateReclaimRecord.expires_at`
- `DuplicateReclaimRecord.reclaimed_at`
- `DuplicateReclaimItem.archive_path`
- `DuplicateReclaimItem.expires_at`

This is the main cleanup rule:

- retire authority first
- drop only after the compatibility window and data audit say the column is genuinely dead

## Recommended Implementation Order

- first implementation slice:
  - Phase 5A authority freeze audit
- second implementation slice:
  - Phase 5B compatibility write narrowing
- third implementation slice:
  - targeted destructive cleanup of record-level path/timing baggage
- final optional slice:
  - reconsider `archive_path`, `expires_at`, and `recycle_path` physical drops on the item table

## Major Risks

- treating “new field exists” as sufficient proof that the legacy field can be dropped
- collapsing `item_status` into `bin_state` too early and breaking workflow transitions
- dropping `archive_path` before the last acceptable legacy restore rows have aged out or been normalized
- assuming record-level fields are harmless while continuing to dual-write them as if they are truth
- doing rename work that adds churn but does not reduce real maintenance cost

## Deferred Questions

- whether `recycle_path` should ultimately be replaced by a derived operator projection instead of a persisted field
- whether `item_status` should remain the workflow transition field long-term even after cleanup
- whether record-level `reclaim_status` should eventually become a pure projection instead of stored state

## Recommendation Summary

- Do not rename models or tables.
- Treat record-level path/timing fields as dead authority now.
- Keep `archive_path` and `expires_at` only as temporary compatibility fields until fallback dependence is gone.
- Keep `item_status`, `reclaim_status`, and likely `recycle_path` longer because they still serve real workflow or reporting roles.
- Sequence cleanup as authority freeze, then write narrowing, then destructive drop.
