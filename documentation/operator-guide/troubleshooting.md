# Troubleshooting

## Command Fails Immediately

- Verify virtualenv is active.
- Verify database configuration (`DATABASE_URL`).
- Verify input path exists.

## Plan Does Not Produce Expected Actions

- Confirm ingest scope and input path.
- Re-run with same inputs to check determinism.
- Review metadata quality if strict mode is enabled.

## Apply Reports Errors

- Capture stderr and summary counters.
- Re-run with same `run_id` after resolving root cause.
- Follow [Resume and Recovery](resume-and-recovery.md).
