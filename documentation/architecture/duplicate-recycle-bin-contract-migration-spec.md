# Duplicate Recycle Bin Contract Migration Spec

## Status

Implementation-ready planning/specification document. This spec defines the staged migration from reclaim-shaped duplicate-removal API contracts toward bin-centered contracts without changing live behavior yet.

Related documents:

- [Duplicate Recycle Bin Lifecycle Simplification](duplicate-recycle-bin-lifecycle.md)
- [Duplicate Recycle Bin Migration Spec](duplicate-recycle-bin-migration-spec.md)

## Purpose

The duplicate-removal service boundary is already bin-centered internally, while public routes, payloads, and policy contracts remain reclaim-shaped in many places.

This spec defines how to migrate those public contracts safely.

Core rule:

- the **internal canonical model** is authoritative
- both legacy and future contract fields are projected from that canonical model
- neither reclaim fields nor future bin fields are inherently authoritative on their own

This is a contract projection migration, not a field-authority swap.

## Current Contract Inventory

### Current duplicate routes

Current live duplicate-removal routes include:

- `POST /api/duplicates/reclaim`
- `POST /api/duplicates/reclaim/execute`
- `GET /api/duplicates/reclaim/items`
- `POST /api/duplicates/reclaim/restore`
- `GET /api/duplicates/bin-policy`

Current route behavior:

- `POST /api/duplicates/reclaim/execute` already delegates internally to `duplicate_bin_execute(...)`
- `GET /api/duplicates/reclaim/items` already delegates internally to `duplicate_bin_items(...)`
- `POST /api/duplicates/reclaim/restore` already delegates internally to `duplicate_bin_restore(...)`
- `POST /api/duplicates/reclaim` still carries reclaim-shaped review-sync semantics and is not merely a move/restore alias

### Current duplicate payload surfaces

Current externally visible duplicate-removal payload fields include:

- `reclaim_status`
- `duplicate_reclaim_actionable`
- `duplicate_reclaim_unavailable_reason`
- `archive_path`
- `item_status`

These remain current contract names, but they should be treated as projections over the canonical model rather than as the canonical model itself.

### Current policy/config contract surfaces

Current externally visible policy/config shapes include:

- `duplicate_reclaim.archive_root`
- `duplicate_reclaim.default_retention_days`
- `duplicate_reclaim.notify_on_reviewed_safe`
- `duplicate_reclaim_archive_root`
- `duplicate_reclaim_default_retention_days`
- `duplicate_reclaim_notify_on_reviewed_safe`

The narrow duplicate read surface `GET /api/duplicates/bin-policy` already exists and should remain the current operator-truth endpoint during migration.

## Canonical Documentation Policy

As soon as bin routes are introduced:

- new documentation uses bin routes only
- reclaim routes are documented as compatibility-only
- no new first-party code should adopt reclaim routes

Before bin routes exist:

- current docs may still describe reclaim routes as current contracts
- those docs should already frame reclaim routes as transitional compatibility surfaces

## Route Migration Strategy

### Recommended route additions

Add bin-centered route aliases in a later implementation phase:

- `POST /api/duplicates/bin/move`
- `GET /api/duplicates/bin/items`
- `POST /api/duplicates/bin/restore`

These aliases should initially be behavior-identical to current reclaim routes and project from the same canonical model.

### Reclaim route posture

Keep these reclaim routes temporarily as compatibility routes:

- `POST /api/duplicates/reclaim/execute`
- `GET /api/duplicates/reclaim/items`
- `POST /api/duplicates/reclaim/restore`

These should be deprecated later, not removed immediately after bin aliases arrive.

### `POST /api/duplicates/reclaim`

This route is:

- **deferred pending review-contract redesign**

It should not receive an initial bin alias.

Reason:

- it is not simply a move/restore route
- it carries reclaim-shaped review-sync semantics
- a naive `/api/duplicates/bin/...` alias would blur review-decision semantics with bin lifecycle semantics

Until redesigned:

- keep it as a compatibility-only route
- do not promote it in new docs once bin routes exist

## Payload Migration Strategy

### Core approach

Keep reclaim-shaped payload fields temporarily while clients still depend on them.

Later, dual-project bin-centered aliases from the same internal canonical model. Do not treat either field family as authoritative.

Recommended strategy:

- translation happens at the API boundary
- clients may adopt new names incrementally
- legacy names remain available during migration
- persisted schema/state does not change in this phase

### Dual-projection rule

When bin-centered payload fields are introduced:

- emit both reclaim and bin names together for the supported transition period
- derive both from the internal canonical model
- do not define precedence where one external field is “more true” than the other

Structural rule for Phase 4 dual-support:

- the expected default is temporary top-level additive aliases
- new bin-centered fields are added beside existing reclaim-shaped fields in the same response shape during the transition period
- this avoids forcing an immediate serializer-shape rewrite on clients
- a future nested preferred structure may still be designed later, but that decision is explicitly deferred and must be settled before implementation if chosen
- Phase 4 implementation must not remain structurally ambiguous: it either uses top-level additive aliases as specified here or a separately approved serializer-shape amendment

### Semantic guardrails for future payload aliases

#### `bin_status`

- Exact meaning:
  - bin/lifecycle projection for a duplicate group during contract migration
- Represents:
  - state
- Persisted or computed:
  - computed/projected from the internal canonical model
- Scope:
  - group-level
- Expected value form:
  - enum-like string
  - nullable only if the canonical model cannot yet truthfully project a value for a current response shape during transition

#### `ready_for_bin`

- Exact meaning:
  - whether the duplicate group is currently eligible to be moved into the Recycle Bin
- Represents:
  - eligibility
- Persisted or computed:
  - computed/projected from the internal canonical model
- Scope:
  - group-level
- Expected value form:
  - boolean
  - non-null once introduced

#### `ready_for_bin_unavailable_reason`

- Exact meaning:
  - machine-readable explanation for why `ready_for_bin` is false
- Represents:
  - eligibility explanation, not state
- Persisted or computed:
  - computed/projected from the internal canonical model
- Scope:
  - group-level
- Expected value form:
  - enum-like string or `null`
  - `null` when `ready_for_bin` is true or when no reason is applicable

#### `bin_item_status`

- Exact meaning:
  - item-level bin/lifecycle projection for an individual duplicate item
- Represents:
  - state
- Persisted or computed:
  - computed/projected from the internal canonical model
- Scope:
  - item-level
- Expected value form:
  - enum-like string
  - nullable only if this alias is introduced before the canonical model can truthfully project an item-level value for all current response shapes
- Notes:
  - this alias remains optional
  - it should only be introduced if a concrete consumer need and mapped status semantics exist

### `archive_path` compatibility guardrail

- `archive_path` remains a compatibility-shaped field for now
- its current name likely reflects legacy archive/reclaim semantics more than the desired future bin-centered contract language
- it should not be used as the naming basis for future contract design without separate semantic clarification
- until that clarification exists, `archive_path` should be preserved as a compatibility surface rather than treated as a model for new bin-centered naming

### Field-family authority rule

The spec must not say:

- “legacy fields remain authoritative”
- “bin fields become authoritative at introduction time”

Instead:

- internal canonical model authoritative
- legacy and new fields both projected from canonical model
- no field-family-specific authority

## Policy / Config Contract Strategy

Policy/config contract migration should be handled separately from move/restore route migration.

Recommended path:

1. keep existing `duplicate_reclaim_*` and `duplicate_reclaim` policy payloads intact
2. continue using `GET /api/duplicates/bin-policy` as the narrow operator-truth read path
3. later introduce bin-centered policy read/write contracts for duplicate removal
4. migrate admin and frontend consumers together
5. only then deprecate reclaim-shaped policy payloads

Reason:

- policy contracts are tightly coupled to admin update flows
- combining policy rename with route alias rollout would widen compatibility risk unnecessarily

Naming rule for the future bin-centered policy contract:

- future policy contracts should use one coherent bin-centered namespace/structure
- flattened legacy `duplicate_reclaim_*` keys remain compatibility-only during migration
- Phase 5 must not introduce mixed ad hoc naming that combines new bin-centered names with unrelated legacy flattened naming patterns in the same first-party target contract

## Formal Compatibility Matrix

The following matrix defines the minimum controlled migration surface.

### Routes

| Current name | Future name | Phase introduced | Dual-supported? | Source of truth | Client impact | Removal precondition |
| --- | --- | --- | --- | --- | --- | --- |
| `POST /api/duplicates/reclaim/execute` | `POST /api/duplicates/bin/move` | Phase 2 | Yes | Internal canonical model | First-party clients can migrate incrementally to bin route | No supported clients rely on reclaim execute route |
| `GET /api/duplicates/reclaim/items` | `GET /api/duplicates/bin/items` | Phase 2 | Yes | Internal canonical model | Read clients can migrate without payload break | No supported clients rely on reclaim items route |
| `POST /api/duplicates/reclaim/restore` | `POST /api/duplicates/bin/restore` | Phase 2 | Yes | Internal canonical model | Restore clients can migrate incrementally | No supported clients rely on reclaim restore route |
| `POST /api/duplicates/reclaim` | Deferred pending review-contract redesign | Not introduced in initial bin-route phase | No | Internal canonical model | Review-sync clients remain on compatibility contract | Separate review-contract replacement approved and adopted |
| `GET /api/duplicates/bin-policy` | No rename in this phase | Already introduced | N/A | Internal canonical model | Remains narrow operator-truth endpoint | A later broader policy-contract redesign explicitly replaces it |

### Duplicate payload fields

| Current name | Future name | Phase introduced | Dual-supported? | Source of truth | Client impact | Removal precondition |
| --- | --- | --- | --- | --- | --- | --- |
| `reclaim_status` | `bin_status` | Phase 4 | Yes | Internal canonical model | Clients may read either field during transition | All supported clients migrated off `reclaim_status` |
| `duplicate_reclaim_actionable` | `ready_for_bin` | Phase 4 | Yes | Internal canonical model | Eligibility UI can migrate incrementally | All supported clients migrated off legacy actionable field |
| `duplicate_reclaim_unavailable_reason` | `ready_for_bin_unavailable_reason` | Phase 4 | Yes | Internal canonical model | Eligibility-explanation UI can migrate incrementally | All supported clients migrated off legacy unavailable-reason field |
| `archive_path` | No public rename initially | Not introduced in this phase | No | Internal canonical model | Current clients keep existing path semantics; field remains compatibility-shaped | Path semantics clarified enough to justify a public rename |
| `item_status` | `bin_item_status` only if later needed | Optional later phase after Phase 4 | Maybe | Internal canonical model | Item-level clients may continue using current field until justified alias exists | A concrete consumer need and fully mapped status semantics exist |

### Policy/config payload fields

| Current name | Future name | Phase introduced | Dual-supported? | Canonical source | Client impact | Removal precondition |
| --- | --- | --- | --- | --- | --- | --- |
| `duplicate_reclaim.archive_root` | future read contract uses a coherent nested bin-centered namespace | Phase 5 | Yes | Internal canonical model | Read consumers can migrate separately from routes | Admin and frontend policy readers migrated |
| `duplicate_reclaim.default_retention_days` | future write/update contract uses the same namespace pattern | Phase 5 | Yes | Internal canonical model | Read consumers can migrate separately from routes | Admin and frontend policy readers migrated |
| `duplicate_reclaim.notify_on_reviewed_safe` | later review/bin policy field if still needed | Phase 5 | Yes | Internal canonical model | Depends on whether concept survives redesign | Field meaning confirmed and all consumers migrated |
| `duplicate_reclaim_archive_root` | exact field names deferred to Phase 5 design | Phase 5 | Yes | Internal canonical model | Admin/update clients can migrate incrementally | Admin/update clients fully migrated |
| `duplicate_reclaim_default_retention_days` | exact field names deferred to Phase 5 design | Phase 5 | Yes | Internal canonical model | Admin/update clients can migrate incrementally | Admin/update clients fully migrated |
| `duplicate_reclaim_notify_on_reviewed_safe` | exact field names deferred to Phase 5 design if retained | Phase 5 | Yes | Internal canonical model | Depends on whether concept survives redesign | Admin/update clients fully migrated and field still needed |

## Phase Sequencing with Gates

### Phase 1: Contract migration spec

- Entry condition:
  - service boundary already bin-centered
  - no live contract changes yet
- Work performed:
  - write this spec
  - define the compatibility matrix
  - define documentation policy
- Exit condition:
  - route, payload, and policy migration sequence is decision-complete
- Rollback posture:
  - doc-only phase; no runtime rollback required

### Phase 2: Bin route alias introduction

- Entry condition:
  - this spec is approved
  - reclaim routes remain stable
- Work performed:
  - add bin move/items/restore aliases
  - keep behavior-identical parity with reclaim routes
  - keep validation-identical parity with reclaim routes
  - keep status-code-identical parity with reclaim routes
  - keep side-effect-identical parity with reclaim routes
  - implement aliases through shared handler/service logic rather than duplicated route-family business logic
  - do not change payloads yet
- Exit condition:
  - both route families operate correctly over the same canonical model
  - parity tests or equivalent proof exist for behavior, validation, status-code, and side-effect parity
- Rollback posture:
  - remove or disable new bin aliases while retaining reclaim routes

### Phase 3: Frontend first-party route cutover

- Entry condition:
  - bin route aliases exist
- Work performed:
  - switch first-party frontend/API helpers to bin routes
  - stop introducing reclaim routes in first-party code
- Exit condition:
  - no first-party frontend traffic depends on reclaim move/items/restore routes
  - no first-party helpers/default call sites for active UI flows point to reclaim move/items/restore routes
  - first-party docs/examples use bin routes
- Rollback posture:
  - frontend can fall back to reclaim routes because compatibility remains live

### Phase 4: Payload dual-projection

- Entry condition:
  - first-party route cutover complete or underway
- Work performed:
  - dual-project bin-centered response aliases as temporary top-level additive aliases beside reclaim-shaped fields
  - keep both field families projected from the canonical model
- Exit condition:
  - first-party clients can read bin-centered names without breakage
- Rollback posture:
  - stop emitting new aliases; legacy fields remain available

### Phase 5: Policy/config contract migration

- Entry condition:
  - move/restore route migration is stable
- Work performed:
  - introduce bin-centered policy read/write contracts
  - migrate admin and frontend consumers together
- Exit condition:
  - first-party policy consumers no longer depend on reclaim-shaped names
- Rollback posture:
  - retain reclaim-shaped policy contract until the new contract is stable

### Phase 6: Deprecation enforcement

- Entry condition:
  - first-party code fully off reclaim move/items/restore routes
  - compatibility usage audited
- Work performed:
  - mark reclaim move/items/restore routes and fields deprecated
  - stop documenting reclaim routes as primary
  - treat reclaim routes as compatibility-only
- Exit condition:
  - reclaim contracts are compatibility-only in practice and documentation
- Rollback posture:
  - continue dual support longer; do not remove compatibility yet

### Phase 7: Compatibility removal

- Entry condition:
  - explicit proof that no supported clients require reclaim contracts
  - policy and payload migrations complete
- Work performed:
  - remove reclaim route aliases and reclaim-shaped contract fields in a deliberate breaking-change phase
- Exit condition:
  - public duplicate-removal contract is bin-centered only
- Rollback posture:
  - this is the first materially breaking phase; if needed, restore compatibility aliases in a follow-up release

## Major Compatibility Risks and Deferred Items

- `POST /api/duplicates/reclaim` remains unresolved until review-contract redesign is specified
- policy/config contract migration is tightly coupled to admin update paths and should remain separate from route alias rollout
- shared frontend types should not be globally renamed until payload dual-projection exists
- route migration without explicit documentation policy risks new first-party code adopting compatibility routes
- payload migration without the compatibility matrix risks partial dual-support and ambiguous client behavior
- `archive_path` and `item_status` should not be renamed casually at the contract layer without stronger semantic clarification

## Non-Goals of This Spec

This spec does not:

- rename live routes
- change live payloads
- rename schema or persistence fields
- redesign review-contract semantics
- implement deprecation enforcement yet

## Implementation Note

When this spec is implemented in future phases:

- bin routes should be additive first
- reclaim routes should remain temporarily as compatibility routes
- no new first-party code should adopt reclaim routes once bin routes exist
