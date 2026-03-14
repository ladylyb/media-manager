# Media Manager Operator Console Upstream Snapshot

Immutable upstream snapshot for the Media Manager operator console. Built with React + Vite + TypeScript + Tailwind CSS.

This directory is not the supported runtime integration layer for this repository.
It may contain stale request shapes or API assumptions from upstream.

Supported runtime/API integration happens in:
- `operator_console/gui_app/`

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

Copy the `dist/` folder contents to your FastAPI static files directory.

## Architecture

```
src/
├── components/       # Reusable UI primitives
├── lib/api/          # Upstream snapshot only; not the supported repo contract
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
