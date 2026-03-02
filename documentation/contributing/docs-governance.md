# Documentation Governance

This policy keeps docs practical, auditable, and aligned with runtime invariants.

## Scope

Applies to all content under `documentation/`.

## Documentation Classes

1. User/Operator docs: workflow and runbook content.
2. Reference docs: stable technical lookup material.
3. API docs: generated module-level reference.
4. Architecture docs: behavior model and ADRs.
5. Archive docs: historical, non-primary material.

## Required Updates Per Change Type

- Behavior change: update workflow docs and relevant runbooks.
- Architecture change: add new ADR and update architecture overview links.
- Schema/lifecycle change: update operator guides and reference docs.
- Deprecated content: move to archive and mark as non-primary.

## ADR Rules

- Use sequential numbering (`0003-...`, `0004-...`).
- Never edit accepted ADR intent retroactively; supersede with a new ADR.
- Include context, decision, consequences, and supersession fields.

## Quality Gate

Before merge:

1. `mkdocs build --strict` passes.
2. Navigation links resolve.
3. New behavior has user-facing and operator-facing documentation coverage.
