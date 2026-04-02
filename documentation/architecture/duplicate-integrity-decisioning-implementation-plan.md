# Duplicate-to-Integrity Decisioning Implementation Plan

## Status

Implementation-planning only. This document converts the accepted recommendation model in [Duplicate-to-Integrity Decisioning Spec](duplicate-integrity-decisioning-spec.md) into a code-adjacent integration plan. It does not implement runtime logic, API changes, persistence changes, or UI behavior changes by itself.

## Purpose

This plan defines the first safe implementation seam for duplicate-to-integrity recommendationing in the current Media Manager architecture.

It answers:

- where recommendation derivation should live
- which current read paths should consume it
- what derived output shape should be produced
- how duplicate and integrity screens should consume that output incrementally
- what should stay deferred until the read-model-first slice proves stable

## Accepted Source Of Truth

The recommendation model is defined in [Duplicate-to-Integrity Decisioning Spec](duplicate-integrity-decisioning-spec.md).

That document is authoritative for:

- recommendation labels
- precedence
- hard block vs review-required semantics
- staleness handling
- reason-code taxonomy
- `Ready for Bin` semantics
- screen-level UX intent

This implementation plan does not redefine those rules. It maps them onto the current codebase.

## Current Architecture Touchpoints

The current implementation already has clear read-model assembly points for duplicate, bin, and integrity surfaces.

### Backend duplicate review / duplicate groups

Primary current backend touchpoints:

- [media_manager/app/persistence/operator_console.py](/home/harish/projects/media-manager/media_manager/app/persistence/operator_console.py)
  - `DuplicateGroupItem`
  - `OperatorConsoleReadService.get_duplicate_groups()`
- [media_manager/app/service_layer/reads.py](/home/harish/projects/media-manager/media_manager/app/service_layer/reads.py)
  - `ReadFacade.duplicates()`

Current responsibilities in `get_duplicate_groups()`:

- load duplicate content IDs
- load canonical mapping and duplicate review rows
- load `DuplicateReclaimRecord` and `DuplicateReclaimItem`
- aggregate integrity counts from `IntegrityCheck`
- derive current `duplicate_reclaim_actionable` and `duplicate_reclaim_unavailable_reason`
- emit `DuplicateGroupItem`

This is the natural existing seam for group-level recommendation derivation.

### Backend ready-for-bin behavior

There is no separate backend "ready for bin" read path today. Current readiness is split across:

- `DuplicateGroupItem.duplicate_reclaim_actionable`
- `DuplicateGroupItem.duplicate_reclaim_unavailable_reason`
- frontend filtering in [operator_console/gui_app/src/pages/DuplicatesPage.tsx](/home/harish/projects/media-manager/operator_console/gui_app/src/pages/DuplicatesPage.tsx)
  - `deriveActionableReadyGroups(...)`
  - `isPendingRemovalStatus(...)`

This means current "Ready for Bin" semantics are partly server-derived and partly frontend-derived.

### Backend recycle-bin / retention reads

Primary backend touchpoints:

- [media_manager/app/persistence/operator_console.py](/home/harish/projects/media-manager/media_manager/app/persistence/operator_console.py)
  - `OperatorConsoleReadService.get_duplicate_reclaim_archive_page()`
  - `OperatorConsoleReadService.get_retention_recycle_page()`
- [media_manager/app/service_layer/reads.py](/home/harish/projects/media-manager/media_manager/app/service_layer/reads.py)
  - `ReadFacade.duplicate_bin_items()`
  - `ReadFacade.retention_recycle_items()`

These already expose authoritative duplicate-bin lifecycle facts but do not add recommendation context.

### Backend integrity / playback issue reads

Primary backend touchpoints:

- [media_manager/app/persistence/operator_console.py](/home/harish/projects/media-manager/media_manager/app/persistence/operator_console.py)
  - `IntegrityIssueItem`
  - `OperatorConsoleReadService.get_integrity_issue_page()`
  - `OperatorConsoleReadService.get_integrity_file_detail()`
- [media_manager/app/service_layer/reads.py](/home/harish/projects/media-manager/media_manager/app/service_layer/reads.py)
  - `ReadFacade.integrity_issues()`
  - `ReadFacade.integrity_file_detail()`

These reads are integrity-first today and do not join duplicate-group recommendation context.

### Current duplicate review state inputs

Relevant persisted sources:

- `DuplicateGroupReview.review_status`
- `DuplicateGroupReview.group_signature`
- `DuplicateGroupReview.reviewed_canonical_instance_id`

Current read-model staleness fields already surfaced in `DuplicateGroupItem`:

- `is_stale`
- `stale_reason`

### Current integrity evidence inputs

Relevant persisted sources:

- `IntegrityCheck.status`
- `IntegrityCheck.last_checked_at`
- `IntegrityReviewDecision.decision`
- `IntegritySignal`

Current read models:

- duplicate groups only expose coarse integrity counts
- integrity issue pages expose file-level status, confidence, and review decision

### Current lifecycle/bin inputs

Relevant persisted sources:

- `DuplicateReclaimRecord.reclaim_status`
- `DuplicateReclaimItem.item_status`
- `DuplicateReclaimItem.bin_state`
- `DuplicateReclaimItem.restore_expires_at`
- `DuplicateReclaimItem.recycle_path`
- `DuplicateReclaimItem.bin_path`

Current lifecycle read paths:

- duplicate groups expose `reclaim_status` and `retention_expires_at`
- duplicate bin page exposes archive/bin items
- retention recycle page exposes current lifecycle rows

### Frontend DTO / mapping touchpoints

Current GUI integration points:

- [operator_console/gui_app/src/types/media.ts](/home/harish/projects/media-manager/operator_console/gui_app/src/types/media.ts)
  - `DuplicateGroup`
  - `IntegrityIssue`
- [operator_console/gui_app/src/lib/api/mappers/media.ts](/home/harish/projects/media-manager/operator_console/gui_app/src/lib/api/mappers/media.ts)
  - duplicate group mapping from backend JSON
- [operator_console/gui_app/src/pages/DuplicatesPage.tsx](/home/harish/projects/media-manager/operator_console/gui_app/src/pages/DuplicatesPage.tsx)
  - current readiness filtering and action enablement

These are the exact client seams that would consume additive recommendation fields later.

## Recommended Architecture Seam

### Recommendation

The first implementation should derive recommendation state in the backend read-model layer, centered in [media_manager/app/persistence/operator_console.py](/home/harish/projects/media-manager/media_manager/app/persistence/operator_console.py).

### Why backend read-model derivation is the right first seam

Reasons:

- the required inputs already meet in `OperatorConsoleReadService.get_duplicate_groups()`
- the accepted spec explicitly treats recommendation as derived read-model output, not persisted authority
- duplicating the same derivation in `DuplicatesPage.tsx`, recycle-bin views, and playback-issues views would create drift immediately
- backend derivation keeps the precedence model and reason-code taxonomy authoritative in one place
- frontend can stay additive and presentation-focused

### Recommended shape of the seam

Add one central derivation module in the backend persistence/service read layer, for example:

- `media_manager/app/persistence/duplicate_integrity_recommendations.py`

Recommended contents of that module later:

- one central derivation function that accepts group-level facts and returns a structured recommendation object
- small helper functions for:
  - keep-copy classification
  - extra-copy health classification
  - staleness classification
  - lifecycle recommendation override
  - reason-code assembly

Recommended top-level function shape later:

- `derive_duplicate_recommendation(group_facts) -> DuplicateRecommendation`

### Why not frontend-only derivation

Frontend-only derivation is the weaker option because:

- it would require reproducing duplicate/integrity joins in the UI that the backend already owns
- playback issues and duplicate screens would likely diverge in rule interpretation
- it would force the frontend to interpret technical lifecycle and integrity combinations that are already assembled server-side

### Why not API-layer-only derivation

Placing derivation only in `ReadFacade` is also weaker than placing it beneath that layer because:

- `ReadFacade` is a thin serialization facade today
- putting rule logic there would couple HTTP/read transport to decision semantics
- `OperatorConsoleReadService` is already the real read-model assembly layer

## Proposed Derived Output Contract

The recommendation contract should be a derived object, not a new persisted entity.

### Recommended backend object shape

Proposed backend dataclass or typed mapping later:

```python
{
  "state": "SAFE_TO_MOVE_EXTRAS",
  "classification": "INFO",
  "primary_reason_code": "EXTRA_COPIES_UNHEALTHY_ONLY",
  "reason_codes": [
    "EXTRA_COPIES_UNHEALTHY_ONLY"
  ],
  "operator_explanation": "Keep copy is healthy. Some extras have playback issues, but extras can still move.",
  "review_is_stale": false,
  "integrity_is_stale": false,
  "lifecycle_context": {
    "already_in_bin": false,
    "restore_expired": false
  },
  "keep_summary": {
    "identity_status": "KNOWN",
    "integrity_status": "OK"
  },
  "extra_summary": {
    "health_class": "EXTRAS_ALL_UNHEALTHY",
    "healthy_count": 0,
    "suspect_count": 1,
    "broken_count": 2,
    "unknown_count": 0
  }
}
```

### Field guidance

Operator-facing fields:

- `state`
- `classification`
- `primary_reason_code`
- `operator_explanation`

Supporting but still safe to expose:

- `reason_codes`
- `review_is_stale`
- `integrity_is_stale`
- `keep_summary.integrity_status`
- `extra_summary.health_class`
- `extra_summary` counts
- `lifecycle_context.already_in_bin`
- `lifecycle_context.restore_expired`

Technical/internal fields that may remain backend-only in the first slice if desired:

- any intermediate rule trace
- raw integrity check IDs used to derive the summary
- raw canonical mapping diagnostics beyond the public reason code

### Proposed API-safe additive contract shapes

#### Duplicate review group row

Recommended additive extension to current duplicate-group payload:

```json
{
  "group_id": "content-uuid",
  "review_status": "looks_right",
  "reclaim_status": "UNREVIEWED",
  "duplicate_reclaim_actionable": true,
  "duplicate_reclaim_unavailable_reason": null,
  "integrity_broken_count": 2,
  "integrity_suspect_count": 1,
  "duplicate_recommendation": {
    "state": "SAFE_TO_MOVE_EXTRAS",
    "classification": "INFO",
    "primary_reason_code": "EXTRA_COPIES_UNHEALTHY_ONLY",
    "reason_codes": ["EXTRA_COPIES_UNHEALTHY_ONLY"],
    "operator_explanation": "Keep copy is healthy. Some extras have playback issues, but extras can still move.",
    "review_is_stale": false,
    "integrity_is_stale": false,
    "keep_summary": {
      "identity_status": "KNOWN",
      "integrity_status": "OK"
    },
    "extra_summary": {
      "health_class": "EXTRAS_ALL_UNHEALTHY",
      "healthy_count": 0,
      "suspect_count": 1,
      "broken_count": 2,
      "unknown_count": 0
    },
    "lifecycle_context": {
      "already_in_bin": false,
      "restore_expired": false
    }
  }
}
```

#### Ready-for-bin row

No separate backend row type is required first. The frontend can derive the bucket from duplicate-group rows when:

- `duplicate_recommendation.state == "SAFE_TO_MOVE_EXTRAS"`

If a future dedicated backend ready-list is added, it can reuse the same nested `duplicate_recommendation` object.

#### Recycle-bin row

Recommended additive contract for archive/bin rows later:

```json
{
  "file_instance_id": "file-uuid",
  "content_id": "content-uuid",
  "item_status": "ARCHIVED",
  "archive_path": "/bin/duplicates/...",
  "expires_at": "2026-04-09T00:00:00+00:00",
  "duplicate_recommendation": {
    "state": "ALREADY_IN_BIN",
    "classification": "INFO",
    "primary_reason_code": "GROUP_ALREADY_IN_BIN",
    "reason_codes": ["GROUP_ALREADY_IN_BIN"],
    "operator_explanation": "This group is already in the bin. Manage it there instead of moving it again.",
    "lifecycle_context": {
      "already_in_bin": true,
      "restore_expired": false
    }
  }
}
```

#### Playback-issues row with duplicate context

Recommended additive contract for integrity issue rows later:

```json
{
  "check_id": "check-uuid",
  "file_instance_id": "file-uuid",
  "status": "BROKEN",
  "absolute_path": "/library/copy.jpg",
  "duplicate_context": {
    "content_id": "content-uuid",
    "is_keep_copy": false,
    "is_extra_copy": true,
    "duplicate_recommendation": {
      "state": "SAFE_TO_MOVE_EXTRAS",
      "classification": "INFO",
      "primary_reason_code": "EXTRA_COPIES_UNHEALTHY_ONLY",
      "operator_explanation": "Keep copy is healthy. Some extras have playback issues, but extras can still move."
    }
  }
}
```

## Read-Path Integration Strategy

### Duplicate review read model

Recommended approach:

- compute recommendation on the backend in `OperatorConsoleReadService.get_duplicate_groups()`
- attach the derived contract server-side to `DuplicateGroupItem`
- serialize it through existing `ReadFacade.duplicates()`
- map it in `operator_console/gui_app/src/lib/api/mappers/media.ts`

Why:

- all group-level facts already converge in `get_duplicate_groups()`
- this avoids a second client-side heuristic for "Ready for Bin"
- this creates one authoritative recommendation source for duplicate review and ready views

Minimum change path later:

1. add recommendation dataclass/type on the backend
2. add `duplicate_recommendation` field to `DuplicateGroupItem`
3. derive recommendation in `get_duplicate_groups()`
4. pass through existing `ReadFacade.duplicates()`
5. add additive GUI type/mapping fields

Performance considerations:

- current `get_duplicate_groups()` already performs group-wide joins and aggregations
- recommendation derivation should be computed per loaded group in memory
- avoid extra per-row DB queries by deriving from already loaded duplicate and integrity rows

### Ready-for-bin integration

Recommended approach:

- do not create a new backend endpoint first
- keep "Ready for Bin" as a frontend bucket derived from duplicate groups
- replace existing frontend heuristics gradually so the bucket keys off `duplicate_recommendation.state`

Why:

- current architecture already treats ready-for-bin as a view over duplicate groups
- this avoids introducing a parallel read endpoint before the recommendation contract stabilizes

Risk to avoid:

- duplicating recommendation derivation in the frontend

Mitigation:

- frontend should consume the server-provided recommendation object and only filter/sort with it

### Recycle-bin read model

Recommended approach:

- compute lightweight lifecycle-derived recommendation context on the backend
- attach additive recommendation output to:
  - `get_duplicate_reclaim_archive_page()`
  - `get_retention_recycle_page()`

Minimum change path later:

- use existing lifecycle facts already assembled in these methods
- do not reuse duplicate-review logic blindly; use the central derivation module with a lifecycle-aware adapter

Why:

- recycle-bin screens need only the lifecycle-derived subset first
- they should not repeat the full duplicate review recommendation logic in the UI

### Playback issues read model

Recommended approach:

- keep integrity issue reads integrity-first
- attach duplicate recommendation context server-side only when the file belongs to a duplicate group
- do this as an additive nested object rather than flattening duplicate fields into the integrity DTO

Minimum change path later:

- add a duplicate-context join/lookup inside:
  - `get_integrity_issue_page()`
  - `get_integrity_file_detail()`
- include only:
  - duplicate group identity
  - keep vs extra role
  - recommendation summary

Why:

- this keeps Playback Issues focused
- it avoids forcing the UI to re-join duplicate recommendation data client-side

Performance considerations:

- this is the most expensive read-path extension in this slice
- initial implementation should batch by content/file IDs rather than do per-issue lookups

## Screen Consumption Mapping

### Review Duplicates

Needs:

- full `duplicate_recommendation` object
- keep/extra summary
- staleness markers

Optional in first UI slice:

- secondary reason-code list
- expanded technical evidence panel

Minimal initial integration:

- badge from `duplicate_recommendation.state`
- one explanation line from `operator_explanation`
- existing review controls remain unchanged

Keep hidden initially:

- raw full reason-code array unless shown in expandable details
- technical derivation trace

### Ready for Bin

Needs:

- `duplicate_recommendation.state`
- `classification`
- `operator_explanation`
- top-level keep/extra health summary if available

Optional:

- reason codes in expandable details

Minimal initial integration:

- bucket/filter only groups with `SAFE_TO_MOVE_EXTRAS`
- keep existing move action flow
- optionally show warning accent when the recommendation is positive but reason codes indicate unhealthy extras

Can wait:

- custom backend ready-for-bin endpoint
- detailed evidence panel

### Recycle Bin

Needs:

- lifecycle-derived recommendation state
- restore-expired flag/context
- concise explanation

Optional:

- supporting integrity context

Minimal initial integration:

- label rows/groups as `ALREADY_IN_BIN` or `EXPIRED_IN_BIN`
- do not show move-stage recommendations here

Can wait:

- full duplicate review context inside recycle-bin screens

### Playback Issues

Needs:

- duplicate context only when applicable
- keep/extra role
- recommendation summary

Optional:

- reason codes
- link back to duplicate group

Minimal initial integration:

- add duplicate context badge or side panel summary
- keep integrity evidence as the primary content

Can wait:

- embedded duplicate actions
- full duplicate recommendation evidence breakdown

## Incremental Rollout Plan

### Phase 1: Backend derivation seam and duplicate-group read-model integration

Likely code areas:

- [media_manager/app/persistence/operator_console.py](/home/harish/projects/media-manager/media_manager/app/persistence/operator_console.py)
- new backend helper module, recommended:
  - `media_manager/app/persistence/duplicate_integrity_recommendations.py`
- [media_manager/app/service_layer/reads.py](/home/harish/projects/media-manager/media_manager/app/service_layer/reads.py)
- backend tests near:
  - [media_manager/tests/test_operator_console_duplicates.py](/home/harish/projects/media-manager/media_manager/tests/test_operator_console_duplicates.py)

Expected change type later:

- additive read-model derivation only
- no persistence changes
- no planner/apply changes

Docs/tests:

- update the decisioning spec only if implementation reveals mismatch
- add unit and operator-read-model tests

Rollback/safety:

- low risk
- recommendation fields can be removed from response shape without touching persistence

### Phase 2: Expose recommendation on Review Duplicates and Ready for Bin

Likely code areas:

- [operator_console/gui_app/src/types/media.ts](/home/harish/projects/media-manager/operator_console/gui_app/src/types/media.ts)
- [operator_console/gui_app/src/lib/api/mappers/media.ts](/home/harish/projects/media-manager/operator_console/gui_app/src/lib/api/mappers/media.ts)
- [operator_console/gui_app/src/pages/DuplicatesPage.tsx](/home/harish/projects/media-manager/operator_console/gui_app/src/pages/DuplicatesPage.tsx)
- GUI tests near:
  - [operator_console/gui_app/src/test/duplicates-page.test.tsx](/home/harish/projects/media-manager/operator_console/gui_app/src/test/duplicates-page.test.tsx)

Expected change type later:

- additive display contract
- frontend bucket/filter updates to use derived recommendation instead of local heuristics where appropriate

Out of scope:

- planner/apply gating
- workflow redesign

Rollback/safety:

- UI-only fallback to existing `duplicate_reclaim_actionable` remains possible during transition

### Phase 3: Extend recommendation context into Recycle Bin and Playback Issues

Likely code areas:

- [media_manager/app/persistence/operator_console.py](/home/harish/projects/media-manager/media_manager/app/persistence/operator_console.py)
- [media_manager/app/service_layer/reads.py](/home/harish/projects/media-manager/media_manager/app/service_layer/reads.py)
- frontend duplicate/bin and integrity page types/mappers/pages

Expected change type later:

- additive nested recommendation context on archive/bin and integrity DTOs
- no persistence changes

Out of scope:

- autoplay/automation
- policy changes

Rollback/safety:

- additive contract can be hidden in UI without disturbing current workflows

### Phase 4: Explicitly deferred future gating review

Potential future code areas:

- duplicate planning/apply services
- possibly policy or operations service layers

This phase stays deferred unless explicitly approved later.

Possible future questions:

- whether `duplicate_reclaim_actionable` should be re-derived from recommendation state
- whether planner should refuse moves for `DO_NOT_MOVE`
- whether automation should ever consume recommendation output

Out of scope for the first implementation:

- hidden gating
- persistence of recommendation output
- planner/apply enforcement

## Testing Strategy For Later Implementation

### Pure recommendation unit tests

Recommended future location:

- new backend unit test file near persistence/read-model tests, for example:
  - `media_manager/tests/test_duplicate_integrity_recommendations.py`

These should cover:

- precedence rules
- keep/extra health classification
- lifecycle override states
- reason-code assembly

### Precedence and stale-evidence cases

Recommended coverage:

- `EXPIRED_IN_BIN` beats `ALREADY_IN_BIN`
- `DO_NOT_MOVE` beats `REVIEW_REQUIRED`
- `REVIEW_REQUIRED` beats `SAFE_TO_MOVE_EXTRAS`
- stale review downgrades otherwise-safe groups
- stale integrity evidence downgrades otherwise-safe groups

### Read-model/API contract tests

Recommended future locations:

- [media_manager/tests/test_operator_console_duplicates.py](/home/harish/projects/media-manager/media_manager/tests/test_operator_console_duplicates.py)
- [media_manager/tests/test_service_layer_reads.py](/home/harish/projects/media-manager/media_manager/tests/test_service_layer_reads.py)

These should cover:

- additive recommendation fields appear on duplicate group payloads
- existing duplicate-group fields remain stable
- recycle-bin and integrity payloads gain only additive context

### Frontend mapper and rendering tests

Recommended future locations:

- [operator_console/gui_app/src/test/duplicates-page.test.tsx](/home/harish/projects/media-manager/operator_console/gui_app/src/test/duplicates-page.test.tsx)
- frontend tests for any playback-issues page consuming duplicate context

These should cover:

- recommendation badge rendering
- Ready for Bin filtering based on derived recommendation
- warning vs blocked display treatment
- no regression in existing duplicate move flows

### Regression checks for duplicate/bin workflow stability

Existing backend suites that should remain green:

- [media_manager/tests/test_phase3_duplicate_reclaim.py](/home/harish/projects/media-manager/media_manager/tests/test_phase3_duplicate_reclaim.py)
- [media_manager/tests/test_operator_console_duplicates.py](/home/harish/projects/media-manager/media_manager/tests/test_operator_console_duplicates.py)

Implementation must prove:

- no planner/apply behavior changed
- no persistence contract changed unexpectedly
- no hidden gating was introduced

## Risks And Deferred Items

### Major implementation risks

- recommendation drift across screens if derivation is duplicated between backend and frontend
- duplicated logic between duplicate groups, recycle-bin rows, and playback issues if no central derivation helper is created
- stale evidence causing confusing recommendation churn if freshness rules are not exposed clearly
- overexposing technical reason codes directly in the operator UI
- accidental hidden gating if recommendation labels start driving planner/apply before explicit approval
- performance degradation if playback issue screens recompute duplicate context with per-row lookups

### What should not be done in the first implementation slice

- do not persist recommendation state
- do not add database fields or migrations
- do not add a second workflow enum family
- do not redesign duplicate/bin UI around a new information architecture
- do not move recommendation derivation into multiple screen-local heuristics
- do not let recommendation output silently change planner/apply eligibility

### Deferred items

- any planner/apply gating
- recommendation persistence
- integrity-override semantics beyond the accepted spec
- automation or policy-driven use of recommendation output
- any rename or cleanup work outside additive read-model integration

## Recommendation

The first safe implementation seam is:

- one central backend recommendation derivation helper
- consumed first by `OperatorConsoleReadService.get_duplicate_groups()`
- surfaced additively through existing read facades and frontend mappers
- reused later by recycle-bin and playback-issues read paths through backend adapters, not frontend recomputation

This approach fits the current Media Manager architecture best because it is:

- additive
- read-model-first
- low-risk to persistence and workflow behavior
- consistent with current Operator Console read assembly patterns
