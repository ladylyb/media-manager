"""FastAPI entrypoint for the Media Manager Operator Console."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import logging
import os
from pathlib import Path
import threading
import time
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from media_manager.app.core.logging_buffer import get_buffered_logs
from media_manager.app.observability import mount_metrics_endpoint
from media_manager.app.persistence.base import create_db_engine, create_session_factory
from media_manager.app.persistence.operator_console import OperatorConsoleReadService
from media_manager.app.persistence.models import TagSource
from media_manager.app.service_layer import (
    AdminServices,
    OperationServices,
    ReadServices,
    ServiceCache,
    ServiceEnvelope,
    ServiceError,
    ServiceLayerException,
    iso_now,
    map_exception,
    schema_version,
)

LOGGER = logging.getLogger(__name__)
_MUTATION_SEMAPHORE = threading.BoundedSemaphore(value=4)
_TRUTHY_ENV = {"1", "true", "yes", "on"}


class _LogsEndpointAccessFilter(logging.Filter):
    """Reduce `/logs` polling noise unless the server is running in DEBUG."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "uvicorn.access":
            return True

        message = record.getMessage()
        if "\"GET /logs" not in message:
            return True

        if logging.getLogger().getEffectiveLevel() > logging.DEBUG:
            return False

        record.levelno = logging.DEBUG
        record.levelname = logging.getLevelName(logging.DEBUG)
        return True


def _install_logs_endpoint_access_filter() -> None:
    """Keep high-frequency `/logs` access records out of INFO-level server logs."""
    access_logger = logging.getLogger("uvicorn.access")
    if any(isinstance(existing, _LogsEndpointAccessFilter) for existing in access_logger.filters):
        return
    access_logger.addFilter(_LogsEndpointAccessFilter())


@lru_cache(maxsize=1)
def get_operator_console_service() -> OperatorConsoleReadService:
    """Build and cache the read-only Operator Console service."""
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    return OperatorConsoleReadService(session_factory)


@lru_cache(maxsize=1)
def get_service_session_factory():
    """Build and cache shared session factory for service-layer adapters."""
    engine = create_db_engine()
    return create_session_factory(engine)


@lru_cache(maxsize=1)
def get_service_cache() -> ServiceCache:
    """Build and cache in-process read cache."""
    return ServiceCache()


@lru_cache(maxsize=1)
def get_read_services() -> ReadServices:
    """Build read/query service-layer adapter."""
    return ReadServices(session_factory=get_service_session_factory(), cache=get_service_cache())


@lru_cache(maxsize=1)
def get_operation_services() -> OperationServices:
    """Build mutation/validation service-layer adapter."""
    return OperationServices(session_factory=get_service_session_factory(), cache=get_service_cache())


@lru_cache(maxsize=1)
def get_admin_services() -> AdminServices:
    """Build admin service-layer adapter."""
    return AdminServices(session_factory=get_service_session_factory())


class PolicyUpdatePayload(BaseModel):
    """Structured update payload for operator policy settings."""

    selected_policy: str
    naming_strategy: str = "SHARED_CANONICAL_NAME"
    preferred_roots: list[str] = Field(default_factory=list)
    integrity_scan_default_mode: str = "FAST"
    integrity_issue_min_confidence: float = 0.9
    integrity_notify_on_high_confidence: bool = True
    duplicate_reclaim_archive_root: str = "/tmp/media-manager/reclaim"
    duplicate_reclaim_default_retention_days: int = 14
    duplicate_reclaim_notify_on_reviewed_safe: bool = True
    integrity_quarantine_root: str = "/tmp/media-manager/quarantine"
    integrity_quarantine_retention_days: int = 14
    recycle_bin_root: str = "/tmp/media-manager/recycle-bin"
    recycle_purge_days: int = 30
    automation_mode: str = "NOTIFY_ONLY"
    recanonicalization_enabled: bool
    version: int


class RunTriggerPayload(BaseModel):
    """Structured payload for operator-initiated run execution."""

    folder_path: str
    policy_name: str
    dry_run: bool = False
    owner: str = "LL"
    context: str = "General"
    naming_strategy: str = "SHARED_CANONICAL_NAME"
    owner_context_override_confirmed: bool = False


class MediaFileValidatePayload(BaseModel):
    """Validation payload for read-only ingest reconciliation checks."""

    folder_path: str
    policy_name: str | None = None


class TagEnrichmentPayload(BaseModel):
    """Structured payload for operator-triggered tag enrichment."""

    model_config = ConfigDict(populate_by_name=True)

    run_all: bool = Field(default=False, alias="all")
    canonical_id: str | None = None
    batch_size: int = 100
    source: str = TagSource.SYSTEM.value


class DbResetPayload(BaseModel):
    """Payload for safe development database reset operations."""

    dry_run: bool = True
    challenge_word: str | None = None


class MetadataBenchmarkPayload(BaseModel):
    """Payload for admin metadata benchmark queue requests."""

    items: int = 1000
    batch_size: int = 250
    challenge_word: str | None = None


class DiscoveryBenchmarkPayload(BaseModel):
    """Payload for admin discovery benchmark queue requests."""

    items: int = 1000
    challenge_word: str | None = None


class IngestPayload(BaseModel):
    """Payload for ingest-only operations."""

    folder_path: str
    dry_run: bool = True


class PlanPayload(BaseModel):
    """Payload for planning-only operations."""

    folder_path: str
    strict_metadata: bool = False
    owner: str = "LL"
    context: str = "General"
    naming_strategy: str = "SHARED_CANONICAL_NAME"
    owner_context_override_confirmed: bool = False


class ApplyPayload(BaseModel):
    """Payload for apply-only operations."""

    run_id: str
    collision_mode: str = "rename"


class CanonicalRecomputePayload(BaseModel):
    """Payload for canonical recompute operations."""

    policy_name: str
    dry_run: bool = True
    preferred_roots: list[str] = Field(default_factory=list)


class DuplicateReviewPayload(BaseModel):
    """Payload for durable duplicate review decisions."""

    content_id: str
    review_status: str
    reviewed_canonical_instance_id: str
    reviewed_by: str | None = None


class DuplicateReclaimPayload(BaseModel):
    """Payload for durable duplicate reclaim readiness decisions."""

    content_id: str
    reclaim_status: str
    reviewed_by: str | None = None


class IntegrityScanPayload(BaseModel):
    """Payload for read-only integrity scans."""

    mode: str = "FAST"
    file_instance_ids: list[str] = Field(default_factory=list)


class IntegrityReviewPayload(BaseModel):
    """Payload for read-only integrity review decisions."""

    check_id: str
    decision: str
    reviewed_by: str | None = None


class IntegrityQuarantinePayload(BaseModel):
    check_id: str


class IntegrityRestorePayload(BaseModel):
    file_instance_id: str


class IntegrityPlaybackFailurePayload(BaseModel):
    file_instance_id: str


class DuplicateReclaimExecutePayload(BaseModel):
    content_ids: list[str] = Field(default_factory=list)
    retention_days: int | None = None


class DuplicateReclaimRestorePayload(BaseModel):
    file_instance_ids: list[str] = Field(default_factory=list)


class RetentionRecyclePayload(BaseModel):
    workflow: str
    file_instance_ids: list[str] = Field(default_factory=list)


class RetentionPurgePayload(BaseModel):
    workflow: str
    file_instance_ids: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class _DiscoveryQueryArgs:
    page: int
    limit: int
    tags: tuple[str, ...]
    sort_by: str
    sort_order: str
    source: TagSource | None
    min_confidence: float | None


def _parse_paging_args(*, page: int, limit: int) -> tuple[int, int]:
    parsed_page = int(page)
    parsed_limit = int(limit)
    if parsed_page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1.")
    if parsed_limit < 1 or parsed_limit > 100:
        raise HTTPException(status_code=400, detail="limit must be within [1, 100].")
    return parsed_page, parsed_limit


def _require_non_empty(value: str | None, field_name: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail=f"{field_name} must not be empty.")
    return normalized


def _resolve_console_static_dir(package_root: Path) -> Path:
    """Return the runtime frontend build directory."""
    return package_root / "gui_app" / "dist"


def _parse_sample_limit(value: int) -> int:
    parsed = int(value)
    if parsed < 1 or parsed > 200:
        raise HTTPException(status_code=400, detail="sample_limit must be within [1, 200].")
    return parsed


def _api_reload_enabled() -> bool:
    raw = os.getenv("MEDIA_MANAGER_API_RELOAD", "false")
    return raw.strip().lower() in _TRUTHY_ENV


def _directory_picker_enabled() -> bool:
    raw = os.getenv("MEDIA_MANAGER_DIRECTORY_PICKER_ENABLED", "false")
    return raw.strip().lower() in _TRUTHY_ENV


def _directory_picker_roots() -> tuple[Path, ...]:
    raw = os.getenv("MEDIA_MANAGER_DIRECTORY_PICKER_ROOTS", "")
    roots: list[Path] = []
    for item in raw.split(","):
        normalized = item.strip()
        if not normalized:
            continue
        path = Path(normalized)
        if not path.is_absolute():
            LOGGER.warning("Skipping non-absolute directory picker root", extra={"path": normalized})
            continue
        try:
            resolved = path.resolve()
        except Exception:
            LOGGER.warning("Skipping unresolvable directory picker root", extra={"path": normalized})
            continue
        if not resolved.exists() or not resolved.is_dir():
            LOGGER.warning("Skipping non-directory picker root", extra={"path": str(resolved)})
            continue
        roots.append(resolved)
    return tuple(roots)


def _directory_picker_label(path: Path) -> str:
    return path.name or str(path)


def _directory_picker_root_for(path: Path, roots: tuple[Path, ...]) -> Path | None:
    for root in sorted(roots, key=lambda item: len(item.parts), reverse=True):
        try:
            path.relative_to(root)
            return root
        except ValueError:
            continue
    return None


def _directory_picker_capability_payload() -> dict[str, object]:
    roots = _directory_picker_roots()
    enabled = _directory_picker_enabled() and bool(roots)
    return {
        "enabled": enabled,
        "roots": [{"label": _directory_picker_label(root), "path": str(root)} for root in roots],
    }


def _directory_picker_listing_payload(path_value: str) -> dict[str, object]:
    if not _directory_picker_enabled():
        raise ServiceLayerException(code="NOT_FOUND", message="Directory picker is disabled.", http_status=404)

    roots = _directory_picker_roots()
    if not roots:
        raise ServiceLayerException(
            code="NOT_FOUND",
            message="Directory picker roots are not configured.",
            http_status=404,
        )

    requested = _require_non_empty(path_value, "path")
    candidate = Path(requested)
    if not candidate.is_absolute():
        raise ServiceLayerException(
            code="VALIDATION_ERROR",
            message="path must be an absolute directory path.",
            http_status=400,
        )

    try:
        resolved = candidate.resolve()
    except Exception as exc:
        raise ServiceLayerException(
            code="VALIDATION_ERROR",
            message=f"Unable to resolve directory path: {requested}",
            http_status=400,
        ) from exc

    if not resolved.exists():
        raise ServiceLayerException(code="NOT_FOUND", message=f"Directory not found: {resolved}", http_status=404)
    if not resolved.is_dir():
        raise ServiceLayerException(
            code="VALIDATION_ERROR",
            message=f"Path must be a directory: {resolved}",
            http_status=400,
        )

    root = _directory_picker_root_for(resolved, roots)
    if root is None:
        raise ServiceLayerException(
            code="VALIDATION_ERROR",
            message="Requested path is outside configured directory picker roots.",
            http_status=400,
        )

    parent_path: str | None = None
    if resolved != root:
        parent = resolved.parent.resolve()
        if _directory_picker_root_for(parent, roots) == root:
            parent_path = str(parent)

    directories = []
    for child in sorted(resolved.iterdir(), key=lambda item: item.name.lower()):
        try:
            child_resolved = child.resolve()
        except Exception:
            continue
        if not child_resolved.is_dir():
            continue
        if _directory_picker_root_for(child_resolved, roots) != root:
            continue
        directories.append({"name": child_resolved.name, "path": str(child_resolved)})

    return {
        "current_path": str(resolved),
        "parent_path": parent_path,
        "directories": directories,
    }


def _v2_ok(*, data: dict[str, object]) -> JSONResponse:
    session_factory = get_service_session_factory()
    payload = ServiceEnvelope(
        ok=True,
        workflow_version="v2-service-layer",
        schema_version=schema_version(session_factory),
        generated_at=iso_now(),
        data=data,
        errors=(),
    ).to_dict()
    return JSONResponse(status_code=200, content=payload)


def _v2_error(*, http_status: int, code: str, message: str, details: dict[str, object] | None = None) -> JSONResponse:
    session_factory = get_service_session_factory()
    payload = ServiceEnvelope(
        ok=False,
        workflow_version="v2-service-layer",
        schema_version=schema_version(session_factory),
        generated_at=iso_now(),
        data={},
        errors=(ServiceError(code=code, message=message, details=details),),
    ).to_dict()
    return JSONResponse(status_code=http_status, content=payload)


def _api_json_envelope_enabled(path: str) -> bool:
    """Return whether a path should use the canonical JSON service envelope on errors."""
    return path.startswith("/api/") and not (
        path.startswith("/api/thumbnail/") or path.startswith("/api/video-thumbnail/")
    )


def _execute_read(name: str, fn) -> JSONResponse:  # type: ignore[no-untyped-def]
    started = time.perf_counter()
    try:
        result = fn()
    except Exception as exc:
        mapped = map_exception(exc)
        LOGGER.exception(
            "v2 read operation failed",
            extra={"operation": name, "error_code": mapped.code, "phase": "operator_console", "action": "V2_READ"},
        )
        return _v2_error(http_status=mapped.http_status, code=mapped.code, message=mapped.message, details=mapped.details)
    duration_ms = (time.perf_counter() - started) * 1000.0
    LOGGER.info(
        "v2 read operation completed",
        extra={"operation": name, "duration_ms": duration_ms, "phase": "operator_console", "action": "V2_READ"},
    )
    return _v2_ok(data={"result": result})


def _execute_mutation(name: str, fn) -> JSONResponse:  # type: ignore[no-untyped-def]
    if not _MUTATION_SEMAPHORE.acquire(blocking=False):
        return _v2_error(http_status=503, code="OVERLOADED", message="Mutation concurrency limit reached.")
    started = time.perf_counter()
    try:
        result = fn()
    except Exception as exc:
        mapped = map_exception(exc)
        log_extra = {"operation": name, "error_code": mapped.code, "phase": "operator_console", "action": "V2_MUTATION"}
        # Expected validation/domain conflicts are logged without traceback noise.
        if 400 <= mapped.http_status < 500:
            LOGGER.warning("v2 mutation rejected", extra=log_extra)
        else:
            LOGGER.exception("v2 mutation failed", extra=log_extra)
        return _v2_error(http_status=mapped.http_status, code=mapped.code, message=mapped.message, details=mapped.details)
    finally:
        _MUTATION_SEMAPHORE.release()
    duration_ms = (time.perf_counter() - started) * 1000.0
    LOGGER.info(
        "v2 mutation completed",
        extra={"operation": name, "duration_ms": duration_ms, "phase": "operator_console", "action": "V2_MUTATION"},
    )
    return _v2_ok(data={"result": result})


def _parse_discovery_query_args(
    *,
    page: int,
    limit: int,
    tags: str | None,
    sort_by: str,
    sort_order: str | None,
    source: str | None,
    min_confidence: float | None,
) -> _DiscoveryQueryArgs:
    normalized_sort_by = sort_by.strip().lower()
    if normalized_sort_by not in {"created_at", "tag_name", "confidence_score"}:
        raise HTTPException(status_code=400, detail="sort_by must be created_at, tag_name, or confidence_score.")

    if sort_order is None:
        normalized_sort_order = "asc" if normalized_sort_by == "tag_name" else "desc"
    else:
        normalized_sort_order = sort_order.strip().lower()
        if normalized_sort_order not in {"asc", "desc"}:
            raise HTTPException(status_code=400, detail="sort_order must be asc or desc.")

    source_value: TagSource | None = None
    if source is not None:
        try:
            source_value = TagSource(source.strip().lower())
        except Exception as exc:
            raise HTTPException(status_code=400, detail="source must be ai, manual, import, or system.") from exc

    if min_confidence is not None and not 0.0 <= float(min_confidence) <= 1.0:
        raise HTTPException(status_code=400, detail="min_confidence must be within [0.0, 1.0].")

    tag_items: tuple[str, ...] = ()
    if tags is not None:
        tag_items = tuple(part.strip() for part in tags.split(",") if part.strip())

    return _DiscoveryQueryArgs(
        page=max(1, int(page)),
        limit=min(100, max(1, int(limit))),
        tags=tag_items,
        sort_by=normalized_sort_by,
        sort_order=normalized_sort_order,
        source=source_value,
        min_confidence=min_confidence,
    )


def create_app() -> FastAPI:
    """Create and configure the Operator Console FastAPI application."""
    package_root = Path(__file__).parent
    console_static_dir = _resolve_console_static_dir(package_root)
    console_static_index = console_static_dir / "index.html"

    # Polling `/logs` is intentional, but its access records should not dominate INFO logs.
    _install_logs_endpoint_access_filter()

    app = FastAPI(title="Media Manager Operator Console")
    app.mount("/static-v2", StaticFiles(directory=str(console_static_dir), check_dir=False), name="static-v2")
    mount_metrics_endpoint(app)

    @app.exception_handler(HTTPException)
    async def _handle_http_exception(request: Request, exc: HTTPException) -> Response:
        if _api_json_envelope_enabled(request.url.path):
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            return _v2_error(
                http_status=exc.status_code,
                code="VALIDATION_ERROR" if exc.status_code < 500 else "INTERNAL_ERROR",
                message=detail,
            )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation_error(request: Request, exc: RequestValidationError) -> Response:
        if _api_json_envelope_enabled(request.url.path):
            message = "; ".join(error["msg"] for error in exc.errors()) or "Request validation failed."
            return _v2_error(http_status=422, code="VALIDATION_ERROR", message=message, details={"errors": exc.errors()})
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    def _render_console_v2_shell() -> Response:
        if not console_static_index.exists():
            return HTMLResponse(
                status_code=503,
                content=(
                    "Operator Console v2 assets are missing. "
                    "Build frontend assets into operator_console/gui_app/dist/."
                ),
            )
        return FileResponse(path=console_static_index)

    @app.get("/favicon.ico")
    def favicon() -> Response:
        """Serve the root favicon expected by browsers and crawlers."""
        favicon_path = console_static_dir / "favicon.ico"
        if not favicon_path.exists():
            raise HTTPException(status_code=404, detail="favicon.ico was not found.")
        return FileResponse(path=favicon_path)

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> Response:
        """Render the Operator Console dashboard page."""
        return _render_console_v2_shell()

    @app.get("/runs", response_class=HTMLResponse)
    def runs_page() -> Response:
        """Render the Operator Console run history page."""
        return _render_console_v2_shell()

    @app.get("/policy", response_class=HTMLResponse)
    def policy_page() -> Response:
        """Render the Operator Console policy management page."""
        return _render_console_v2_shell()

    @app.get("/admin", response_class=HTMLResponse)
    def admin_page() -> Response:
        """Render Operator Console admin page."""
        return _render_console_v2_shell()

    @app.get("/admin/diagnostics", response_class=HTMLResponse)
    def admin_diagnostics_page() -> Response:
        """Render Operator Console admin diagnostics page."""
        return _render_console_v2_shell()

    @app.get("/operations", response_class=HTMLResponse)
    def operations_page() -> Response:
        """Render explicit operation controls for the supported API workflows."""
        return _render_console_v2_shell()

    @app.get("/duplicates", response_class=HTMLResponse)
    def duplicates_page() -> Response:
        """Render the Operator Console duplicate group browser page."""
        return _render_console_v2_shell()

    @app.get("/integrity", response_class=HTMLResponse)
    def integrity_page() -> Response:
        """Render the Operator Console integrity review page."""
        return _render_console_v2_shell()

    @app.get("/gallery", response_class=HTMLResponse)
    def gallery_page() -> Response:
        """Render the Operator Console canonical gallery page."""
        return _render_console_v2_shell()

    @app.get("/ledger", response_class=HTMLResponse)
    def ledger_page() -> Response:
        """Render legacy ledger entry route for the Operator Console SPA shell."""
        return _render_console_v2_shell()

    @app.get("/discover", response_class=HTMLResponse)
    def discover_page() -> Response:
        """Render read-only discovery explorer page."""
        return _render_console_v2_shell()

    @app.get("/pipeline-wizard", response_class=HTMLResponse)
    def pipeline_wizard_page() -> Response:
        """Render pipeline wizard page shell."""
        return _render_console_v2_shell()

    @app.get("/gallery/{file_id}", response_class=HTMLResponse)
    def gallery_detail_page(file_id: UUID) -> Response:
        """Render canonical media detail page shell."""
        _ = file_id
        return _render_console_v2_shell()

    @app.get("/logs")
    def recent_logs(limit: int = Query(default=100)) -> JSONResponse:
        """Support lightweight frontend polling of recent in-process logs."""
        parsed_limit = max(1, min(1000, int(limit)))
        return JSONResponse(content=get_buffered_logs(limit=parsed_limit))

    @app.get("/api/gallery/{file_id}")
    def canonical_gallery_detail(
        file_id: UUID,
        service: OperatorConsoleReadService = Depends(get_operator_console_service),
    ) -> JSONResponse:
        """Return detail for a canonical gallery item by durable file instance identifier."""
        detail = service.get_canonical_gallery_detail(file_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Canonical media item not found.")
        return _execute_read("canonical-gallery-detail", detail.to_dict)

    @app.get("/api/dashboard-summary")
    def dashboard_summary(
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        """Return aggregate library counters in the canonical API envelope."""
        return _execute_read("dashboard-summary", services.dashboard_summary)

    @app.get("/api/home")
    def home(
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        """Return media-first home page data in the canonical API envelope."""
        return _execute_read("home", services.home)

    @app.get("/api/latest-metrics")
    def latest_metrics(
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        """Return latest persisted performance metrics in the canonical API envelope."""
        return _execute_read("latest-metrics", services.latest_metrics)

    @app.get("/api/directory-picker/capability")
    def directory_picker_capability() -> JSONResponse:
        """Return whether the optional directory picker is enabled and which roots are browseable."""
        return _execute_read("directory-picker-capability", _directory_picker_capability_payload)

    @app.get("/api/directory-picker/list")
    def directory_picker_list(path: str | None = Query(default=None)) -> JSONResponse:
        """Return immediate child directories for a configured root or subdirectory."""
        normalized_path = _require_non_empty(path, "path")
        return _execute_read("directory-picker-list", lambda: _directory_picker_listing_payload(normalized_path))

    @app.get("/api/runs")
    def runs_history(
        limit: int = Query(default=50),
        operation_type: str | None = Query(default=None),
        status: str | None = Query(default=None),
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        """Return unified operation run history in the canonical API envelope."""
        parsed_limit = max(1, min(200, int(limit)))
        return _execute_read(
            "runs",
            lambda: services.runs(limit=parsed_limit, operation_type=operation_type, status=status),
        )

    @app.get("/api/status")
    def status_v2(
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        """Return status metadata envelope."""
        try:
            result = services.status()
        except Exception as exc:
            mapped = map_exception(exc)
            return _v2_error(
                http_status=mapped.http_status,
                code=mapped.code,
                message=mapped.message,
                details=mapped.details,
            )
        return _v2_ok(data=result)

    @app.get("/api/operation-runs")
    def operation_runs_v2(
        limit: int = Query(default=50),
        operation_type: str | None = Query(default=None),
        status: str | None = Query(default=None),
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        parsed_limit = max(1, min(200, int(limit)))
        return _execute_read(
            "operation-runs",
            lambda: services.operation_runs(limit=parsed_limit, operation_type=operation_type, status=status),
        )

    @app.get("/api/internal-runs")
    def internal_runs_v2(
        limit: int = Query(default=50),
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        parsed_limit = max(1, min(200, int(limit)))
        return _execute_read("internal-runs", lambda: services.internal_runs(limit=parsed_limit))

    @app.get("/api/canonical")
    def canonical_gallery_v2(
        page: int = 1,
        limit: int = 30,
        tags: str | None = Query(default=None),
        sort_by: str = Query(default="created_at"),
        sort_order: str | None = Query(default=None),
        source: str | None = Query(default=None),
        min_confidence: float | None = Query(default=None),
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        parsed = _parse_discovery_query_args(
            page=page,
            limit=limit,
            tags=tags,
            sort_by=sort_by,
            sort_order=sort_order,
            source=source,
            min_confidence=min_confidence,
        )
        return _execute_read(
            "canonical",
            lambda: services.canonical(
                page=parsed.page,
                limit=parsed.limit,
                tags=parsed.tags,
                sort_by=parsed.sort_by,
                sort_order=parsed.sort_order,
                source=parsed.source.value if parsed.source is not None else None,
                min_confidence=parsed.min_confidence,
            ),
        )

    @app.get("/api/canonical/tags")
    def canonical_tag_suggestions_v2(
        q: str | None = Query(default=None),
        limit: int = Query(default=10),
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        parsed_limit = min(50, max(1, int(limit)))
        return _execute_read(
            "canonical-tags",
            lambda: services.canonical_tags(q=q, limit=parsed_limit),
        )

    @app.get("/api/duplicates")
    def duplicates_v2(
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        return _execute_read("duplicates", services.duplicates)

    @app.get("/api/integrity/dashboard")
    def integrity_dashboard_v2(
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        return _execute_read("integrity-dashboard", services.integrity_dashboard)

    @app.get("/api/integrity/issues")
    def integrity_issues_v2(
        status: str | None = Query(default=None),
        min_confidence: float | None = Query(default=None),
        page: int = Query(default=1),
        limit: int = Query(default=30),
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        parsed_page, parsed_limit = _parse_paging_args(page=page, limit=limit)
        return _execute_read(
            "integrity-issues",
            lambda: services.integrity_issues(
                status=status,
                min_confidence=min_confidence,
                page=parsed_page,
                limit=parsed_limit,
            ),
        )

    @app.get("/api/integrity/quarantine/items")
    def integrity_quarantine_items_v2(
        page: int = Query(default=1),
        limit: int = Query(default=30),
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        parsed_page, parsed_limit = _parse_paging_args(page=page, limit=limit)
        return _execute_read(
            "integrity-quarantine-items",
            lambda: services.integrity_quarantine_items(page=parsed_page, limit=parsed_limit),
        )

    @app.get("/api/retention/recycle")
    def retention_recycle_items_v2(
        page: int = Query(default=1),
        limit: int = Query(default=30),
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        parsed_page, parsed_limit = _parse_paging_args(page=page, limit=limit)
        return _execute_read(
            "retention-recycle-items",
            lambda: services.retention_recycle_items(page=parsed_page, limit=parsed_limit),
        )

    @app.get("/api/integrity/file/{check_id}")
    def integrity_file_detail_v2(
        check_id: UUID,
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        detail = services.integrity_file_detail(check_id=str(check_id))
        if detail is None:
            raise HTTPException(status_code=404, detail="Integrity check not found.")
        return _execute_read("integrity-file", lambda: detail)

    @app.post("/api/duplicates/review")
    def duplicate_review_set_v2(
        payload: DuplicateReviewPayload,
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        return _execute_mutation(
            "duplicates-review",
            lambda: services.duplicate_review_set(
                content_id=payload.content_id,
                review_status=payload.review_status,
                reviewed_canonical_instance_id=payload.reviewed_canonical_instance_id,
                reviewed_by=payload.reviewed_by,
            ),
        )

    @app.post("/api/duplicates/reclaim")
    def duplicate_reclaim_set_v2(
        payload: DuplicateReclaimPayload,
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        return _execute_mutation(
            "duplicates-reclaim",
            lambda: services.duplicate_reclaim_set(
                content_id=payload.content_id,
                reclaim_status=payload.reclaim_status,
                reviewed_by=payload.reviewed_by,
            ),
        )

    @app.post("/api/duplicates/reclaim/execute")
    def duplicate_reclaim_execute_v2(
        payload: DuplicateReclaimExecutePayload,
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        return _execute_mutation(
            "duplicates-reclaim-execute",
            lambda: services.duplicate_reclaim_execute(
                content_ids=payload.content_ids,
                retention_days=payload.retention_days,
            ),
        )

    @app.get("/api/duplicates/reclaim/items")
    def duplicate_reclaim_items_v2(
        page: int = Query(default=1),
        limit: int = Query(default=30),
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        parsed_page, parsed_limit = _parse_paging_args(page=page, limit=limit)
        return _execute_read(
            "duplicates-reclaim-items",
            lambda: services.duplicate_reclaim_items(page=parsed_page, limit=parsed_limit),
        )

    @app.post("/api/duplicates/reclaim/restore")
    def duplicate_reclaim_restore_v2(
        payload: DuplicateReclaimRestorePayload,
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        return _execute_mutation(
            "duplicates-reclaim-restore",
            lambda: services.duplicate_reclaim_restore(file_instance_ids=payload.file_instance_ids),
        )

    @app.post("/api/retention/recycle")
    def retention_recycle_v2(
        payload: RetentionRecyclePayload,
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        workflow = payload.workflow.strip().lower()
        if workflow == "duplicates":
            return _execute_mutation(
                "retention-recycle-duplicates",
                lambda: services.retention_recycle_duplicates(file_instance_ids=payload.file_instance_ids),
            )
        if workflow == "integrity":
            return _execute_mutation(
                "retention-recycle-integrity",
                lambda: services.retention_recycle_integrity(file_instance_ids=payload.file_instance_ids),
            )
        raise HTTPException(status_code=400, detail="workflow must be one of: duplicates, integrity")

    @app.post("/api/retention/purge")
    def retention_purge_v2(
        payload: RetentionPurgePayload,
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        workflow = payload.workflow.strip().lower()
        if workflow == "duplicates":
            return _execute_mutation(
                "retention-purge-duplicates",
                lambda: services.retention_purge_duplicates(file_instance_ids=payload.file_instance_ids),
            )
        if workflow == "integrity":
            return _execute_mutation(
                "retention-purge-integrity",
                lambda: services.retention_purge_integrity(file_instance_ids=payload.file_instance_ids),
            )
        raise HTTPException(status_code=400, detail="workflow must be one of: duplicates, integrity")

    @app.post("/api/integrity/scan")
    def integrity_scan_v2(
        payload: IntegrityScanPayload,
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        normalized_mode = payload.mode.strip().upper()
        requested_file_count = len(payload.file_instance_ids)
        scan_scope = "EXPLICIT_FILE_IDS" if payload.file_instance_ids else "DEFAULT_ACTIVE_LIBRARY"
        LOGGER.info(
            (
                f"POST /api/integrity/scan received: mode={normalized_mode} "
                f"requested_file_count={requested_file_count} scan_scope={scan_scope}"
            ),
            extra={
                "phase": "operator_console",
                "stage": "integrity_scan",
                "status": "received",
                "action": "manual_integrity_scan_request",
                "action_type": "api_request",
                "total_count": requested_file_count,
                "scope": scan_scope,
            },
        )
        return _execute_mutation(
            "integrity-scan",
            lambda: services.integrity_scan(
                mode=payload.mode,
                file_instance_ids=payload.file_instance_ids,
            ),
        )

    @app.post("/api/integrity/playback-failure")
    def integrity_playback_failure_v2(
        payload: IntegrityPlaybackFailurePayload,
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        return _execute_mutation(
            "integrity-playback-failure",
            lambda: services.integrity_playback_failure(file_instance_id=payload.file_instance_id),
        )

    @app.post("/api/integrity/review")
    def integrity_review_set_v2(
        payload: IntegrityReviewPayload,
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        return _execute_mutation(
            "integrity-review",
            lambda: services.integrity_review_set(
                check_id=payload.check_id,
                decision=payload.decision,
                reviewed_by=payload.reviewed_by,
            ),
        )

    @app.post("/api/integrity/quarantine")
    def integrity_quarantine_v2(
        payload: IntegrityQuarantinePayload,
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        return _execute_mutation(
            "integrity-quarantine",
            lambda: services.integrity_quarantine(check_id=payload.check_id),
        )

    @app.post("/api/integrity/restore")
    def integrity_restore_v2(
        payload: IntegrityRestorePayload,
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        return _execute_mutation(
            "integrity-restore",
            lambda: services.integrity_restore(file_instance_id=payload.file_instance_id),
        )

    @app.get("/api/media-file/by-hash")
    def media_file_by_hash_v2(
        hash_prefix: str | None = Query(default=None),
        page: int = 1,
        limit: int = 30,
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        normalized_hash = _require_non_empty(hash_prefix, "hash_prefix")
        parsed_page, parsed_limit = _parse_paging_args(page=page, limit=limit)
        return _execute_read(
            "media-file-by-hash",
            lambda: services.media_file_by_hash(hash_prefix=normalized_hash, page=parsed_page, limit=parsed_limit),
        )

    @app.get("/api/media-file/history")
    def media_file_history_v2(
        path: str | None = Query(default=None),
        page: int = 1,
        limit: int = 30,
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        normalized_path = _require_non_empty(path, "path")
        parsed_page, parsed_limit = _parse_paging_args(page=page, limit=limit)
        return _execute_read(
            "media-file-history",
            lambda: services.media_file_history(path=normalized_path, page=parsed_page, limit=parsed_limit),
        )

    @app.get("/api/media-file/by-status")
    def media_file_by_status_v2(
        status: str | None = Query(default=None),
        page: int = 1,
        limit: int = 30,
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        normalized_status = _require_non_empty(status, "status")
        parsed_page, parsed_limit = _parse_paging_args(page=page, limit=limit)
        return _execute_read(
            "media-file-by-status",
            lambda: services.media_file_by_status(status=normalized_status, page=parsed_page, limit=parsed_limit),
        )

    @app.get("/api/media-file/reappearances")
    def media_file_reappearances_v2(
        path: str | None = Query(default=None),
        page: int = 1,
        limit: int = 30,
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        normalized_path = _require_non_empty(path, "path")
        parsed_page, parsed_limit = _parse_paging_args(page=page, limit=limit)
        return _execute_read(
            "media-file-reappearances",
            lambda: services.media_file_reappearances(path=normalized_path, page=parsed_page, limit=parsed_limit),
        )

    @app.get("/api/media-file/analytics")
    def media_file_analytics_v2(
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        return _execute_read("media-file-analytics", services.media_file_analytics)

    @app.get("/api/admin/hash-audit")
    def media_file_hash_audit_v2(
        root_path: str | None = Query(default=None),
        sample_limit: int = Query(default=20),
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        normalized_root: str | None = None
        if root_path is not None:
            normalized_root = _require_non_empty(root_path, "root_path")
        parsed_limit = _parse_sample_limit(sample_limit)
        return _execute_read(
            "ledger-hash-audit",
            lambda: services.ledger_hash_audit(root_path=normalized_root, sample_limit=parsed_limit),
        )

    @app.get("/api/admin/observability/summary")
    def admin_observability_summary(
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        return _execute_read("admin-observability-summary", services.admin_observability_summary)

    @app.get("/api/admin/observability/operation-runs")
    def admin_observability_operation_runs(
        limit: int = Query(default=50),
        operation_type: str | None = Query(default=None),
        status: str | None = Query(default=None),
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        parsed_limit = max(1, min(200, int(limit)))
        return _execute_read(
            "admin-observability-operation-runs",
            lambda: services.operation_runs(limit=parsed_limit, operation_type=operation_type, status=status),
        )

    @app.get("/api/admin/observability/failures")
    def admin_observability_failures(
        limit: int = Query(default=25),
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        parsed_limit = max(1, min(100, int(limit)))
        return _execute_read(
            "admin-observability-failures",
            lambda: services.admin_observability_failures(limit=parsed_limit),
        )

    @app.get("/api/admin/observability/metrics-series")
    def admin_observability_metrics_series(
        hours: int = Query(default=24),
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        parsed_hours = max(1, min(168, int(hours)))
        return _execute_read(
            "admin-observability-metrics-series",
            lambda: services.admin_observability_metrics_series(hours=parsed_hours),
        )

    @app.get("/api/media-file/dry-run-audit")
    def media_file_dry_run_audit_v2(
        start: str | None = Query(default=None),
        end: str | None = Query(default=None),
        limit: int = 50,
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        if limit < 1 or limit > 200:
            raise HTTPException(status_code=400, detail="limit must be within [1, 200].")
        return _execute_read(
            "media-file-dry-run-audit",
            lambda: services.media_file_dry_run_audit(start=start, end=end, limit=limit),
        )

    @app.post("/api/media-file/validate")
    def post_media_file_validate_v2(
        payload: MediaFileValidatePayload,
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        return _execute_mutation(
            "media-file-validate",
            lambda: services.media_file_validate(folder_path=payload.folder_path),
        )

    @app.get("/media/{file_id}")
    def media(
        file_id: UUID,
        service: OperatorConsoleReadService = Depends(get_operator_console_service),
    ) -> FileResponse:
        """Stream a canonical media file by durable file instance identifier."""
        resolved = service.resolve_media_source(file_id)
        if resolved is None:
            raise HTTPException(status_code=404, detail="Media not found.")
        path, media_type = resolved
        return FileResponse(path=path, media_type=media_type)

    @app.get("/api/thumbnail/{file_instance_id}")
    def thumbnail(
        file_instance_id: UUID,
        service: OperatorConsoleReadService = Depends(get_operator_console_service),
    ) -> FileResponse:
        """Return source bytes for an active image instance thumbnail preview."""
        resolved = service.resolve_thumbnail_source(file_instance_id)
        if resolved is None:
            raise HTTPException(status_code=404, detail="Thumbnail not available.")
        path, media_type = resolved
        return FileResponse(path=path, media_type=media_type)

    @app.get("/api/video-thumbnail/{file_instance_id}")
    def video_thumbnail(
        file_instance_id: UUID,
        service: OperatorConsoleReadService = Depends(get_operator_console_service),
    ) -> FileResponse:
        """Return generated poster bytes for an active video instance when available."""
        resolved = service.resolve_video_thumbnail_source(file_instance_id)
        if resolved is None:
            raise HTTPException(status_code=404, detail="Video thumbnail not available.")
        path, media_type = resolved
        return FileResponse(path=path, media_type=media_type)

    @app.get("/api/policy")
    def get_policy_v2(
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        return _execute_read("policy-get", services.policy_get)

    @app.post("/api/policy")
    def post_policy_v2(
        payload: PolicyUpdatePayload,
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        return _execute_mutation(
            "policy-set",
            lambda: services.policy_set(
                selected_policy=payload.selected_policy,
                naming_strategy=payload.naming_strategy,
                preferred_roots=tuple(payload.preferred_roots),
                integrity_scan_default_mode=payload.integrity_scan_default_mode,
                integrity_issue_min_confidence=payload.integrity_issue_min_confidence,
                integrity_notify_on_high_confidence=payload.integrity_notify_on_high_confidence,
                duplicate_reclaim_archive_root=payload.duplicate_reclaim_archive_root,
                duplicate_reclaim_default_retention_days=payload.duplicate_reclaim_default_retention_days,
                duplicate_reclaim_notify_on_reviewed_safe=payload.duplicate_reclaim_notify_on_reviewed_safe,
                integrity_quarantine_root=payload.integrity_quarantine_root,
                integrity_quarantine_retention_days=payload.integrity_quarantine_retention_days,
                recycle_bin_root=payload.recycle_bin_root,
                recycle_purge_days=payload.recycle_purge_days,
                automation_mode=payload.automation_mode,
                recanonicalization_enabled=payload.recanonicalization_enabled,
                version=payload.version,
            ),
        )

    @app.post("/api/run")
    def post_run_v2(
        payload: RunTriggerPayload,
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        return _execute_mutation(
            "run",
            lambda: services.run(
                folder_path=payload.folder_path,
                policy_name=payload.policy_name,
                dry_run=payload.dry_run,
                owner=payload.owner,
                context=payload.context,
                naming_strategy=payload.naming_strategy,
                owner_context_override_confirmed=payload.owner_context_override_confirmed,
            ),
        )

    @app.post("/api/ingest")
    def post_ingest_v2(
        payload: IngestPayload,
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        return _execute_mutation(
            "ingest",
            lambda: services.ingest(folder_path=payload.folder_path, dry_run=payload.dry_run),
        )

    @app.post("/api/plan")
    def post_plan_v2(
        payload: PlanPayload,
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        return _execute_mutation(
            "plan",
            lambda: services.plan(
                folder_path=payload.folder_path,
                strict_metadata=payload.strict_metadata,
                owner=payload.owner,
                context=payload.context,
                naming_strategy=payload.naming_strategy,
                owner_context_override_confirmed=payload.owner_context_override_confirmed,
            ),
        )

    @app.post("/api/apply")
    def post_apply_v2(
        payload: ApplyPayload,
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        return _execute_mutation(
            "apply",
            lambda: services.apply(run_id=payload.run_id, collision_mode=payload.collision_mode),
        )

    @app.post("/api/canonical/recompute")
    def post_canonical_recompute_v2(
        payload: CanonicalRecomputePayload,
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        return _execute_mutation(
            "canonical-recompute",
            lambda: services.canonical_recompute(
                policy_name=payload.policy_name,
                dry_run=payload.dry_run,
                preferred_roots=tuple(payload.preferred_roots),
            ),
        )

    @app.get("/api/operations/catalog")
    def get_operations_catalog_v2(
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        return _execute_read("operations-catalog", services.operations_catalog)

    @app.post("/api/tag-enrichment")
    def post_tag_enrichment_v2(
        payload: TagEnrichmentPayload,
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        return _execute_mutation(
            "tag-enrichment",
            lambda: services.tag_enrichment(
                run_all=payload.run_all,
                canonical_id=payload.canonical_id,
                batch_size=int(payload.batch_size),
                source=payload.source,
            ),
        )

    @app.post("/api/admin/db-reset")
    def post_db_reset(
        payload: DbResetPayload,
        services: AdminServices = Depends(get_admin_services),
    ) -> JSONResponse:
        """
        Perform safe, idempotent data reset for dev/test environments.

        - `dry_run=true`: list affected tables only.
        - `dry_run=false`: requires exact challenge_word.
        - Always preserves alembic migration state (does not truncate alembic_version).
        """
        return _execute_mutation(
            "db-reset",
            lambda: services.db_reset(dry_run=bool(payload.dry_run), challenge_word=payload.challenge_word),
        )

    @app.post("/api/admin/benchmarks/metadata")
    def post_admin_metadata_benchmark(
        payload: MetadataBenchmarkPayload,
        services: AdminServices = Depends(get_admin_services),
    ) -> JSONResponse:
        return _execute_mutation(
            "benchmark-metadata-queue",
            lambda: services.benchmark_metadata_queue(
                items=payload.items,
                batch_size=payload.batch_size,
                challenge_word=payload.challenge_word,
            ),
        )

    @app.post("/api/admin/benchmarks/discovery")
    def post_admin_discovery_benchmark(
        payload: DiscoveryBenchmarkPayload,
        services: AdminServices = Depends(get_admin_services),
    ) -> JSONResponse:
        return _execute_mutation(
            "benchmark-discovery-queue",
            lambda: services.benchmark_discovery_queue(
                items=payload.items,
                challenge_word=payload.challenge_word,
            ),
        )

    @app.get("/api/admin/benchmarks/runs")
    def get_admin_benchmark_runs(
        limit: int = Query(default=50),
        services: AdminServices = Depends(get_admin_services),
    ) -> JSONResponse:
        parsed_limit = max(1, min(200, int(limit)))
        return _execute_read(
            "benchmark-runs",
            lambda: services.benchmark_runs(limit=parsed_limit),
        )

    @app.get("/api/admin/benchmarks/runs/{operation_run_id}")
    def get_admin_benchmark_run(
        operation_run_id: str,
        services: AdminServices = Depends(get_admin_services),
    ) -> JSONResponse:
        return _execute_read(
            "benchmark-run-detail",
            lambda: services.benchmark_run_detail(operation_run_id=operation_run_id),
        )

    @app.post("/api/admin/benchmarks/runs/{operation_run_id}/cancel")
    def post_admin_benchmark_run_cancel(
        operation_run_id: str,
        services: AdminServices = Depends(get_admin_services),
    ) -> JSONResponse:
        return _execute_mutation(
            "benchmark-run-cancel",
            lambda: services.benchmark_run_cancel(operation_run_id=operation_run_id),
        )

    return app


app = create_app()


def main() -> None:
    """Run the API server as the supported package entrypoint."""
    import uvicorn

    host = os.getenv("MEDIA_MANAGER_API_HOST", "127.0.0.1")
    port = int(os.getenv("MEDIA_MANAGER_API_PORT", "8000"))
    uvicorn.run(
        "operator_console.main:app",
        host=host,
        port=port,
        reload=_api_reload_enabled(),
    )
