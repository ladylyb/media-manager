# Duplicate-to-Integrity Decisioning Spec

## Status

Planning/specification only. This document defines the recommendation layer for duplicate review and duplicate bin workflows. It does not implement new decision logic, persistence, or UI behavior by itself.

## Summary

The current duplicate operator experience exposes:

- human duplicate review state via `DuplicateGroupReview.review_status`
- duplicate lifecycle/bin state via `DuplicateReclaimRecord.reclaim_status` and `DuplicateReclaimItem`
- integrity truth via `IntegrityCheck.status` plus optional integrity review overrides

That gives the operator raw fragments, but not a system recommendation.

Today the duplicate group read model in [operator_console.py](/home/harish/projects/media-manager/media_manager/app/persistence/operator_console.py) exposes:

- `review_status`
- `reclaim_status`
- `duplicate_reclaim_actionable`
- `duplicate_reclaim_unavailable_reason`
- `integrity_issue_count`
- `integrity_broken_count`
- `integrity_suspect_count`

This is enough to show facts, but not enough to answer the product questions directly:

- can extra copies move if the keep copy is healthy and only extras are broken?
- should movement be blocked if the keep copy is broken or suspect?
- should mixed health keep the group in review?
- how should this be surfaced consistently across Review Duplicates, Ready for Bin, Recycle Bin, and Playback Issues?

The product needs a recommendation layer that translates existing duplicate plus integrity facts into operator guidance without collapsing review state, lifecycle state, and recommendation state into one blob.

## Grounded Current State

### Current duplicate review state

Human review is stored separately in `DuplicateGroupReview.review_status` with:

- `looks_right`
- `needs_review`
- `not_sure`

This is the operator's durable assessment of whether the group is genuinely duplicate. It is not a system recommendation and should remain separate.

### Current duplicate lifecycle/bin state

Duplicate group lifecycle is represented separately through:

- `DuplicateReclaimRecord.reclaim_status`
- `DuplicateReclaimItem.item_status`
- `DuplicateReclaimItem.bin_state`
- item-level location/timing fields such as `bin_path`, `restore_expires_at`, `recycle_path`

After the completed duplicate recycle-bin persistence migration, item-level bin-native fields are authoritative for duplicate item location and restore timing.

### Current integrity truth

Playback/integrity truth is persisted through `IntegrityCheck.status`:

- `OK`
- `SUSPECT`
- `BROKEN`

Optional operator review exists through `IntegrityReviewDecision.decision`:

- `MARK_OK`
- `IGNORE`

The duplicate group read model currently only aggregates integrity into counts of broken and suspect files. It does not distinguish:

- keep copy health vs extra-copy health
- whether all issues are on extras only
- whether the canonical/keep copy is the unhealthy file
- whether integrity overrides should change recommendation severity

### Current operator surfaces

Current operator-facing duplicate surfaces are split across:

- Review Duplicates: duplicate groups with review state, coarse reclaim status, and integrity counts
- Ready for Bin behavior: derived today from `duplicate_reclaim_actionable` and `duplicate_reclaim_unavailable_reason`
- Recycle Bin: duplicate bin/archive and retention pages
- Playback Issues: integrity issue pages and file detail views

The decisioning layer must work with these surfaces rather than replacing them wholesale.

## Goals

- give the operator a clear recommendation for what to do with a duplicate group
- preserve explicit separation between human review state, duplicate/bin lifecycle state, and system recommendation state
- distinguish hard blockers from warnings
- keep the first implementation derived from existing durable facts
- avoid destabilizing the current duplicate/bin workflow

## Non-Goals

- implementing the decision engine in this slice
- redesigning the full Operator Console UI
- collapsing review state and recommendation state
- replacing integrity detail views
- changing duplicate/bin persistence semantics again
- introducing new filesystem behavior
- turning recommendation output into hidden planner/apply gating in the first implementation slice

## Recommendation Model

The recommendation layer should be operator-facing and derived, not the first new persisted authority layer.

### Operator-facing recommendation states

The initial recommendation vocabulary is:

- `SAFE_TO_MOVE_EXTRAS`
- `REVIEW_REQUIRED`
- `DO_NOT_MOVE`
- `ALREADY_IN_BIN`
- `EXPIRED_IN_BIN`

### Meanings

`SAFE_TO_MOVE_EXTRAS`

- the system recommends that extra copies may move into the duplicate bin
- this is not an auto-action
- warnings may still be attached, but they do not change the recommendation label

`REVIEW_REQUIRED`

- the system does not recommend movement yet
- the operator should review because evidence is incomplete, stale, or conflicting

`DO_NOT_MOVE`

- the system recommends that movement be blocked
- a true safety or structural stop exists under current facts

`ALREADY_IN_BIN`

- the relevant operator context is bin management, not move eligibility
- the group or actionable extras are already in the duplicate-bin lifecycle

`EXPIRED_IN_BIN`

- the group is already in the bin lifecycle and the restore window has expired
- the relevant operator context is retention/recycle handling, not duplicate review

### Derived vs displayed

All five states are operator-facing.

Their sources differ:

- `SAFE_TO_MOVE_EXTRAS`, `REVIEW_REQUIRED`, `DO_NOT_MOVE` are move-stage recommendations derived from duplicate plus integrity facts
- `ALREADY_IN_BIN`, `EXPIRED_IN_BIN` are lifecycle-derived informational outputs for surfaces that are no longer in the review/move stage

### Deterministic recommendation precedence

Recommendation selection must be deterministic. When multiple conditions are true, the highest-precedence recommendation wins.

Precedence order:

1. `EXPIRED_IN_BIN`
2. `ALREADY_IN_BIN`
3. `DO_NOT_MOVE`
4. `REVIEW_REQUIRED`
5. `SAFE_TO_MOVE_EXTRAS`

Interpretation:

- `EXPIRED_IN_BIN` and `ALREADY_IN_BIN` are lifecycle-dominant informational states. They win over move-stage recommendations because the relevant operator task is no longer "should I move this group now?"
- `DO_NOT_MOVE` wins over `REVIEW_REQUIRED` because a hard blocker must not be presented as mere caution.
- `REVIEW_REQUIRED` wins over `SAFE_TO_MOVE_EXTRAS` because incomplete, stale, or conflicting evidence must prevent a "safe to move" recommendation.

Classification:

| Recommendation | Class | Meaning |
| --- | --- | --- |
| `EXPIRED_IN_BIN` | terminal informational | bin lifecycle is the active operator context and restore is no longer allowed |
| `ALREADY_IN_BIN` | informational | group is already in bin lifecycle and should not be shown as ready-to-move |
| `DO_NOT_MOVE` | actionable blocker | movement should be blocked |
| `REVIEW_REQUIRED` | actionable hold | movement is not recommended yet; operator review or rescan is needed |
| `SAFE_TO_MOVE_EXTRAS` | actionable positive | movement is recommended |

## Rule Model

The first implementation should use explicit rule buckets rather than a hidden scoring model.

### Inputs

The recommendation engine should evaluate these inputs per duplicate group:

- canonical/keep file instance identity
- duplicate extra-copy file instance identities
- duplicate review state
- duplicate review staleness
- duplicate lifecycle/bin state
- integrity status for keep copy
- integrity status for each extra copy
- integrity evidence freshness
- integrity review override, if present
- restore/retention timing for in-bin rows

### Keep-copy health classes

The decision layer should classify the keep copy as one of:

- `KEEP_HEALTHY`
  - integrity status is `OK`
- `KEEP_SUSPECT`
  - integrity status is `SUSPECT`
- `KEEP_BROKEN`
  - integrity status is `BROKEN`
- `KEEP_UNKNOWN`
  - keep identity is known, but no usable integrity conclusion exists yet
- `KEEP_IDENTITY_MISSING`
  - no canonical mapping exists, or keep identity is ambiguous/inconsistent

### Extra-copy health classes

The decision layer should classify extras as one of:

- `EXTRAS_ALL_HEALTHY`
- `EXTRAS_ALL_UNHEALTHY`
- `EXTRAS_MIXED_HEALTH`
- `EXTRAS_UNKNOWN`
- `NO_ACTIVE_EXTRAS`

### Hard block vs review-required semantics

These categories are not interchangeable.

#### `DO_NOT_MOVE` means a true safety or structural stop

Use `DO_NOT_MOVE` only when the operator should not be encouraged to move extras at all under current facts.

This category covers:

- true safety stop
  - keep copy is `KEEP_BROKEN`
- structural stop
  - keep identity is `KEEP_IDENTITY_MISSING`
  - no active extra copies exist
- workflow stop
  - the group is already in bin lifecycle and should no longer be represented as move-stage actionable

`DO_NOT_MOVE` is not for "needs a closer look." It is for "do not proceed under current conditions."

#### `REVIEW_REQUIRED` means incomplete, conflicting, or stale evidence

Use `REVIEW_REQUIRED` when the operator needs to resolve ambiguity before a safe recommendation can be made.

This category covers:

- incomplete evidence
  - keep copy exists but integrity not yet evaluated
  - extras not yet evaluated
- conflicting evidence
  - healthy keep copy with mixed extra-copy health
  - suspect keep copy
- stale evidence
  - duplicate review stale
  - integrity evidence stale
- unresolved human decision
  - review state is `needs_review`
  - review state is `not_sure`
  - no duplicate review exists yet

`REVIEW_REQUIRED` must not be used when a hard stop exists.

#### `SAFE_TO_MOVE_EXTRAS` means allowed, even if warnings exist

Use `SAFE_TO_MOVE_EXTRAS` only when:

- the group is still in the move-stage workflow
- keep copy is healthy
- human duplicate review is favorable and fresh
- no hard stop exists
- no review-hold condition exists

This recommendation may still carry warning reason codes such as extra copies being unhealthy. The warnings explain context, but they do not change the recommendation label.

In Phase 1, `primary_reason_code` remains mandatory for every recommendation outcome.

### Unknown vs unhealthy vs missing identity

These must be treated separately.

| Condition | Meaning | Recommendation | Why | Operator next step |
| --- | --- | --- | --- | --- |
| keep copy unhealthy | keep copy integrity result is `BROKEN` | `DO_NOT_MOVE` | moving extras would preserve a broken keep copy as the survivor | investigate or repair keep copy before moving extras |
| keep copy suspect | keep copy integrity result is `SUSPECT` | `REVIEW_REQUIRED` | evidence is warning-grade, not final stop-grade | inspect playback issue or run deeper validation |
| keep copy unknown | keep copy exists but no usable integrity result exists yet | `REVIEW_REQUIRED` | evidence is incomplete, not structurally broken | run or refresh integrity evaluation |
| canonical/keep identity missing | no canonical mapping, or ambiguous keep identity | `DO_NOT_MOVE` | no trustworthy keep target exists | structural remediation; fix canonical identity first |
| extras unhealthy only | one or more extras are broken/suspect while keep is healthy | `SAFE_TO_MOVE_EXTRAS` | extra-copy health alone does not block preserving the healthy keep copy | move is allowed; warning explains extra-copy issues |
| extras mixed | extras contain both healthy and unhealthy copies | `REVIEW_REQUIRED` | operator should confirm intent before moving a mixed-quality set | manual review before moving |
| extras unknown | extras lack complete integrity evidence while keep is healthy | `REVIEW_REQUIRED` | recommendation would otherwise rely on incomplete evidence | run or refresh integrity evidence |

### Staleness model

Staleness is a first-class input and must be reported explicitly.

#### Stale duplicate review

Definition:

- the stored duplicate group review no longer matches the current group signature
- current canonical selection changed since review

Effect:

- degrades `SAFE_TO_MOVE_EXTRAS` to `REVIEW_REQUIRED`
- never upgrades a blocked group
- is not by itself a `DO_NOT_MOVE` hard stop unless keep identity is also ambiguous

#### Stale integrity evidence

Definition:

- integrity evidence is missing for one or more relevant files
- integrity evidence is outdated relative to current duplicate membership or current file identity snapshot

Effect:

- degrades `SAFE_TO_MOVE_EXTRAS` to `REVIEW_REQUIRED`
- does not convert a healthy keep copy into `BROKEN`
- does not justify `DO_NOT_MOVE` unless keep identity itself is missing

#### Stale bin/lifecycle timing assumptions

Definition:

- authoritative item-level timing or lifecycle facts imply the group is already in bin or restore has expired

Effect:

- resolved through lifecycle precedence rather than warning downgrade
- yields `ALREADY_IN_BIN` or `EXPIRED_IN_BIN`

Staleness reason codes:

- `REVIEW_STALE`
- `INTEGRITY_EVIDENCE_STALE`
- `BIN_LIFECYCLE_OUT_OF_DATE` only for technical/telemetry surfaces if needed later; not required for the first operator-facing version

### Decision rules

#### Lifecycle-dominant rules

- if authoritative duplicate lifecycle shows restore expired in bin, recommendation is `EXPIRED_IN_BIN`
- else if authoritative duplicate lifecycle shows active bin presence, recommendation is `ALREADY_IN_BIN`

These states take precedence before move-stage rules are evaluated for operator display.

#### Hard blockers -> `DO_NOT_MOVE`

- keep classification is `KEEP_IDENTITY_MISSING`
- keep classification is `KEEP_BROKEN`
- extra classification is `NO_ACTIVE_EXTRAS`

#### Review hold -> `REVIEW_REQUIRED`

- keep classification is `KEEP_SUSPECT`
- keep classification is `KEEP_UNKNOWN`
- extra classification is `EXTRAS_MIXED_HEALTH`
- extra classification is `EXTRAS_UNKNOWN`
- duplicate review state is not `looks_right`
- duplicate review is stale
- integrity evidence is stale or incomplete for relevant files

#### Positive recommendation -> `SAFE_TO_MOVE_EXTRAS`

- review state is `looks_right`
- review is fresh
- keep classification is `KEEP_HEALTHY`
- extra classification is `EXTRAS_ALL_HEALTHY` or `EXTRAS_ALL_UNHEALTHY`
- no lifecycle-dominant state applies
- no hard blocker applies
- no review-hold condition applies

Important product decision:

- broken or suspect extra copies alone do not block movement if the keep copy is healthy and the group has been positively reviewed
- the recommendation should still attach warning reason codes explaining that some extras have playback issues, but the recommendation label remains `SAFE_TO_MOVE_EXTRAS`
- positive `SAFE_TO_MOVE_EXTRAS` outcomes use:
  - `SAFE_TO_MOVE_REVIEWED_DUPLICATES` for the clean-safe case
  - `EXTRA_COPIES_UNHEALTHY_ONLY` for the safe-with-warning case

### Severity model

The first version should expose a second derived dimension:

- `BLOCK`
- `WARN`
- `INFO`

Recommended mapping:

- `DO_NOT_MOVE` -> `BLOCK`
- `REVIEW_REQUIRED` -> `WARN`
- `SAFE_TO_MOVE_EXTRAS` -> `INFO`
- `ALREADY_IN_BIN` -> `INFO`
- `EXPIRED_IN_BIN` -> `INFO`

This keeps recommendations readable without introducing a separate scoring system.

### Reason-code taxonomy

Reason codes must explain why the recommendation was produced. They are not the same thing as the recommendation label.

Naming convention:

- upper snake case
- short semantic phrases
- stable enough for read-model clients and future telemetry
- operator-facing codes should describe the condition, not the implementation detail

Recommended compact reason-code set:

| Code | Layer | Meaning |
| --- | --- | --- |
| `GROUP_ALREADY_IN_BIN` | operator-facing | group is already in active bin lifecycle |
| `BIN_RESTORE_EXPIRED` | operator-facing | restore window has expired |
| `CANONICAL_MAPPING_MISSING` | operator-facing | keep identity cannot be determined |
| `KEEP_COPY_UNHEALTHY` | operator-facing | keep copy is broken |
| `KEEP_COPY_SUSPECT` | operator-facing | keep copy is suspect |
| `KEEP_COPY_UNKNOWN` | operator-facing | keep copy exists but integrity truth is missing/incomplete |
| `SAFE_TO_MOVE_REVIEWED_DUPLICATES` | operator-facing | keep copy is healthy, review is favorable, and no warning-grade extra condition is present |
| `EXTRA_COPIES_UNHEALTHY_ONLY` | operator-facing | only extra copies are unhealthy; keep copy is healthy |
| `MIXED_EXTRA_HEALTH` | operator-facing | extras have mixed healthy and unhealthy conditions |
| `EXTRA_HEALTH_UNKNOWN` | operator-facing | extras lack complete integrity evidence |
| `REVIEW_REQUIRED_BY_OPERATOR_STATE` | operator-facing | human duplicate review is not in a move-approved state |
| `REVIEW_STALE` | operator-facing | duplicate review is stale against current group composition |
| `INTEGRITY_EVIDENCE_STALE` | operator-facing | integrity evidence is stale or incomplete |
| `NO_ACTIVE_EXTRAS` | technical/operator-details | nothing remains to move |

Reason-code usage rules:

- `primary_reason_code` remains mandatory in Phase 1
- primary UI surfaces should show friendly explanation text derived from these codes
- raw code strings may appear in details panels or diagnostics, but should not be the only operator explanation
- technical-only codes should be limited and should not dominate primary workflow screens
- new reason codes must be added to this accepted spec before or together with implementation; implementation-only taxonomy drift is not allowed

Condition -> reason -> explanation examples:

| Rule condition | Reason code(s) | Operator explanation |
| --- | --- | --- |
| keep copy is broken | `KEEP_COPY_UNHEALTHY` | Keep copy has playback issues. Do not move extras yet. |
| keep copy healthy, extras healthy | `SAFE_TO_MOVE_REVIEWED_DUPLICATES` | Keep copy is healthy and the group is approved for movement. |
| keep copy healthy, extras broken | `EXTRA_COPIES_UNHEALTHY_ONLY` | Keep copy is healthy. Some extras have playback issues, but extras can still move. |
| canonical mapping missing | `CANONICAL_MAPPING_MISSING` | The keep copy is not clearly identified yet. Resolve canonical selection first. |
| review no longer matches current group | `REVIEW_STALE` | This group changed since it was reviewed. Review it again before moving. |
| restore window expired | `BIN_RESTORE_EXPIRED` | This group is already in the bin and can no longer be restored. |

### Explicit decision matrix

The matrix below defines representative high-risk cases for implementation. It is not exhaustive, but it is normative for the listed scenarios.

| Keep status | Extra status | Integrity freshness | Review state/freshness | Lifecycle/bin state | Recommendation | Class | Reason codes | Operator explanation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| healthy | unhealthy only | fresh | `looks_right`, fresh | not in bin | `SAFE_TO_MOVE_EXTRAS` | `INFO` | `EXTRA_COPIES_UNHEALTHY_ONLY` | Keep copy is healthy. Extra copies can move even though some extras have playback issues. |
| broken | healthy | fresh | any | not in bin | `DO_NOT_MOVE` | `BLOCK` | `KEEP_COPY_UNHEALTHY` | The keep copy has playback issues. Do not move extras yet. |
| healthy | mixed | fresh | `looks_right`, fresh | not in bin | `REVIEW_REQUIRED` | `WARN` | `MIXED_EXTRA_HEALTH` | Extra copies have mixed health. Review before moving. |
| unknown | unhealthy | stale or missing | any | not in bin | `REVIEW_REQUIRED` | `WARN` | `KEEP_COPY_UNKNOWN`, `INTEGRITY_EVIDENCE_STALE` | Keep copy health is not confirmed yet. Refresh integrity evidence first. |
| identity missing | any | any | any | not in bin | `DO_NOT_MOVE` | `BLOCK` | `CANONICAL_MAPPING_MISSING` | The keep copy is not clearly identified. Resolve canonical mapping first. |
| healthy | healthy | stale | `looks_right`, fresh | not in bin | `REVIEW_REQUIRED` | `WARN` | `INTEGRITY_EVIDENCE_STALE` | Integrity results are stale. Refresh before moving. |
| healthy | healthy | fresh | `looks_right`, stale | not in bin | `REVIEW_REQUIRED` | `WARN` | `REVIEW_STALE` | The group changed since review. Review it again before moving. |
| any | any | any | any | active in bin, restore allowed | `ALREADY_IN_BIN` | `INFO` | `GROUP_ALREADY_IN_BIN` | This group is already in the bin. Manage it there instead of moving it again. |
| any | any | any | any | in bin, restore expired | `EXPIRED_IN_BIN` | `INFO` | `BIN_RESTORE_EXPIRED` | This group is already in the bin and the restore window has expired. |

## Separation Of Concerns

This layer must preserve three distinct concepts.

### 1. Human review state

Owned by `DuplicateGroupReview.review_status`.

Questions answered:

- does the operator believe this group is genuinely duplicate?
- has the operator reviewed the currently active group composition?

This is human intent, not system guidance.

### 2. Lifecycle/bin state

Owned by duplicate reclaim/bin persistence:

- `DuplicateReclaimRecord.reclaim_status`
- `DuplicateReclaimItem.item_status`
- `DuplicateReclaimItem.bin_state`
- item-level timing/path fields

Questions answered:

- are extras pending move, in bin, restored, recycled, or purged?
- is restore still allowed?

This is workflow fact, not recommendation.

### 3. System recommendation state

Owned by the future decision layer.

Questions answered:

- should the operator move extras now?
- should the operator hold for review?
- should movement be blocked?
- is the relevant operator action now bin management rather than review?

This must remain derived from human review plus lifecycle plus integrity facts.

The system must not collapse these into one persisted status blob.

## Ready for Bin semantics

`Ready for Bin` should be treated as a UI workflow bucket/filter, not as a new domain lifecycle state and not as a persisted recommendation state.

Recommended contract:

- not a lifecycle state
- not a persisted recommendation enum
- not a replacement for `review_status` or `bin_state`
- yes, a UI bucket derived from recommendation output

Operationally:

- a group appears in `Ready for Bin` when its recommendation is `SAFE_TO_MOVE_EXTRAS`
- a group does not appear there when its recommendation is `REVIEW_REQUIRED`, `DO_NOT_MOVE`, `ALREADY_IN_BIN`, or `EXPIRED_IN_BIN`

This stays compatible with current architecture and avoids overloading "Ready for Bin" into a fourth status system.

## Screen consumption contract

### Review Duplicates

This is the primary decisioning surface.

Primary recommendation signal:

- one prominent recommendation badge per duplicate group

Supporting explanation:

- one short explanation line derived from primary reason codes
- separate display of human review state

Technical evidence:

- keep copy health
- extra-copy health summary
- integrity counts
- stale review marker if applicable

Action behavior:

- move action enabled for `SAFE_TO_MOVE_EXTRAS`
- move action may use a warning affordance when `SAFE_TO_MOVE_EXTRAS` carries warning reason codes
- move action suppressed for `DO_NOT_MOVE`
- move action suppressed for `REVIEW_REQUIRED`

Do not duplicate:

- full playback issue detail
- recycle-bin lifecycle controls

### Ready for Bin

This is a derived workflow bucket over the recommendation layer.

Primary recommendation signal:

- `SAFE_TO_MOVE_EXTRAS` only

Supporting explanation:

- concise reason summary, especially when extras are unhealthy-only

Technical evidence:

- minimal keep/extra health summary
- do not foreground stale diagnostics because stale groups should not be in this bucket

Action behavior:

- move action enabled

Do not duplicate:

- groups with `REVIEW_REQUIRED`
- raw technical reason-code lists in the primary row
- recycle-bin management information

### Recycle Bin

This screen is lifecycle-first, not move-decision-first.

Primary recommendation signal:

- `ALREADY_IN_BIN` or `EXPIRED_IN_BIN`

Supporting explanation:

- restore eligibility
- retention expiry

Technical evidence:

- current bin location
- restore-expiry timing
- optional integrity context as supporting detail only

Action behavior:

- restore action enabled only when restore is still allowed
- move-to-bin action never shown here

Do not duplicate:

- duplicate-review guidance as if the group were still pending movement
- duplicate "safe to move" messaging

### Playback Issues

Playback Issues should remain integrity-first, but it should gain duplicate context rather than duplicate context taking over the page.

Primary recommendation signal:

- integrity status remains primary

Supporting explanation:

- whether the file is the keep copy or an extra copy
- duplicate-group recommendation, if one exists

Technical evidence:

- existing probe/decode/signal detail remains here

Action behavior:

- duplicate move actions should not be primary actions on this screen
- links back to Review Duplicates are preferred over embedding duplicate workflow controls

Do not duplicate:

- full duplicate-group review controls
- recycle-bin controls

## Proposed Read-Model Shape

The first implementation should add a derived read-model layer rather than a new persisted table.

For duplicate group reads, add derived fields such as:

- `duplicate_recommendation_state`
- `duplicate_recommendation_severity`
- `duplicate_recommendation_reason_codes`
- `duplicate_recommendation_primary_reason_code`
- `duplicate_recommendation_block_class`
- `duplicate_review_is_stale`
- `duplicate_integrity_is_stale`
- `keep_copy_identity_status`
- `keep_copy_integrity_status`
- `extra_copy_health_class`
- `healthy_extra_count`
- `suspect_extra_count`
- `broken_extra_count`

These should be computed in service/read paths close to current duplicate group assembly in [operator_console.py](/home/harish/projects/media-manager/media_manager/app/persistence/operator_console.py).

They should not replace:

- `review_status`
- `reclaim_status`
- `retention_expires_at`
- integrity detail views

## Implementation Strategy

### Phase 1: Derived read-model only

- add a recommendation computation helper over existing duplicate plus integrity facts
- expose derived recommendation fields on duplicate group read models
- do not persist recommendation state
- do not change planner/apply behavior

### Phase 2: UI surfacing in Review Duplicates and Ready for Bin

- display recommendation badge and explanation
- keep current review controls and integrity badges
- ensure warnings vs blockers are visually distinct

### Phase 3: Recycle Bin and Playback Issues context bridging

- add lifecycle-derived recommendation labels to Recycle Bin pages
- add duplicate recommendation context to Playback Issues detail where relevant

### Phase 4: Optional workflow gating refinement

- only after the recommendation layer proves stable, evaluate whether current `duplicate_reclaim_actionable` and `duplicate_reclaim_unavailable_reason` should be re-derived from the recommendation model
- do not do this in the first implementation slice

## Major Risks

- overloading the new recommendation state until it becomes a second workflow enum
- treating integrity counts as sufficient without distinguishing keep copy vs extra copies
- accidentally conflating operator review state with system recommendation
- surfacing recommendations as if they were automatic actions
- introducing hidden policy logic before the recommendation model is observable and testable

## Deferred Items

- persistence of recommendation state
- automatic movement blocking in planner/apply based on the recommendation layer
- richer integrity override semantics such as whether `MARK_OK` should downgrade `SUSPECT` or `BROKEN`
- UI redesign beyond adding recommendation signals to current pages
- any model/table renames
- exact heuristic for when integrity evidence counts as stale versus merely absent
- whether warnings on `SAFE_TO_MOVE_EXTRAS` should require explicit move confirmation in the UI

## Recommendation

Implement this next slice as a derived recommendation/read-model layer over existing duplicate, lifecycle, and integrity facts.

Do not start by persisting recommendation state.
Do not replace human review state.
Do not let lifecycle/bin state masquerade as operator guidance.

The first implementation should make recommendations visible and explainable before it is allowed to influence workflow gating.
