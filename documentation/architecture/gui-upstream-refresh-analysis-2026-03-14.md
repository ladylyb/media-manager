# GUI Upstream Refresh Analysis

Date: 2026-03-14

## Summary

- Parent branch baseline: `chore/gui-sync-boundary-policy`
- Analysis branch: `chore/gui-upstream-refresh-analysis`
- Prior imported upstream commit: `5935054c813141827bbbef3731e536857a405291`
- Refreshed upstream commit: `05ab0a9a45449c15b0e7a5c0c50e47bf7b462645`
- Local subtree refresh merge commit: `a65b50c9c4bccff85f8da3e70c08ce80a659d439`

This refresh updates `operator_console/gui_upstream/` only. The supported
runtime client remains `operator_console/gui_app/`, which is API-only and is
the source of truth for the live `/api/*` contract.

Upstream changed 36 files with a large frontend refactor: layout renames, page
renames, route consolidation, new media-focused components, new polling hooks,
and a split of API envelope/types code. Most of the UI ideas are portable only
after manual review because the local `gui_app` has diverged into a
repo-specific integration layer with canonical `/api/*` mapping, operation-run
semantics, benchmark and observability flows, and destructive admin safeguards.

## Implementation Status (MTM)

This section tracks movement from analysis to implementation.

Implemented and merged to `develop`:

- policy/docs/CI guardrail work that formalized `gui_upstream` as reference-only
- media/gallery presentation harvest:
  - `src/components/media/MediaCard.tsx`
  - `src/components/media/MediaGrid.tsx`
  - `src/components/media/MediaPreviewModal.tsx`
  - refreshed `src/pages/GalleryPage.tsx`

Implemented on branch `feat/gui-layout-and-routing-polish`:

- low-risk layout adoption from upstream `layout/*`:
  - `src/components/layout/Sidebar.tsx`
  - `src/components/layout/StatusStrip.tsx`
  - `src/components/layout/TopBar.tsx`
- compatibility wrappers so existing imports keep working:
  - `src/components/AppLayout.tsx`
  - `src/components/AppSidebar.tsx`
  - `src/components/StatusBar.tsx`
- SPA routing cleanup in `src/App.tsx`:
  - route table normalized into `appRoutes`
  - `/console-v2` was reduced to a temporary client-side compatibility redirect to `/` before full cutover

Implemented on branch `feat/gui-page-ux-polish`:

- selected page-level UX improvements for local runtime pages:
  - `src/pages/DashboardPage.tsx`
  - `src/pages/RunsPage.tsx`
  - `src/pages/DuplicatesPage.tsx`
  - `src/pages/PolicyPage.tsx`
- retained the existing local API/query layer while improving:
  - page-level information hierarchy
  - summary cards and at-a-glance status framing
  - detail/inspection panels
  - policy editor affordances and save-state clarity

Implemented on branch `feat/gui-console-route-cutover`:

- removed the `/console-v2` compatibility surface from both FastAPI and the SPA
- removed the `MEDIA_MANAGER_UI_V2_ENABLED` cutover flag and legacy template fallback path
- made the canonical operator-console HTML routes always serve the React shell
- updated docs/tests to treat `/` and the normal operator routes as the only supported UI entrypoints

Implemented on branch `feat/gui-operations-ux-polish`:

- extracted the local operations card into a reusable `gui_app` component
- refreshed operations-page hierarchy with summary framing and guided vs high-impact grouping
- preserved the current local execution model, confirmation behavior, and invalidation wiring
- intentionally kept `/api/operations/catalog` unused in this slice

Implemented on branch `feat/gui-gallery-detail-consolidation`:

- merged discover filtering and sorting into `GalleryPage`
- removed standalone discover navigation and treated `/discover` as compatibility routing into the gallery experience
- added a dedicated client-side media detail route at `/gallery/:fileId`
- kept the existing API-only runtime model and introduced only a thin canonical-gallery detail read for deep-link support

Still intentionally not implemented:

- type/module splitting into `media.ts` / `runs.ts`
- envelope extraction or alternate data hooks

MTM assessment:

- low-risk visual harvest from upstream has been successfully applied without
  disturbing the API adapter layer
- medium-risk layout/routing and page-composition harvest is now substantially
  completed on the local `gui_app` runtime
- route-surface ambiguity around `/console-v2` is now removed; canonical UI
  entrypoints are the standard operator-console routes
- operations-page UX adoption is now complete without moving execution control
  out of the local runtime layer
- discover-to-gallery consolidation and media-detail adoption are now complete
  on top of the current API-only runtime model
- high-risk API/data/admin ownership areas remain correctly untouched

## High-Risk Local Ownership Areas

Treat the following `gui_app` areas as canonical local code. Do not overwrite
them wholesale from upstream:

- `src/lib/api/client.ts`
- `src/lib/api/endpoints.ts`
- `src/types/api.ts`
- admin, observability, benchmark, and operation-run UI flows

Reasons:

- local API base is `/api`, while upstream still carries `/api/v2` assumptions
- local envelope parsing unwraps `{ data: { result: ... } }` responses
- local endpoints map canonical request keys and repo-specific payload shapes
- local admin flows reflect service-layer safeguards and benchmark behavior

## Change Themes

- Layout refresh: `AppLayout`, `AppSidebar`, and `StatusBar` were renamed and
  reorganized into `layout/*`.
- Navigation changes: standalone `Discover` was removed upstream, while
  `Gallery` and `MediaDetail` were expanded.
- Operations UI changes: upstream added a generic `OperationCard` pattern and
  reshaped route-level page files.
- Data-layer changes: upstream introduced `envelope.ts`, `useApi`, `usePolling`,
  and split types into `api.ts`, `media.ts`, and `runs.ts`.
- Tooling changes: upstream added `bun.lock` and TypeScript config updates.

## File-By-File Port Recommendations

Classification legend:

- `ignore`
- `visual-only candidate`
- `manual UX adaptation candidate`
- `do not port`

| Upstream file | Classification | Recommendation |
|---|---|---|
| `operator_console/gui_upstream/.lovable/plan.md` | `ignore` | Lovable workspace metadata only; not part of the supported product. |
| `operator_console/gui_upstream/README.md` | `ignore` | Upstream project README does not describe the local API-only runtime contract. |
| `operator_console/gui_upstream/bun.lock` | `ignore` | Local frontend build currently uses the existing Node/npm workflow; do not introduce a second package-manager baseline from upstream analysis alone. |
| `operator_console/gui_upstream/index.html` | `visual-only candidate` | Safe to mine for site metadata or small branding changes, but do not let it redefine runtime assumptions. |
| `operator_console/gui_upstream/src/App.tsx` | `manual UX adaptation candidate` | Upstream route and layout refactor is useful as a reference, but local routing still needs to preserve current `gui_app` pages and API-backed flows. |
| `operator_console/gui_upstream/src/components/layout/Sidebar.tsx` | `visual-only candidate` | Implemented as local layout harvest on `feat/gui-layout-and-routing-polish`; preserve local route coverage and discover entry until product changes are intentional. |
| `operator_console/gui_upstream/src/components/layout/StatusStrip.tsx` | `visual-only candidate` | Implemented as local layout harvest on `feat/gui-layout-and-routing-polish`, but with local status semantics preserved. |
| `operator_console/gui_upstream/src/components/layout/TopBar.tsx` | `visual-only candidate` | Implemented as local layout harvest on `feat/gui-layout-and-routing-polish`. |
| `operator_console/gui_upstream/src/components/media/MediaCard.tsx` | `visual-only candidate` | Implemented locally and merged as gallery/media presentation work. |
| `operator_console/gui_upstream/src/components/media/MediaGrid.tsx` | `visual-only candidate` | Implemented locally and merged as gallery/media presentation work. |
| `operator_console/gui_upstream/src/components/media/MediaPreviewModal.tsx` | `visual-only candidate` | Implemented locally and merged as gallery/media presentation work. |
| `operator_console/gui_upstream/src/components/ui/LoadingSkeleton.tsx` | `visual-only candidate` | Simple skeleton rename/export cleanup; safe only if it fits existing local component conventions. |
| `operator_console/gui_upstream/src/components/ui/OperationCard.tsx` | `manual UX adaptation candidate` | The generic card pattern is interesting, but local operations already encode invalidation targets and canonical backend semantics in `OperationsPage.tsx`. |
| `operator_console/gui_upstream/src/hooks/useApi.ts` | `do not port` | This introduces an alternate data-access abstraction and risks bypassing the repo-owned API adapter layer. |
| `operator_console/gui_upstream/src/hooks/usePolling.ts` | `manual UX adaptation candidate` | Polling behavior may be worth borrowing selectively, but it must plug into local query keys and operation-run semantics rather than upstream defaults. |
| `operator_console/gui_upstream/src/lib/api/client.ts` | `do not port` | Upstream still assumes `/api/v2`; local client handles canonical `/api` routing and result-envelope quirks. |
| `operator_console/gui_upstream/src/lib/api/endpoints.ts` | `do not port` | Local endpoint adapters are repo-specific and map current backend payloads, request keys, and invalidation behavior. |
| `operator_console/gui_upstream/src/lib/api/envelope.ts` | `manual UX adaptation candidate` | Envelope factoring is structurally interesting, but only if reimplemented around the local `/api` contract rather than copied directly. |
| `operator_console/gui_upstream/src/pages/Admin.tsx` | `do not port` | Local admin is significantly richer and bound to service-layer-backed DB reset, observability, and benchmark flows. |
| `operator_console/gui_upstream/src/pages/Dashboard.tsx` | `manual UX adaptation candidate` | Dashboard layout ideas may be useful, but local metrics and operation wiring are now repo-specific. Implemented locally on `feat/gui-page-ux-polish` as composition-only UX refresh without API-hook changes. |
| `operator_console/gui_upstream/src/pages/DiscoverPage.tsx` | `implemented` | Local UX now consolidates discover filtering into `GalleryPage` and routes `/discover` into that experience for compatibility. |
| `operator_console/gui_upstream/src/pages/Duplicates.tsx` | `manual UX adaptation candidate` | The page refactor may improve presentation, but local duplicate-group data mapping must stay intact. Implemented locally on `feat/gui-page-ux-polish` as presentation/detail-panel refresh while preserving current duplicate-group mapping. |
| `operator_console/gui_upstream/src/pages/Gallery.tsx` | `manual UX adaptation candidate` | Gallery UX ideas are relevant, but local gallery already maps canonical payloads and modal detail behavior. |
| `operator_console/gui_upstream/src/pages/GalleryPage.tsx` | `ignore` | Historical upstream file removed by the refactor; no direct port needed. |
| `operator_console/gui_upstream/src/pages/Index.tsx` | `ignore` | Historical scaffold file removed upstream; no local value. |
| `operator_console/gui_upstream/src/pages/Ledger.tsx` | `manual UX adaptation candidate` | Page structure may inspire cleanup, but local ledger endpoints and analytics mapping are canonical. |
| `operator_console/gui_upstream/src/pages/MediaDetail.tsx` | `implemented` | Local media detail now exists at `/gallery/:fileId`, built around the durable `file_id` model instead of upstream hash-based lookup. |
| `operator_console/gui_upstream/src/pages/Operations.tsx` | `manual UX adaptation candidate` | The upstream reshaping of operations UI is worth reviewing, but local operation execution, invalidation, and safety affordances must remain canonical. |
| `operator_console/gui_upstream/src/pages/OperationsPage.tsx` | `ignore` | Historical upstream file removed by the refactor; only useful as context while reviewing the new operations page. |
| `operator_console/gui_upstream/src/pages/Policy.tsx` | `manual UX adaptation candidate` | Policy-editor presentation may be portable, but local policy payloads and save semantics are backend-owned. Implemented locally on `feat/gui-page-ux-polish` as editor/layout polish only; local save semantics remain canonical. |
| `operator_console/gui_upstream/src/pages/Runs.tsx` | `manual UX adaptation candidate` | Polling and table UX may be useful, but local run history is tied to unified `operation_runs`. Implemented locally on `feat/gui-page-ux-polish` as inspection-panel and summary-card refresh without changing run queries. |
| `operator_console/gui_upstream/src/types/api.ts` | `do not port` | Local API types are already aligned to current `/api/*` envelopes and payloads. |
| `operator_console/gui_upstream/src/types/media.ts` | `manual UX adaptation candidate` | Type splitting is a code-organization idea only; any split must preserve local runtime fields and request/response mapping. |
| `operator_console/gui_upstream/src/types/runs.ts` | `manual UX adaptation candidate` | Same as `media.ts`: structure idea only, not a copy target. |
| `operator_console/gui_upstream/tsconfig.app.json` | `ignore` | Tooling changes do not justify divergence from the local frontend toolchain during analysis. |
| `operator_console/gui_upstream/tsconfig.json` | `ignore` | Same as above; review only if later frontend compiler settings are intentionally revisited. |

## Recommended Next Port Order

Completed:

1. media components and gallery preview UX
2. layout polish from `layout/*` (implemented on `feat/gui-layout-and-routing-polish`)
3. selected page-level UX improvements for dashboard, runs, duplicates, and policy (implemented on `feat/gui-page-ux-polish`)
4. operations-page UX adoption using the same local-runtime-only adaptation strategy (implemented on `feat/gui-operations-ux-polish`)

Recommended next:

5. code-organization-only follow-up: type/module splitting and any envelope factoring, if still valuable after the UI work settles

Do not start with API, types, admin pages, or alternate data hooks.

## Verification Notes

- The subtree refresh touched `operator_console/gui_upstream/` only.
- `gui_app` remained unchanged during this phase.
- Existing boundary guards should remain the acceptance gate before any later
  adaptation into `gui_app`.
- Gallery/media harvest passed guard checks and build before merge to `develop`.
- Layout/routing polish on `feat/gui-layout-and-routing-polish` passes:
  - `bash tools/ci/check_gui_sync_boundary.sh`
  - `bash tools/ci/check_gui_app_api_client_contract.sh`
  - `bash tools/ci/check_supported_tooling_api_boundary.sh`
  - `npm run build`
- Page UX polish on `feat/gui-page-ux-polish` should pass the same guard/build
  sequence before PR:
  - `bash tools/ci/check_gui_sync_boundary.sh`
  - `bash tools/ci/check_gui_app_api_client_contract.sh`
  - `bash tools/ci/check_supported_tooling_api_boundary.sh`
  - `npm run build`
- Route-surface cutover on `feat/gui-console-route-cutover` should pass:
  - `bash tools/ci/check_gui_sync_boundary.sh`
  - `bash tools/ci/check_gui_app_api_client_contract.sh`
  - `bash tools/ci/check_supported_tooling_api_boundary.sh`
  - `pytest operator_console/tests/test_main.py` with a working local pytest environment
  - `npm run build`
- Operations-page UX polish on `feat/gui-operations-ux-polish` should pass:
  - `bash tools/ci/check_gui_sync_boundary.sh`
  - `bash tools/ci/check_gui_app_api_client_contract.sh`
  - `bash tools/ci/check_supported_tooling_api_boundary.sh`
  - `npm run build`
- Gallery/detail consolidation on `feat/gui-gallery-detail-consolidation` should pass:
  - `bash tools/ci/check_gui_sync_boundary.sh`
  - `bash tools/ci/check_gui_app_api_client_contract.sh`
  - `bash tools/ci/check_supported_tooling_api_boundary.sh`
  - `pytest operator_console/tests/test_main.py -k "gallery or discover"` with a working local pytest environment
  - `npm run build`
