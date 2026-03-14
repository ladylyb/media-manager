# Apply Workflow

Apply consumes planned state and executes gated filesystem operations.

## Command

```bash
media-manager apply <RUN_ID>
```

Optional collision handling:

```bash
media-manager apply <RUN_ID> --collision-mode rename
```

## Output Contract

- Grouped action sections
- Summary counters including errors

## Safety Notes

- Apply should only execute against a valid planned run.
- If apply is interrupted, use the same run identifier for controlled recovery.
- Do not perform manual filesystem edits mid-run.
