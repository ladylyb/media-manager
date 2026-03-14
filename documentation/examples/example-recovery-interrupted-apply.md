# Example: Recovery After Interrupted Apply

This scenario covers a run interrupted during apply.

## Recovery Commands

```bash
source .venv/bin/activate
curl -X POST http://127.0.0.1:8000/api/apply \
  -H 'Content-Type: application/json' \
  -d '{"run_id":"<RUN_ID>","collision_mode":"rename"}'
```

## Expected Behavior

- apply resumes from durable boundary behavior
- summary counters reflect remaining work and any errors
- repeated retries without root-cause resolution should be treated as incidents

## Operator Checklist

1. capture `run_id` and timestamp
2. capture response payload and server logs
3. re-run apply for same `run_id`
4. compare results to prior plan/apply summary
5. escalate if drift or repeated errors persist
