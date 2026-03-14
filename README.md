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

## Development

```bash
npm run dev      # Start dev server
npm run build    # Production build
npm run preview  # Preview production build
npm run lint     # Lint codebase
npm run test     # Run tests
```

## Production Build for FastAPI

```bash
npm run build
```

This produces `dist/index.html` and `dist/assets/*`.

Copy the `dist/` folder contents to your FastAPI static files directory:

```python
# FastAPI integration example
from fastapi.staticfiles import StaticFiles

app.mount("/", StaticFiles(directory="dist", html=True), name="static")
```

For BrowserRouter support, ensure your FastAPI server returns `index.html` for all unmatched routes.

## Architecture

```
src/
├── components/
│   ├── layout/          # Sidebar, TopBar, StatusStrip
│   ├── media/           # MediaGrid, MediaCard, MediaPreviewModal
│   └── ui/              # StatusBadge, MetricCard, OperationCard, etc.
├── hooks/
│   ├── useApi.ts        # TanStack Query wrapper for API calls
│   └── usePolling.ts    # Auto-refreshing query hook
├── lib/api/
│   ├── client.ts        # Central fetch-based API client
│   ├── envelope.ts      # Typed envelope parser
│   └── endpoints.ts     # All typed endpoint functions
├── pages/               # Route-level page components
└── types/
    ├── api.ts           # API envelope + shared types
    ├── media.ts         # Media domain types
    └── runs.ts          # Run domain types
```

## API Client

All HTTP calls go through `src/lib/api/client.ts`. Pages never call `fetch` directly.

The envelope parser (`envelope.ts`) unwraps the standard API response:
- If `ok=true`: returns `data` directly
- If `ok=false`: throws `ApiClientError` with the first error message

## State Management

Uses TanStack Query for all API state with:
- Automatic caching and deduplication
- Loading/error states
- Auto-polling for dashboard, status, metrics, and runs (10s interval)

## Routes

| Route | Description |
|---|---|
| `/` | Dashboard — KPIs, performance, quick actions |
| `/operations` | Pipeline operations with risk labels |
| `/runs` | Sortable/filterable run history |
| `/ledger` | Analytics, hash queries, audit |
| `/duplicates` | Split-pane duplicate group browser |
| `/gallery` | Filterable media grid + detail modal |
| `/media?hash=...` | Individual media file detail |
| `/policy` | Policy configuration editor |
| `/admin` | Destructive operations with challenge confirmation |
