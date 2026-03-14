# Quickstart

This walkthrough gets you from install to a completed deterministic run.

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

`media-manager` loads repo `.env` automatically.  
For all variables and defaults, see [Environment Variables](../reference/environment-variables.md).

## 2. Select Input Path

Choose a file or directory with media files.

Example:

```bash
INPUT_PATH=/path/to/media
```

## 3. Ingest and Plan

```bash
media-manager plan "$INPUT_PATH"
```

Expected output sections:

- `MOVE`
- `DUPLICATE`
- `NOOP`
- `Summary`
- `Run ID: <uuid>`

Save the emitted `Run ID` for apply.

## 4. Apply Planned Actions

```bash
media-manager apply <RUN_ID>
```

Expected output sections:

- `MOVE`
- `DUPLICATE`
- `NOOP`
- `Summary`

## 5. Verify

- Filesystem changes should match planned actions.
- Run summary should show no unexpected errors.
- If interrupted, rerun with the same `RUN_ID` and inspect results.

## Next

- [First Run](first-run.md)
- [Ingest Workflow](../guides/ingest-workflow.md)
- [Plan Workflow](../guides/plan-workflow.md)
- [Apply Workflow](../guides/apply-workflow.md)
- [Practical Examples](../examples/index.md)
