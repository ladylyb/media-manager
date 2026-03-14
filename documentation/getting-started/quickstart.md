# Quickstart

This walkthrough gets you from install to a completed deterministic run through the REST API.

## 1. Prepare Environment

```bash
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.sample .env
```

Edit `.env` with your PostgreSQL URLs:

```bash
DATABASE_URL='postgresql+psycopg://user:password@localhost:5432/media_manager'
TEST_DATABASE_URL='postgresql+psycopg://user:password@localhost:5432/media_manager_test'
```

`media-manager-api` loads repo `.env` automatically.  
For all variables and defaults, see [Environment Variables](../reference/environment-variables.md).

## 2. Select Input Path

Choose a file or directory with media files.

Example:

```bash
INPUT_PATH=/path/to/media
```

## 3. Start The API

```bash
media-manager-api
```

## 4. Plan

```bash
curl -X POST http://127.0.0.1:8000/api/plan \
  -H 'Content-Type: application/json' \
  -d "{\"folder_path\":\"$INPUT_PATH\",\"strict_metadata\":false}"
```

Expected response:

- `ok: true`
- `data.result.run_id`
- `data.result.summary`

Save the emitted `run_id` for apply.

## 5. Apply Planned Actions

```bash
curl -X POST http://127.0.0.1:8000/api/apply \
  -H 'Content-Type: application/json' \
  -d '{"run_id":"<RUN_ID>","collision_mode":"rename"}'
```

## 6. Verify

- Filesystem changes should match planned actions.
- API response should show no unexpected errors.
- If interrupted, rerun with the same `RUN_ID` and inspect results.

## Next

- [First Run](first-run.md)
- [Ingest Workflow](../guides/ingest-workflow.md)
- [Plan Workflow](../guides/plan-workflow.md)
- [Apply Workflow](../guides/apply-workflow.md)
- [Practical Examples](../examples/index.md)
