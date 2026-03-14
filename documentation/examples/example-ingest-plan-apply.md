# Example: Ingest to Apply End-to-End

This scenario demonstrates a full deterministic run.

## Commands

```bash
source .venv/bin/activate
media-manager plan /path/to/media
media-manager apply <RUN_ID>
```

## Expected Output Shape

`plan` emits sections similar to:

```text
MOVE
  /input/file1.mp4
    → /target/file1.mp4

DUPLICATE
  /input/file2.mp4

NOOP
  /input/file3.mp4

Summary
  Files scanned: <n>
  Moves: <n>
  Duplicates: <n>
  No-op: <n>
Run ID: <uuid>
```

`apply` emits sections similar to:

```text
Summary
  Files applied: <n>
  Moves: <n>
  Duplicates: <n>
  No-op: <n>
  Skipped: <n>
  Errors: <n>
Run ID: <uuid>
```

## Verification

- filesystem outcomes align with planned actions
- no unexpected errors in apply summary
- same input set produces consistent plan semantics
