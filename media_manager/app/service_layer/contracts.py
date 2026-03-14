"""Shared service-layer contracts for CLI and API adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def iso_now() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ServiceError:
    """Structured error payload shared by CLI/API envelopes."""

    code: str
    message: str
    details: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass(frozen=True)
class ServiceEnvelope:
    """Shared machine-readable envelope for service-layer outputs."""

    ok: bool
    workflow_version: str
    schema_version: str
    generated_at: str
    data: dict[str, object] = field(default_factory=dict)
    errors: tuple[ServiceError, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "workflow_version": self.workflow_version,
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "data": self.data,
            "errors": [item.to_dict() for item in self.errors],
        }
