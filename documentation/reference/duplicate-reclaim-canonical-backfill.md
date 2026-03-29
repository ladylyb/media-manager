# Duplicate Reclaim Canonical Backfill

This note documents the historical-data gap behind Recycle Bin groups that show:

- `Looks right`
- `Planner-confirmed keep copy is missing`

## Problem Summary

The Recycle Bin move planner requires `file_contents.canonical_file_instance_id` to be set before it will plan archive actions for duplicate extra copies.

Some historical duplicate groups already have a display-side canonical decision in `canonical_assignments`, but still have:

- `file_contents.canonical_file_instance_id IS NULL`

That leaves the system in a split state:

- Review/UI surfaces can still show a keep copy from the latest `CanonicalAssignment`
- Duplicate reclaim planning refuses to move files because the planner-safe canonical mapping is missing

## Audit Command

Use:

```bash
.venv/bin/python tools/audit_duplicate_reclaim_canonical_mapping.py
```

The command reports duplicate groups where:

1. the group still has more than one active file instance
2. a latest `CanonicalAssignment` exists
3. `FileContent.canonical_file_instance_id` is still missing

The output separates:

- groups that appear safe to backfill automatically
- groups that would still require manual review

## Auto-Backfillable Definition

A mismatch group is considered auto-backfillable only when all of the following are true for the latest `CanonicalAssignment`:

1. the assigned canonical file instance still exists
2. it belongs to the same `content_id`
3. it is still `ACTIVE`
4. `FileContent.canonical_file_instance_id` is currently `NULL`

If any of those checks fail, the row must not be backfilled automatically.

## Historical-Only Repair Command Design

The intended repair command is historical-only. It should operate only on rows where:

- `FileContent.canonical_file_instance_id IS NULL`
- a latest `CanonicalAssignment` exists
- the latest assignment passes the auto-backfillable checks above

Suggested command shape:

```bash
.venv/bin/python tools/backfill_duplicate_reclaim_canonical_mapping.py --dry-run
.venv/bin/python tools/backfill_duplicate_reclaim_canonical_mapping.py --apply
```

Recommended flags:

- `--dry-run`
  - default mode
  - prints counts and sample rows
- `--apply`
  - performs the actual backfill
- `--content-id <uuid>`
  - optional single-group repair for controlled testing
- `--limit <n>`
  - optional cap for staged rollout

## Repair Algorithm

For each candidate row, the repair command should:

1. load `FileContent` under lock
2. skip if `canonical_file_instance_id` is already populated
3. resolve the latest `CanonicalAssignment` using:
   - `assigned_at DESC`
   - `assignment_id DESC`
4. verify the assigned canonical instance:
   - exists
   - belongs to the same `content_id`
   - is `ACTIVE`
5. set `FileContent.canonical_file_instance_id` to that instance id
6. commit

## Safety Expectations

The repair must be:

- idempotent
  - reruns should skip already-filled rows
- narrow
  - historical-only; do not rewrite groups that already have planner-safe canonical mappings
- explicit
  - log updated rows, skipped rows, and skip reasons
- non-destructive
  - no filesystem mutation
  - no duplicate reclaim state changes

## Why This Repair Is Safe

This repair does not introduce a new canonical decision.

It only copies the already-effective latest `CanonicalAssignment` into the planner-side canonical field used by duplicate reclaim execution, but only when that assignment is still valid and active.

## Not Included

This note does not change:

- duplicate review semantics
- duplicate reclaim workflow semantics
- later recycle/purge semantics
- canonical policy selection logic
