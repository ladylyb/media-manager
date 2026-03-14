# Apply Workflow

Apply consumes planned state and executes gated filesystem operations.

## Request

```bash
curl -X POST http://127.0.0.1:8000/api/apply \
  -H 'Content-Type: application/json' \
  -d '{"run_id":"<RUN_ID>","collision_mode":"rename"}'
```

Optional collision handling:

```bash
curl -X POST http://127.0.0.1:8000/api/apply \
  -H 'Content-Type: application/json' \
  -d '{"run_id":"<RUN_ID>","collision_mode":"skip"}'
```

## Output Contract

- `ok=true`
- `data.result.summary`, including error counts

## Safety Notes

- Apply should only execute against a valid planned run.
- If apply is interrupted, use the same run identifier for controlled recovery.
- Do not perform manual filesystem edits mid-run.
