# ADR-0001: Runtime Invariants as Hard Constraints

- Status: Accepted
- Date: 2026-03-02

## Context

The system manages failure-sensitive filesystem and persistence operations where ambiguous behavior causes drift and recovery failures.

## Decision

Treat core runtime invariants as non-negotiable constraints for all design and implementation work:

1. DB gating before filesystem mutation.
2. Restart-safe apply behavior.
3. Idempotent operation semantics.
4. Pure planning with zero side effects.
5. Explicit validated transitions.
6. Durable failure facts and observability.

## Consequences

- Changes that weaken invariants are rejected.
- New features must define crash/retry/partial-completion semantics.
- Review process prioritizes deterministic behavior over convenience.

## Supersedes

- None

## Superseded By

- None
