# ADR-0002: Planner/Apply Separation and Durable Gating

- Status: Accepted
- Date: 2026-03-02

## Context

Previous approaches mixed intent calculation with execution, creating hidden side effects and weak recovery boundaries.

## Decision

Enforce strict separation:

- Planner reads durable state and emits deterministic planned actions.
- Apply consumes planned actions and performs mutations only after durable DB writes.
- Failure paths append durable failure events before aborting the run.

## Consequences

- Resume operates at explicit durable boundaries.
- Drift detection is feasible through persisted action/failure facts.
- Filesystem operations outside apply are treated as policy violations.

## Supersedes

- None

## Superseded By

- None
