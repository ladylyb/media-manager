# Test Strategy

| Document Authority | Scope |
| --- | --- |
| Authoritative for | Test taxonomy, risk-to-test mapping, verification classes |
| Not authoritative for | Runtime state machine definitions, schema contracts |
| Canonical references | `04-risk-register.md`, `06-operational-guardrails.md`, `07-unified-architecture-spec.md` |

## Coverage Areas

### Unit Tests (Core Logic)
- Media type inference and mismatch rules
- Path resolver (effective path derivation)
- Duplicate scoring function (deterministic)
- Canonical selection rules
- Collision naming function (deterministic)

### Integration Tests (DB + Filesystem Sandbox)
- Use a temp directory tree plus temp SQLite DB
- Run: scan -> plan -> apply -> verify filesystem and DB statuses
- Assert expected files moved, action statuses updated, and resume behavior

### Regression Tests (Golden Fixtures)
- Curated fixture trees with known edge cases:
  - same-name collisions
  - unicode filenames
  - EXIF missing vs present
  - same content different names
  - already organized rerun
- Snapshot expected plans and audit outputs

### Performance Tests (10k+ Simulation)
- Synthetic generator:
  - create N files with controlled sizes and timestamps (no huge media required)
  - mock metadata extraction where needed
- Benchmarks:
  - scan throughput
  - planning time
  - DB write rate
  - apply throughput

### Safety Tests
- Idempotency: apply twice does nothing on second run
- Recovery: kill process mid-run and verify resume consistency
- Collision handling: target exists -> deterministic resolution, no overwrite
- Schema drift: older schema -> tool refuses with clear message
- Read-only mode: no write operations happen without `--apply`
