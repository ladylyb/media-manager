# Media Manager Documentation

This site is the canonical documentation entrypoint for the deterministic media manager.

## Core Principles

- Filesystem mutation is gated by durable DB state.
- Apply operations are restart-safe and idempotent.
- Planner remains pure and deterministic.
- Failure creates durable facts for observability and recovery.

## Quick Links

- [Documentation Index](README.md)
- [Run Lifecycle](architecture/run-lifecycle.md)
- [Invariant Summary](architecture/invariants.md)
- [API Reference](reference/api-cli.md)
