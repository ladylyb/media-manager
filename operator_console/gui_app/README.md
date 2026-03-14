# Media Manager Operator Console v2 (Integration Layer)

Supported integration layer for the operator console. Built with React + Vite + TypeScript + Tailwind CSS.

Upstream source snapshot is tracked at:
- `operator_console/gui_upstream/` (git subtree, do not edit directly)

This folder:
- `operator_console/gui_app/` is the supported runtime client integration layer.
- all operational actions must go through `src/lib/api/client.ts` and `src/lib/api/endpoints.ts`
- local Python service or persistence imports are out of bounds for the GUI

## Quick Start

```bash
npm install
npm run dev
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `/api` | Base URL for the FastAPI backend |

## Production Build for FastAPI

```bash
npm run build
```

Build output is written directly to:
- `operator_console/static_v2/`

Serve via FastAPI route:
- `/console-v2`

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
| `/` | Dashboard - KPIs, performance, quick actions |
| `/operations` | Pipeline operations with risk labels |
| `/runs` | Sortable/filterable run history |
| `/ledger` | Analytics, hash queries, audit |
| `/discover` | Tag-based media filtering |
| `/duplicates` | Split-pane duplicate group browser |
| `/gallery` | Responsive media grid + detail modal |
| `/policy` | Policy configuration editor |
| `/admin` | Destructive operations with challenge confirmation |

## Sync Strategy

See [SYNC.md](./SYNC.md) for subtree update workflow and rules.
