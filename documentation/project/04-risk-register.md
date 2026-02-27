# Risk Register

| Document Authority | Scope |
| --- | --- |
| Authoritative for | Risk inventory, impact/likelihood framing, mitigation ownership |
| Not authoritative for | Exact implementation semantics or schema constraints |
| Canonical references | `06-operational-guardrails.md`, `07-unified-architecture-spec.md` |

## Risk Matrix

| Risk | Impact | Likelihood | Control / Mitigation |
| --- | ---: | ---: | --- |
| Data loss / overwrite | Severe | Medium | No overwrite policy, quarantine, collision rules, plan->apply, backups, stop-the-line |
| Partial execution without audit | Severe | High (historical) | Log intent before execution, state transitions, transactions, reconciliation command |
| Schema drift (code vs DB) | High | High | schema_version checks, migrations, automated startup validation |
| Wrong duplicate classification | Medium-High | Medium | human review pack, conservative scoring, thresholding, fixture regression suite |
| Path drift / stale paths | High | Medium | single resolver plus current_state view, never use `files.path` for now-state |
| Performance bottlenecks | Medium | Medium | indexes, batch queries, incremental hashing, profiling, 10k test harness |
| Long-running job failures | Medium | Medium | checkpoints, resumability, per-action state, timeouts, explicit retries via resume |
| Operator error (wrong root) | High | Medium | config validation, explicit root allowlist, danger summary before apply |
| Cross-platform path issues | Medium | Medium | path normalization, pathlib, avoid hard-coded Windows paths |
