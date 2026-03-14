# Example: Ingest to Apply End-to-End

This scenario demonstrates a full deterministic run.

## Commands

```bash
source .venv/bin/activate
media-manager-api &
curl -X POST http://127.0.0.1:8000/api/plan \
  -H 'Content-Type: application/json' \
  -d '{"folder_path":"/path/to/media","strict_metadata":false}'
curl -X POST http://127.0.0.1:8000/api/apply \
  -H 'Content-Type: application/json' \
  -d '{"run_id":"<RUN_ID>","collision_mode":"rename"}'
```

## Expected Response Shape

`plan` returns payload similar to:

```json
{
  "ok": true,
  "data": {
    "result": {
      "run_id": "<uuid>",
      "summary": {
        "scanned_count": 0,
        "move_actions": 0,
        "duplicate_actions": 0,
        "noop_actions": 0
      }
    }
  }
}
```

`apply` returns payload similar to:

```json
{
  "ok": true,
  "data": {
    "result": {
      "run_id": "<uuid>",
      "summary": {
        "applied_count": 0,
        "moves_count": 0,
        "duplicates_count": 0,
        "noop_count": 0,
        "skipped_count": 0,
        "errors_count": 0
      }
    }
  }
}
```

## Verification

- filesystem outcomes align with planned actions
- no unexpected errors in apply summary
- same input set produces consistent plan semantics
