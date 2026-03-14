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


class PlanningStateError(MediaManagerError):
    """Raised when planning is attempted from an invalid run state."""


class ApplyStateError(MediaManagerError):
    """Raised when apply is attempted from an invalid run state."""


class MissingRequiredMetadataError(MediaManagerError):
    """Raised when strict planning finds missing required metadata."""

    def __init__(self, content_id: str, file_instance_id: str, missing_codes: list[str]) -> None:
        missing_joined = ",".join(missing_codes)
        super().__init__(
            "Missing required metadata "
            f"(content_id={content_id}, file_instance_id={file_instance_id}, missing_codes={missing_joined})"
        )


class CollisionResolutionError(MediaManagerError):
    """Raised when apply cannot resolve a destination collision deterministically."""

    def __init__(self, original_target_path: str, collision_mode: str, attempt_count: int) -> None:
        super().__init__(
            "Collision resolution failed "
            f"(target={original_target_path}, collision_mode={collision_mode}, attempt_count={attempt_count})"
        )


class ApplyIntegrityException(MediaManagerError):
    """Raised when post-apply verification detects integrity violations."""


class CanonicalPolicyException(MediaManagerError):
    """Raised when canonical policy selection cannot deterministically resolve an instance."""


class PolicySettingsValidationError(MediaManagerError):
    """Raised when operator policy settings payload fails deterministic validation."""


class PolicySettingsVersionConflictError(MediaManagerError):
    """Raised when a policy update is based on a stale version."""


class CanonicalUnreadableError(MediaManagerError):
    """Raised when canonical instance cannot be read in current runtime."""

    def __init__(
        self,
        *,
        content_id: str,
        canonical_instance_id: str | None,
        canonical_path: str | None,
        reason: str,
        runtime_context: str | None = None,
    ) -> None:
        canonical_id = canonical_instance_id or "-"
        path = canonical_path or "-"
        context = runtime_context or "-"
        super().__init__(
            "Canonical unreadable "
            f"(content_id={content_id}, canonical_instance_id={canonical_id}, "
            f"canonical_path={path}, reason={reason}, runtime_context={context})"
        )
