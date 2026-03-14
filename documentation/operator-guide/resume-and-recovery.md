# Resume and Recovery

Use this guide when a run is interrupted or partially applied.

## Recovery Checklist

1. Identify the affected `run_id`.
2. Confirm database availability and durability.
3. Re-run apply for the same run:

```bash
curl -X POST http://127.0.0.1:8000/api/apply \
  -H 'Content-Type: application/json' \
  -d '{"run_id":"<RUN_ID>","collision_mode":"rename"}'
```

4. Compare output summary against expected action counts.
5. Investigate any persistent error counts before reattempting.

## Rules

- Resume from durable boundaries only.
- Avoid ad-hoc manual file operations during recovery.
- Treat repeated failures as incidents requiring explicit diagnosis.

## Decision Table

| Symptom | Immediate Action | Next Step |
| --- | --- | --- |
| Apply interrupted once | Re-run `POST /api/apply` for same `run_id` | Compare summary counters with prior run |
| Apply errors persist | Capture response payload and logs | Follow incident response |
| Filesystem state appears inconsistent | Pause further applies on same dataset | Run drift diagnosis |
