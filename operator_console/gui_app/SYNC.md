# GUI Sync Workflow

This project uses a two-layer model:

1. `operator_console/gui_upstream/`
- Imported from `https://github.com/ladylyb/media-manager-gui.git` via git subtree.
- Treat as immutable upstream snapshot.

2. `operator_console/gui_app/`
- Supported runtime integration layer for API contract alignment and runtime routing needs.
- The only first-party GUI layer that should track this repo's live `/api/*` contract.

## Update Process

1. Pull latest upstream subtree:
```bash
git fetch lovable-gui
git subtree pull --prefix operator_console/gui_upstream lovable-gui main
```

2. Review upstream changes and selectively copy/adapt into `gui_app`.
Only copy what is needed to preserve the supported `gui_app` runtime contract.

3. Re-run frontend build:
```bash
cd operator_console/gui_app
npm ci
npm run build
```

4. Validate FastAPI dual-run behavior (`MEDIA_MANAGER_UI_V2_ENABLED` on/off).

## Rules

- Do not edit `gui_upstream` files directly.
- Preserve the canonical `/api/*` contracts in `gui_app`; do not normalize `gui_upstream`.
- Keep all operational calls in `gui_app` routed through `src/lib/api/client.ts`.
- Treat `gui_upstream` as reference material only, not a second deployable integration layer.
