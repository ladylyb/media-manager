# Legacy Documentation Archive Strategy (Deferred Execution)

This document defines the future procedure for moving legacy documentation out
of the default branch while keeping durable historical access.

## Scope

- Legacy documentation currently centralized under `archive/legacy/docs/`.
- Strategy only; no deletion is performed by this document.

## Branch and Tag Naming

- Archive branch format: `archive/docs-legacy-YYYYMMDD`
- Freeze tag format: `legacy-docs-freeze-YYYYMMDD`

Example:

- Branch: `archive/docs-legacy-20260303`
- Tag: `legacy-docs-freeze-20260303`

## Preconditions Before Legacy Removal

1. `mkdocs build --strict` passes on the default branch.
2. Legacy docs are centralized under `archive/legacy/docs/`.
3. No published docs links point to legacy content:
   - `bash tools/docs/check_no_legacy_links.sh` passes.
4. Release notes/changelog entry is prepared.

## Archival Procedure (Future Change)

1. Create branch from the current default branch:
   - `git checkout -b archive/docs-legacy-YYYYMMDD`
2. Create and push an immutable freeze tag:
   - `git tag legacy-docs-freeze-YYYYMMDD`
   - `git push origin archive/docs-legacy-YYYYMMDD`
   - `git push origin legacy-docs-freeze-YYYYMMDD`
3. Generate a manifest listing archived files and commit it on the default
   branch before deletion.
4. In a separate PR, remove legacy docs from default branch.

## Post-Delete Verification Checklist

1. `mkdocs build --strict` passes.
2. `bash tools/docs/check_no_legacy_links.sh` passes.
3. No links in `documentation/` point to deleted legacy paths.
4. Site navigation includes only current documentation sections.
5. Archive branch and tag are present on remote and documented in release notes.

## Rollback

If historical content must be restored, recover files from:

- `archive/docs-legacy-YYYYMMDD` branch, or
- `legacy-docs-freeze-YYYYMMDD` tag.
