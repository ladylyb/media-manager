"""Service-layer errors and mapping helpers."""

from __future__ import annotations

from dataclasses import dataclass

from media_manager.app.core.errors import (
    MediaManagerError,
    OwnerContextClassificationRequiredError,
    OwnerContextOverrideRequiredError,
    PolicySettingsValidationError,
    PolicySettingsVersionConflictError,
)
from media_manager.app.service_layer.contracts import ServiceError


@dataclass
class ServiceLayerException(Exception):
    code: str
    message: str
    http_status: int
    details: dict[str, object] | None = None

    def to_service_error(self) -> ServiceError:
        return ServiceError(code=self.code, message=self.message, details=self.details)


def map_exception(exc: Exception) -> ServiceLayerException:
    """Normalize exceptions into deterministic service-layer taxonomy."""
    if isinstance(exc, ServiceLayerException):
        return exc
    if isinstance(exc, PolicySettingsValidationError):
        return ServiceLayerException(code="VALIDATION_ERROR", message=str(exc), http_status=400)
    if isinstance(exc, PolicySettingsVersionConflictError):
        return ServiceLayerException(code="STATE_CONFLICT", message=str(exc), http_status=400)
    if isinstance(exc, OwnerContextOverrideRequiredError):
        return ServiceLayerException(
            code="OWNER_CONTEXT_OVERRIDE_REQUIRED",
            message=(
                "This batch matches existing content with different saved owner/context values. "
                "Confirm the override to correct the existing content group and corresponding canonical item."
            ),
            http_status=400,
            details=exc.details,
        )
    if isinstance(exc, OwnerContextClassificationRequiredError):
        return ServiceLayerException(
            code="OWNER_CONTEXT_CLASSIFICATION_REQUIRED",
            message=(
                "This batch still contains content with unclassified owner/context metadata. "
                "Choose explicit owner/context values in Plan before naming can continue."
            ),
            http_status=400,
            details=exc.details,
        )
    if isinstance(exc, ValueError):
        return ServiceLayerException(code="VALIDATION_ERROR", message=str(exc), http_status=400)
    if isinstance(exc, MediaManagerError):
        return ServiceLayerException(code="DOMAIN_CONFLICT", message=str(exc), http_status=400)
    return ServiceLayerException(code="INTERNAL_ERROR", message=str(exc), http_status=500)
