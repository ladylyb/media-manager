# Media Manager Operator Console

Production-quality frontend for the Media Manager pipeline. Built with React + Vite + TypeScript + Tailwind CSS.

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

Copy the `dist/` folder contents to your FastAPI static files directory.

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
