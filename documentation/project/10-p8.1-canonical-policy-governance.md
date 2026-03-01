# Phase 8.1: Canonical Policy Governance (Design)

## Purpose
Define a deterministic canonical selection abstraction that preserves Phase 7 identity guarantees and Phase 8 execution determinism.

This phase is design-first. No automatic recanonicalization behavior is introduced.

## Scope and Boundaries

In scope:
1. Canonical policy interface and deterministic strategy rules.
2. Default policy parity (`FIRST_SEEN`) with no behavior change.
3. Optional root-preference strategy with explicit fallback.
4. Structured explanation output for visibility and debugging.
5. Determinism test matrix.

Out of scope:
1. Silent reassignment of existing canonicals.
2. Runtime randomization or input-order-dependent selection.
3. Planner/apply side effects inside policy logic.
4. Implicit policy-driven DB mutation.

## Canonical Policy Responsibility

Canonical policy answers one pure question:

Given all `file_instances` for one `content_id`, which instance is canonical?

Required properties:
1. Deterministic.
2. Stateless.
3. Pure.
4. Explainable.

## Proposed Abstraction

```python
class CanonicalPolicy(Protocol):
    name: str
    version: str

    def select(
        self,
        instances: list[FileInstance],
        context: CanonicalContext,
    ) -> FileInstance: ...

    def explain(
        self,
        instances: list[FileInstance],
        selected: FileInstance,
        context: CanonicalContext,
    ) -> dict[str, Any]: ...
```

```python
@dataclass(frozen=True)
class CanonicalContext:
    preferred_roots: tuple[str, ...] = ()
```

Notes:
1. Policy layer has no DB access.
2. Policy layer performs no writes.
3. Caller provides already-loaded instances.

## Policy Set (Phase 8.1)

### FIRST_SEEN v1 (default)

Ordering:
1. `created_at ASC`
2. `file_instance_id ASC` (required deterministic tie-break)

Result:
1. Select first row after full sort.
2. Preserve current behavior.

### PREFER_ROOT v1

Inputs:
1. `preferred_roots` from config.

Rule:
1. Normalize paths and roots.
2. Partition into matching and non-matching sets by prefix.
3. If matches exist, apply FIRST_SEEN ordering within matches.
4. Else fallback to FIRST_SEEN across all instances.

## Config and Factory

Environment (example):

```text
MEDIA_CANONICAL_POLICY=FIRST_SEEN
MEDIA_PREFERRED_ROOTS=/Archive,/Media
```

Factory:

```python
def build_canonical_policy(config) -> CanonicalPolicy: ...
```

Constraints:
1. No plugin system.
2. No dynamic imports.
3. Unknown policy value is a hard validation error.

## Application Points

Policy is applied at:
1. Ingestion-time canonical assignment decisions.
2. Duplicate visibility/reporting commands that need explain output.

Policy is not applied to:
1. Silent retroactive reassignment.
2. Per-plan dynamic recomputation that can drift with config changes.

## Policy Change Semantics

Rule:
1. Policy changes do not auto-mutate existing canonical assignments.
2. Re-canonicalization is explicit and operator-invoked.

Future command shape (target: Phase 8.2+):

```bash
media-manager canonical recompute --policy PREFER_ROOT --dry-run
media-manager canonical recompute --policy PREFER_ROOT --apply
```

## Determinism Safeguards

Every policy must:
1. Fully sort candidates before selecting.
2. Ignore input list order.
3. Include `file_instance_id` as final tie-break.
4. Use only stable attributes.

## Test Requirements

Minimum deterministic tests:
1. Shuffled input order returns same selected canonical.
2. Multiple matching roots remain stable.
3. No-root-match fallback uses FIRST_SEEN behavior.
4. Repeated calls with identical input return identical output.
5. Explain payload is stable and matches selected ID.

## Phase 8.1 Deliverables

1. `CanonicalPolicy` interface.
2. `FIRST_SEEN v1` implementation.
3. `PREFER_ROOT v1` implementation.
4. Policy factory and config mapping.
5. Duplicate visibility output with `--explain` support.
6. Determinism tests.

## Deferred to Phase 8.2+

1. Explicit recanonicalization command execution.
2. Optional append-only canonical assignment history model.
3. Manual override layer above policy decisions.
