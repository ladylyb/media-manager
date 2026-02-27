# Documentation Index

This folder contains the canonical documentation set for the media-manager rewrite.

## Governance and Agent Contract
- `AGENTS.md`: invariant and behavior contract for engineering agents.
- `ARCHITECTURE_GUARDRAILS.md`: core design philosophy.
- `STATE_MACHINE.md`: allowed run/action state transitions.
- `AGENT_CHECKLIST.md`: required pre-merge safety checklist.

## Project Planning and Architecture
- `project/00-charter.md`: project intent, goals, non-goals.
- `project/01-roadmap.md`: narrative sequencing.
- `project/02-milestones.md`: authoritative milestone definitions.
- `project/03-test-strategy.md`: test taxonomy and risk coverage.
- `project/04-risk-register.md`: risk inventory and controls.
- `project/05-release-plan.md`: rollout sequencing and gates.
- `project/06-operational-guardrails.md`: authoritative runtime guardrails.
- `project/07-unified-architecture-spec.md`: canonical technical specification.

## Reference Material
- `reference/data-dictionary.md`: schema/data dictionary reference from legacy system for context.

## Legacy Archive
- `legacy/README.md`: legacy implementation archive summary.
- `legacy/failure-notes.md`: legacy post-mortem and failure modes.
- `legacy/media-manager-dev-*.md`: historical development artifacts.

## Authority Rules
- If project docs conflict, use `project/07-unified-architecture-spec.md` for technical behavior.
- Agent behavior and state transitions are strictly governed by:
  - `AGENTS.md`
  - `STATE_MACHINE.md`
  - `ARCHITECTURE_GUARDRAILS.md`
