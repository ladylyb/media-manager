# CLI API

::: media_manager.app.cli

## Ingest Dry-Run Validation

`media-manager ingest <path> --dry-run` runs read-only ingest validation and returns a would-change report.

- No DB writes occur in this mode.
- `--json` is supported only with `--dry-run`:
  - `media-manager ingest <path> --dry-run --json`
