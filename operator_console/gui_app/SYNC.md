# GUI Sync Workflow

This project uses a two-layer model:

1. `operator_console/gui_upstream/`
- Imported from `https://github.com/ladylyb/media-manager-gui.git` via git subtree.
- Treat as immutable upstream snapshot.
- Purpose: design/reference source only.
- Not a supported runtime integration layer.

2. `operator_console/gui_app/`
- Supported runtime integration layer for API contract alignment and runtime routing needs.
- The only first-party GUI layer that should track this repo's live `/api/*` contract.
- Current product baseline for all operator-console behavior in this repository.

## Policy

- `gui_app` is API-only and is the source of truth for runtime integration behavior.
- `gui_upstream` is a refreshed reference snapshot, not a merge target expected to apply cleanly.
- Upstream changes must be reviewed in three buckets:
  1. visual/layout-only changes
  2. route/page UX ideas
  3. API/data-layer changes
- Only bucket 1 should be considered low-friction by default.
- Buckets 2 and 3 require manual adaptation into `gui_app` around the current `/api/*` contract.
- Do not replace `gui_app` API client, endpoint adapters, types, or admin flows with upstream versions.

## Update Process

1. Pull latest upstream subtree:
```bash
git fetch lovable-gui
git subtree pull --prefix operator_console/gui_upstream lovable-gui main
```

2. Review upstream changes and selectively copy/adapt into `gui_app`.
Only copy what is needed to preserve the supported `gui_app` runtime contract.
Treat upstream as a UI/design harvest, not as a second source of runtime truth.

3. Re-run frontend build:
```bash
cd operator_console/gui_app
npm ci
npm run build
```

The supported build now writes runtime assets into:
- `operator_console/gui_app/dist/`

FastAPI serves that directory first and keeps `operator_console/static_v2/` only as a
temporary local fallback for older environments that have not rebuilt yet.

4. Validate the canonical FastAPI operator-console routes render the React shell.

The March 2026 upstream refresh and selective-adaptation sequence is complete.
Use this file as the long-lived source of truth for future upstream syncs rather
than the retired one-off analysis report.

## High-Risk Local Ownership Areas

The following areas in `gui_app` are canonical to this repository and should not
be overwritten wholesale from upstream:

- `src/lib/api/client.ts`
- `src/lib/api/endpoints.ts`
- `src/types/`
- admin, observability, benchmark, and operation-run UI flows

These files encode the supported `/api/*` contract, envelope handling,
repo-specific mapping, cache invalidation behavior, and destructive-operation
safeguards expected by the current backend.

## Rules

- Do not edit `gui_upstream` files directly.
- Preserve the canonical `/api/*` contracts in `gui_app`; do not normalize `gui_upstream`.
- Keep all operational calls in `gui_app` routed through `src/lib/api/client.ts`.
- Treat `gui_upstream` as reference material only, not a second deployable integration layer.
- Do not import from `gui_upstream` into `gui_app`.
- Do not reintroduce `/api/v1/*` or `/api/v2/*` runtime assumptions into `gui_app`.
