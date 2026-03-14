# Plan Workflow

Planning computes deterministic actions without filesystem mutation.

## Request

```bash
curl -X POST http://127.0.0.1:8000/api/plan \
  -H 'Content-Type: application/json' \
  -d '{"folder_path":"/path/to/media","strict_metadata":false}'
```

Optional strict metadata mode:

```bash
curl -X POST http://127.0.0.1:8000/api/plan \
  -H 'Content-Type: application/json' \
  -d '{"folder_path":"/path/to/media","strict_metadata":true}'
```

## Output Contract

- `ok=true`
- `data.result.summary`
- durable `data.result.run_id`

## Important

- Keep the `run_id`; it is required for `apply`.
- Planning is expected to be deterministic for identical durable inputs.
