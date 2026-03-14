# media-manager

`media-manager` is a deterministic, failure-sensitive media management engine for planning and applying file organization work with durable state boundaries. It is built around explicit `plan` and `apply` phases so that planning stays side-effect free, while filesystem mutation happens only after durable database gating.

The project is designed for restart safety, idempotent operations, and operator visibility. It includes a Python CLI, a FastAPI-backed operator console, structured documentation, and observability hooks for production-style workflows.

## Key capabilities

- Deterministic planning that produces reproducible planned actions for identical inputs.
- Restart-safe apply execution with explicit durable state transitions.
- Canonical persistence and policy-driven canonicalization workflows.
- Drift detection, structured failure recording, and operator-focused observability.
- Multiple interfaces: CLI, operator console, and HTTP API endpoints.
- Performance and Prometheus metrics support for planner, apply, ingest, and cache behavior.

## Why this project is different

This repository is not a generic scripting playground or a thin file-moving utility. The core operating model is built around runtime invariants:

- No filesystem mutation without durable DB gating.
- Planning has zero side effects.
- Apply consumes durable planned state instead of inventing work on the fly.
- Operations are designed to be idempotent and restart-safe.
- Failures and drift must become durable, observable facts.

Those rules are enforced throughout the system design and are documented in [AGENTS.md](AGENTS.md), [Architecture Invariants](documentation/architecture/invariants.md), and the [Run Lifecycle docs](documentation/architecture/run-lifecycle.md).

## Architecture at a glance

- Planner: reads durable state and emits deterministic `planned_actions`.
- Apply Engine: consumes planned actions and performs filesystem mutation only after DB gating.
- Canonical Persistence Layer: stores content, instances, policies, and run state durably.
- Drift Detection: makes divergence visible instead of silently masking it.
- Failure Logging: records failure events as durable facts.
- Run Lifecycle Controller: defines explicit state boundaries for crash recovery and resume safety.

Deeper architecture material lives in [documentation/architecture/](documentation/architecture/index.md) and [documentation/STATE_MACHINE.md](documentation/STATE_MACHINE.md).

## Interfaces

### CLI

The primary entrypoint is the `media-manager` CLI. Core first-run commands are:

- `media-manager plan <path>`
- `media-manager apply <run-id>`

The CLI also exposes ingest, canonical recompute, policy, observability, operator, and performance workflows. See the [CLI reference](documentation/api/api-cli.md).

### Operator Console

The operator console is served by FastAPI and includes a React v2 shell for dashboard, runs, policy, ledger, duplicates, and admin flows. It is intended for operational visibility and controlled execution rather than replacing the system safety model.

Relevant docs:

- [Operator Console API](documentation/api/api-operator-console.md)
- [Operator Guide](documentation/operator-guide/index.md)
- [GUI integration notes](operator_console/gui_app/README.md)

### HTTP API

The FastAPI app exposes service-layer endpoints under `/api/v2/*` for status, runs, policy, plan/apply triggers, and operator workflows. Metrics can also be mounted at `/metrics`.

See [API Documentation](documentation/api/index.md) for the module-oriented reference.

## Quick start

### Prerequisites

- Python 3.11+
- PostgreSQL
- Git

### Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Optional extras:

```bash
pip install -e ".[docs,operator_console]"
```

### Configure the environment

Use the repository template:

```bash
cp .env.sample .env
```

Set at least:

```bash
DATABASE_URL='postgresql+psycopg://user:password@localhost:5432/media_manager'
TEST_DATABASE_URL='postgresql+psycopg://user:password@localhost:5432/media_manager_test'
```

`DATABASE_URL` is required for runtime operation. Full variable reference: [documentation/reference/environment-variables.md](documentation/reference/environment-variables.md).

### Run a first plan/apply cycle

Choose a file or directory containing media files:

```bash
media-manager plan /path/to/media
```

Expected output includes grouped action sections such as `MOVE`, `DUPLICATE`, and `NOOP`, plus a final `Run ID`.

Apply the planned run:

```bash
media-manager apply <RUN_ID>
```

`apply` consumes the previously planned durable state. It does not plan new work on the fly.

### Start the operator console

After installing the `operator_console` extra, you can run the FastAPI app with Uvicorn:

```bash
uvicorn operator_console.main:app --reload
```

The console also exposes `/metrics` when metrics are mounted. To force the React v2 shell on the main console routes, set `MEDIA_MANAGER_UI_V2_ENABLED=true`. The v2 shell is also available directly at `/console-v2`.

## Example workflow

```bash
source .venv/bin/activate
cp .env.sample .env
# Edit .env with PostgreSQL connection details first.

media-manager plan /data/inbox
# Review MOVE / DUPLICATE / NOOP output and note the emitted Run ID.

media-manager apply 11111111-1111-1111-1111-111111111111
# Confirm the apply summary and inspect any skipped or errored actions.
```

Success on a first run means:

- `plan` completes with a `Run ID`.
- `apply` completes without unexpected filesystem mutation outside planned targets.
- rerunning from a durable state boundary remains safe if a run is interrupted.

For more guided walkthroughs, start with [Quickstart](documentation/getting-started/quickstart.md) and [First Run](documentation/getting-started/first-run.md).

## Operator console and API

The operator console and API are for monitoring, policy control, run triggering, diagnostics, and administrative workflows. They are not a shortcut around the runtime invariants; they sit on top of the same safety model.

Operator-facing entry points:

- `/api/v2/status`
- `/api/v2/runs`
- `/api/v2/policy`
- `/api/v2/operator-run`
- `/metrics`

Use these docs for operational details instead of relying on the README for endpoint-by-endpoint behavior:

- [Operator Guide](documentation/operator-guide/index.md)
- [Operator Console API](documentation/api/api-operator-console.md)
- [Observability guide](documentation/operator-guide/observability.md)

## Project structure

```text
media-manager/
├── media_manager/        # Core application, CLI, persistence, planner, apply, tests
├── operator_console/     # FastAPI app and React operator console integration
├── documentation/        # User, operator, API, architecture, and reference docs
├── migrations/           # Alembic migrations
├── tools/                # Local tooling and support scripts
├── artifacts/            # Generated artifacts and run outputs
├── README.md             # Project entrypoint
├── AGENTS.md             # Runtime invariants and agent safety rules
└── CONTRIBUTING.md       # Contribution workflow
```

## Documentation map

- [Getting Started](documentation/getting-started/index.md)
- [Guides](documentation/guides/index.md)
- [Operator Guide](documentation/operator-guide/index.md)
- [API Documentation](documentation/api/index.md)
- [Architecture](documentation/architecture/index.md)
- [Reference](documentation/reference/index.md)
- [Examples](documentation/examples/index.md)
- [Contributing](documentation/contributing/index.md)

The docs site home is [documentation/home.md](documentation/home.md).

## Development

Install development dependencies:

```bash
pip install -e ".[dev]"
```

Run tests:

```bash
./.venv/bin/python -m pytest
```

Build the docs:

```bash
./.venv/bin/python -m mkdocs build --strict
```

Contribution workflow, branch conventions, review expectations, and merge policy are documented in [CONTRIBUTING.md](CONTRIBUTING.md).

## Safety model and invariants

Before changing code or runtime behavior, read [AGENTS.md](AGENTS.md). It is the repository’s single source of truth for invariants such as:

- no filesystem mutation without durable DB gating
- explicit state transitions
- restart-safe apply behavior
- idempotent operations
- durable failure facts

This matters for code changes, operational tooling, and documentation that describes system behavior.

## License

This repository currently uses the license in [LICENSE](LICENSE): Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International (`CC BY-NC-ND 4.0`).

In practical terms, that means:

- you may view and share the repository for non-commercial purposes
- commercial use is not permitted without separate permission
- derivative works and modifications are not permitted without separate permission

Review the full license text before reuse, redistribution, or contribution planning. This repository is publicly accessible, but the current license is more restrictive than a typical OSI-approved open source license.

## Status and roadmap

The project already has a substantial CLI, persistence, operator-console, and documentation surface area, and the current work is focused on hardening workflows, operator playbooks, and documentation quality rather than introducing a brand-new skeleton.

For current documentation priorities, see the [Documentation Roadmap](documentation/roadmap/index.md).
