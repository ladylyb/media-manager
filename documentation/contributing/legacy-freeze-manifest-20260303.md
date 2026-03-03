# Legacy Freeze Manifest (2026-03-03)

## Freeze Refs

- Branch: `archive/legacy-freeze-20260303`
- Tag: `legacy-freeze-20260303`
- Commit SHA: `add054dff55cd6e032917c9fa5552e99a8772981`

## Removal Scope

All paths previously under:

- `archive/legacy/**`

## Removed Paths

- `archive/legacy/README.md`
- `archive/legacy/docs/README.md`
- `archive/legacy/docs/documentation-archive/index.md`
- `archive/legacy/docs/documentation-archive/legacy-implementation.md`
- `archive/legacy/docs/documentation-archive/project-history.md`
- `archive/legacy/docs/documentation-archive/retention-policy.md`
- `archive/legacy/docs/failure-notes.md`
- `archive/legacy/docs/media-manager-dev-chat-backup0-0001.md`
- `archive/legacy/docs/media-manager-dev-chat-backup0-0002.md`
- `archive/legacy/docs/media-manager-dev-todo.md`
- `archive/legacy/logs/logs.zip`
- `archive/legacy/output/output.zip`
- `archive/legacy/sql/legacy_schema.sql`
- `archive/legacy/sql/media-manager-1.sql`
- `archive/legacy/sql/media-manager-2.sql`
- `archive/legacy/sql/media-manager.sqbpro`
- `archive/legacy/sql/media-manager.sql`

## Recovery Instructions

1. Create a recovery branch from current `develop`.
2. Restore required files from tag:
   - `git checkout legacy-freeze-20260303 -- archive/legacy`
3. Commit restored files and open a PR.

No force push and no history rewrite are permitted for recovery.
