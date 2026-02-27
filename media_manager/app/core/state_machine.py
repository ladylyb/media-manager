"""Run state machine with deterministic transition validation.

No persistence logic belongs in this module.
"""

from __future__ import annotations

from enum import StrEnum

from media_manager.app.core.errors import InvalidRunTransitionError


class RunState(StrEnum):
    CREATED = "CREATED"
    PLANNED = "PLANNED"
    APPLYING = "APPLYING"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


VALID_TRANSITIONS: dict[RunState, tuple[RunState, ...]] = {
    RunState.CREATED: (RunState.PLANNED,),
    RunState.PLANNED: (RunState.APPLYING,),
    RunState.APPLYING: (RunState.COMPLETED, RunState.FAILED),
    RunState.FAILED: (RunState.APPLYING,),
    RunState.COMPLETED: (),
    RunState.ABORTED: (),
}


def validate_transition(current: RunState, next_state: RunState) -> None:
    """Validate the next transition according to the deterministic state map."""
    allowed = VALID_TRANSITIONS[current]
    if next_state not in allowed:
        raise InvalidRunTransitionError(current.value, next_state.value)
