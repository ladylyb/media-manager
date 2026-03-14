# Ingest Workflow

Use the ingest endpoint to populate content and file-instance records before planning.

## Request

```bash
curl -X POST http://127.0.0.1:8000/api/ingest \
  -H 'Content-Type: application/json' \
  -d '{"folder_path":"/path/to/media","dry_run":false}'
```

## Expected Response

`data.result.summary` includes:

- files scanned
- new contents
- new instances
- duplicates detected
- metadata extracted
- duration

## Notes

- Ingest can be run independently before `plan`.
- `plan` also performs ingest by default for its input set.
