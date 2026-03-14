# Run Lifecycle

The lifecycle is centered on deterministic planning, gated apply, and durable failure facts.

## Phases

1. Planning reads durable state and emits planned actions.
2. Apply consumes planned actions and records file actions.
3. Filesystem mutation only occurs after durable gating writes.
4. Failures are persisted as events with run and action identifiers.
5. Resume continues from durable boundaries only.

See also:

- [State Machine](../STATE_MACHINE.md)
- [Architecture Guardrails](../ARCHITECTURE_GUARDRAILS.md)
