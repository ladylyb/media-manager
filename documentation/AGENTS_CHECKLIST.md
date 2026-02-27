# Agent Change Checklist

Before submitting change:

[ ] I verified no filesystem mutation occurs outside apply engine.
[ ] I defined crash behavior.
[ ] I defined retry behavior.
[ ] I defined resume behavior.
[ ] I validated state transitions.
[ ] I preserved idempotency.
[ ] I added failure events for new failure modes.
[ ] I did not introduce dual sources of truth.
[ ] I updated documentation if invariants changed.