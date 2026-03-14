# First Run

This page defines what a successful first run looks like.

## Preconditions

- Database is reachable.
- Input path exists and contains at least one file.
- The API server is running locally.

## Execute

```bash
curl -X POST http://127.0.0.1:8000/api/plan \
  -H 'Content-Type: application/json' \
  -d '{"folder_path":"/path/to/media","strict_metadata":false}'

curl -X POST http://127.0.0.1:8000/api/apply \
  -H 'Content-Type: application/json' \
  -d '{"run_id":"<RUN_ID_FROM_PLAN>","collision_mode":"rename"}'
```

## Success Criteria

- `plan` returns `ok=true` and a durable `run_id`.
- `apply` completes and returns summary counters.
- No unexpected 4xx/5xx response.
- No unexpected filesystem mutations outside planned targets.

## If It Fails

- Re-run the same API call and capture the error payload.
- Confirm path and database configuration.
- Use [Resume and Recovery](../operator-guide/resume-and-recovery.md).
