# Ingest Workflow

Use ingest to populate content and file-instance records before planning.

## Command

```bash
media-manager ingest /path/to/media
```

## Expected Output

`Ingest Summary` includes:

- files scanned
- new contents
- new instances
- duplicates detected
- metadata extracted
- duration

## Notes

- Ingest can be run independently before `plan`.
- `plan` also performs ingest by default for its input set.
