# Incident Response

Use this playbook for high-signal failures in planning/apply/canonical operations.

## Severity Heuristics

- Sev-1: active unsafe mutation risk or broad data integrity concern
- Sev-2: blocked run pipeline with deterministic recovery path
- Sev-3: isolated run failure with low blast radius

## Response Steps

1. Identify incident owner.
2. Capture run context (`run_id`, command, phase, timestamp).
3. Halt further high-risk operations on same input set.
4. Collect logs and summary outputs.
5. Execute minimal safe recovery action.
6. Document outcome and residual risk.

## Required Incident Notes

- trigger condition
- impacted scope
- executed commands
- whether retry succeeded
- follow-up fix ticket link

## Post-Incident

- add or update runbook guidance if diagnosis was non-obvious
- add regression test coverage when behavior bug is confirmed
- ensure docs reflect actual operator workflow
