# Documentation Governance

This policy keeps docs practical, auditable, and aligned with runtime invariants.

## Scope

Applies to all content under `documentation/`.

## Documentation Classes

1. User/Operator docs: workflow and runbook content.
2. Reference docs: stable technical lookup material.
3. API docs: generated module-level reference.
4. Architecture docs: behavior model and ADRs.
5. Legacy archive docs: historical, non-primary material retained via frozen git refs.

## Legacy Documentation Policy

- Canonical legacy source is frozen refs:
  - Branch `archive/legacy-freeze-YYYYMMDD`
  - Tag `legacy-freeze-YYYYMMDD`
- Legacy documentation must not be linked from files under `documentation/`.
- Legacy documentation must not be included in `mkdocs.yml` navigation.
- Any historical note in published docs must be plain text (non-link) unless superseded by an active current-doc page.

## Required Updates Per Change Type

- Behavior change: update workflow docs and relevant runbooks.
- Architecture change: add new ADR and update architecture overview links.
- Schema/lifecycle change: update operator guides and reference docs.
- Deprecated content: stage in a release PR, then archive via freeze branch/tag before deletion from `develop`.

## ADR Rules

- Use sequential numbering (`0003-...`, `0004-...`).
- Never edit accepted ADR intent retroactively; supersede with a new ADR.
- Include context, decision, consequences, and supersession fields.

## Quality Gate

Before merge:

1. `mkdocs build --strict` passes.
2. Navigation links resolve.
3. New behavior has user-facing and operator-facing documentation coverage.
4. Legacy-link guard passes (`bash tools/docs/check_no_legacy_links.sh`).
