# Media Manager (Legacy) — Archive README

## Purpose
This directory documents the legacy Python + SQLite implementation of Media Manager.
It is preserved for historical reference and post-mortem learning only.

## Baseline Tag
- `v0-legacy-scripts-final`

## Contents
- `failure-notes.md`: detailed root-cause analysis of legacy failures.
- `media-manager-dev-chat-backup0-0001.md`, `media-manager-dev-chat-backup0-0002.md`: historical notes.
- `media-manager-dev-todo.md`: historical working notes.

## Operating Notes
- Legacy system artifacts (logs/output/sql snapshots) are retained elsewhere in the repository.
- No active development should occur in this legacy model.
- All new implementation work should follow the contracts in:
  - `documentation/AGENTS.md`
  - `documentation/STATE_MACHINE.md`
  - `documentation/project/07-unified-architecture-spec.md`
