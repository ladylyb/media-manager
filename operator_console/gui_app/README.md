# Media Manager Operator Console (Integration Layer)

Supported integration layer for the operator console. Built with React + Vite + TypeScript + Tailwind CSS.

Upstream source snapshot is tracked at:
- `operator_console/gui_upstream/` (git subtree, do not edit directly)

This folder:
- `operator_console/gui_app/` is the supported runtime client integration layer.
- all operational actions must go through `src/lib/api/client.ts` and `src/lib/api/endpoints.ts`
- local Python service or persistence imports are out of bounds for the GUI
- lovable upstream changes are reference input only and must be manually adapted to the live `/api/*` contract

## Quick Start

```bash
npm install
npm run dev
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `/api` | Base URL for the FastAPI backend |

Local deployment note:
- the Pipeline Wizard can optionally expose a `Browse` button for `folder_path`
- this is server-host browsing, not client-machine browsing
- enable it only in trusted/local environments with constrained roots via `MEDIA_MANAGER_DIRECTORY_PICKER_ENABLED` and `MEDIA_MANAGER_DIRECTORY_PICKER_ROOTS`

## Production Build for FastAPI

```bash
npm run build
```

Build output is written directly to:
- `operator_console/gui_app/dist/`

Serve via FastAPI route:
- `/`
- and the canonical operator-console routes such as `/operations`, `/admin/diagnostics`, `/gallery`, and `/admin`

FastAPI prefers `gui_app/dist/` at runtime and temporarily falls back to the checked-in
`operator_console/static_v2/` snapshot when a local build is not present.

## Architecture

```
src/
├── components/       # Reusable UI primitives
├── lib/api/          # Supported shared API client + endpoint functions
├── pages/            # Route-level page components
└── types/            # TypeScript interfaces for API payloads
```

## Routes

| Route | Description |
|---|---|
| `/` | Home - media-first start screen, review queues, and guided workflow entry |
| `/operations` | Import workspace with risk labels and calmer follow-up actions |
| `/pipeline-wizard` | Organize workflow with guided review checkpoints |
| `/admin/diagnostics` | Legacy compatibility route into Admin tabs for activity, file history, and integrity checks |
| `/duplicates` | Throughput-first duplicate review workspace with queue, progress, and keyboard shortcuts |
| `/gallery` | Library browsing surface with filters, sort controls, and detail modal |
| `/gallery/:fileId` | Full-page canonical media detail |
| `/policy` | Legacy compatibility route that redirects to Admin Library Rules |
| `/admin` | Integrated admin workspace for activity, library rules, file history, integrity checks, health, benchmarks, and reset |

## Sync Strategy

See [SYNC.md](./SYNC.md) for the subtree refresh workflow and selective-adaptation rules.

Practical rule:
- treat `gui_upstream` as a design/reference snapshot
- treat `gui_app` as the canonical runtime client
- never replace the API client, endpoint adapters, types, or admin flows wholesale from upstream
