# Run State Machine

States:

- CREATED
- PLANNED
- APPLYING
- FAILED
- COMPLETED
- ABORTED

Allowed transitions:

CREATED -> PLANNED
PLANNED -> APPLYING
APPLYING -> COMPLETED
APPLYING -> FAILED
FAILED -> APPLYING (resume)
ANY -> ABORTED (manual)

Invalid transitions must error.

---

# Planned Action State

- PENDING
- LOCKED
- EXECUTING
- SUCCEEDED
- FAILED

No action may skip states.
FAILED actions must have failure_event.