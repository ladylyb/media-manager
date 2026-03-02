# Plan Workflow

Planning computes deterministic actions without filesystem mutation.

## Command

```bash
media-manager plan /path/to/media
```

Optional strict metadata mode:

```bash
media-manager plan /path/to/media --strict-metadata
```

## Output Contract

- Grouped action sections (`MOVE`, `DUPLICATE`, `NOOP`)
- Summary counters
- Durable `Run ID`

## Important

- Keep the `Run ID`; it is required for `apply`.
- Planning is expected to be deterministic for identical durable inputs.
