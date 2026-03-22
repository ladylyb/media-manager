# Plan Workflow

Planning computes deterministic actions without filesystem mutation.

## Request

```bash
curl -X POST http://127.0.0.1:8000/api/plan \
  -H 'Content-Type: application/json' \
  -d '{
    "folder_path":"/path/to/media",
    "strict_metadata":false,
    "owner":"TripA",
    "context":"Family",
    "naming_strategy":"DUPLICATE_OWNS_DATE_STANDARDIZED",
    "owner_context_override_confirmed":false
  }'
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
- `owner` and `context` are now run-scoped naming inputs; defaults remain `LL` and `General`.
- `naming_strategy` controls how duplicate filenames are generated.
- If a duplicate-backed content group already has stored `owner/context`, the planner keeps those values unless `owner_context_override_confirmed=true`.
