# Media Manager Operator Console v2 (Integration Layer)

Editable integration layer for the Lovable-generated operator console. Built with React + Vite + TypeScript + Tailwind CSS.

Upstream source-of-truth is tracked at:
- `operator_console/gui_upstream/` (git subtree, do not edit directly)

This folder:
- `operator_console/gui_app/` is where compatibility fixes and contract mappings live.

## Quick Start

```bash
npm install
npm run dev
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `/api/v2` | Base URL for the FastAPI backend |

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
├── lib/api/          # Typed API client + endpoint functions
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
