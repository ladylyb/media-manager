# API-Only Transition

This document records the supported architecture after the CLI-to-API migration.
The repository is already beyond the historical "freeze the CLI" stage: the CLI
has been removed from the supported product surface, and the remaining
compatibility notes in this document refer to HTTP routes only.

## Migration Matrix

Already API-backed and supported:

- `plan` -> `POST /api/plan`
- `apply` -> `POST /api/apply`
- `ingest` -> `POST /api/ingest`
- `canonical recompute` -> `POST /api/canonical/recompute`
- policy read/update -> `GET/POST /api/policy`
- run history and status -> `/api/status`, `/api/runs`, `/api/operation-runs`
- tag enrichment -> `POST /api/tag-enrichment`
- admin reset -> `POST /api/admin/db-reset`
- hash audit -> `GET /api/admin/hash-audit`

Compatibility removals completed:

- `/api/v1/*` has been removed.
- `/api/v2/*` has been removed.

Legacy CLI-only and removed from the supported interface:

- `legacy-import`
- `perf-run`, `perf-compare`, `perf-refresh-baseline`
- `refresh-mv`
- `planner-benchmark`
- `observability-quick-check`
- `explain-file`
- `health-check`
- `db-reset` CLI wrapper

The remaining perf helpers are internal legacy tooling only and are not part of
the supported application interface.

Supported first-party clients:

- `operator_console/gui_app/` is the supported GUI integration layer and calls the REST API only.
- `tools/e2e_workflow_sanity.sh` is the supported API-client workflow smoke harness.

Unsupported runtime client surfaces:

- `operator_console/gui_upstream/` is an immutable upstream snapshot, not a deployable contract layer.
- legacy direct benchmark scripts have been removed; benchmark execution now flows through the admin API plus benchmark worker.

## Supported Architecture

The supported runtime shape is:

`API route/controller -> service layer -> persistence/core -> database/filesystem gating`

Rules:

- Route handlers stay thin and do not implement planner/apply business logic.
- Service-layer mutations remain responsible for operation logging, validation, cache invalidation, and durable boundaries.
- Planner and apply semantics remain unchanged: planning is side-effect free with respect to filesystem writes, and apply only executes after DB gating.

## Invariant Risks Reviewed

- Filesystem gating: unchanged, because `ApplyService` still owns gated filesystem mutation.
- Planner purity: preserved, because HTTP routes delegate to `OperationServices.plan()` and then to `PlanningService`.
- Idempotency and resume safety: preserved, because API-triggered operations still use the same run and operation-run persistence services.
- Failure durability: preserved, because route handlers only wrap service calls; failures still flow through the existing persistence-backed failure paths.

## Operational Defaults

- The REST API is the only supported application interface.
- The GUI, admin tooling, and automation are expected to call `/api/*`.
- The packaged Python CLI has been removed from the supported product surface.

## Migration Summary

Removed:

- packaged CLI entrypoint and supported CLI module surface
- CLI-focused tests and CLI-first documentation
- `/api/v1/*` compatibility surface

Kept:

- service-layer-backed FastAPI application under `/api/*`
- operator console and API-client tooling

Temporary compatibility shims:

- `/api/run` composite workflow endpoint for callers that still prefer the single-call compatibility flow

Remaining follow-up work:

- no remaining direct benchmark scripts should be reintroduced outside the admin API plus benchmark worker flow
