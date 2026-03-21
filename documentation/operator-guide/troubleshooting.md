# Troubleshooting

## Command Fails Immediately

- Verify virtualenv is active.
- Verify database configuration (`DATABASE_URL`).
- Verify input path exists.

### PostgreSQL Socket Error On Startup

- Symptom: `connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed`
- Usual cause: `DATABASE_URL` resolved without a hostname, so psycopg fell back to a local Unix socket.
- Check for unresolved placeholders such as `${WINDOWS_DB_HOST}` in `.env`.
- Fix by setting an explicit host in `DATABASE_URL`, for example `postgresql+psycopg://user:password@localhost:5432/media_manager`.

## Plan Does Not Produce Expected Actions

- Confirm ingest scope and input path.
- Re-run with same inputs to check determinism.
- Review metadata quality if strict mode is enabled.

## Apply Reports Errors

- Capture stderr and summary counters.
- Re-run with same `run_id` after resolving root cause.
- Follow [Resume and Recovery](resume-and-recovery.md).

## Decision Table

| Condition | Action | Escalate When |
| --- | --- | --- |
| Command exits non-zero before run starts | Check env, path, DB connectivity | Same error repeats after config fix |
| Plan output unexpected | Re-check input scope and metadata quality | Repeated deterministic mismatch |
| Apply reports errors | Re-run same `run_id` after remediation | Error count persists across reruns |
