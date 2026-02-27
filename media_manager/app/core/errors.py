"""Error types used by deterministic state transitions and persistence services."""

from __future__ import annotations


class MediaManagerError(Exception):
    """Base error for the media manager foundation."""


class InvalidRunTransitionError(MediaManagerError):
    """Raised when a run state transition is not allowed by the state machine."""

    def __init__(self, current_state: str, next_state: str) -> None:
        super().__init__(
            f"Invalid run transition: {current_state} -> {next_state}. "
            "Allowed transitions are explicitly constrained."
        )


class RunNotFoundError(MediaManagerError):
    """Raised when a run identifier cannot be found."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"Run not found: {run_id}")


class TransitionConflictError(MediaManagerError):
    """Raised when persistence constraints reject a transition (e.g., concurrent APPLYING)."""


class AppendOnlyViolationError(MediaManagerError):
    """Raised when an append-only model is mutated unexpectedly."""
