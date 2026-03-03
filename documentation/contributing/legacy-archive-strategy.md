# Legacy Archive Freeze and Removal Strategy

This document defines the archival and removal contract for legacy repository
content that is no longer kept on `develop`.

## Scope

- Applies to legacy content previously stored under `archive/legacy/**`.
- Legacy content is retained only via frozen git refs after removal.

## Naming Standard

- Freeze branch: `archive/legacy-freeze-YYYYMMDD`
- Freeze tag: `legacy-freeze-YYYYMMDD`
- Deletion branch: `feature/remove-legacy-archive-YYYYMMDD`

## Required Approvals

Before removal from `develop`:

1. Owner approval.
2. Manual release gate acknowledgment.
3. Successful docs checks on the candidate branch.

## Execution Contract

1. Create freeze branch from gate commit on `develop`.
2. Create annotated freeze tag on the same commit.
3. Push branch and tag to origin.
4. Verify remote refs and capture commit SHA.
5. Produce a dated freeze manifest under `documentation/contributing/`.
6. In a separate PR, remove `archive/legacy/**` from `develop`.

## Freeze Snapshot Executed

- Date: `2026-03-03`
- Freeze branch: `archive/legacy-freeze-20260303`
- Freeze tag: `legacy-freeze-20260303`
- Frozen commit SHA: `add054dff55cd6e032917c9fa5552e99a8772981`
- Manifest: `documentation/contributing/legacy-freeze-manifest-20260303.md`

## Post-Removal Verification

1. `mkdocs build --strict` passes.
2. `bash tools/docs/check_no_legacy_links.sh` passes.
3. `rg --files archive/legacy` returns no files on `develop`.
4. Historical references in docs point to freeze branch/tag, not removed paths.

## Rollback

To restore removed legacy content, recover files from:

- `archive/legacy-freeze-20260303` branch, or
- `legacy-freeze-20260303` tag.

Rollback must be done via a normal PR; do not rewrite history.
