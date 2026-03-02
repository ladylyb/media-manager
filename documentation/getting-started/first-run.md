# First Run

This page defines what a successful first run looks like.

## Preconditions

- Database is reachable.
- Input path exists and contains at least one file.
- You can execute `media-manager` from your virtualenv.

## Execute

```bash
media-manager plan /path/to/media
media-manager apply <RUN_ID_FROM_PLAN>
```

## Success Criteria

- `plan` prints grouped actions and a `Run ID`.
- `apply` completes and prints summary counters.
- No non-zero exit code.
- No unexpected filesystem mutations outside planned targets.

## If It Fails

- Re-run the same command and capture stderr.
- Confirm path and database configuration.
- Use [Resume and Recovery](../operator-guide/resume-and-recovery.md).
