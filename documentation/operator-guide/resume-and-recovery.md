# Resume and Recovery

Use this guide when a run is interrupted or partially applied.

## Recovery Checklist

1. Identify the affected `run_id`.
2. Confirm database availability and durability.
3. Re-run apply for the same run:

```bash
media-manager apply <RUN_ID>
```

4. Compare output summary against expected action counts.
5. Investigate any persistent error counts before reattempting.

## Rules

- Resume from durable boundaries only.
- Avoid ad-hoc manual file operations during recovery.
- Treat repeated failures as incidents requiring explicit diagnosis.
