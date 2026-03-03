"""FastAPI entrypoint for the Media Manager Operator Console."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import logging
from pathlib import Path
import threading
import time
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from media_manager.app.core.errors import (
    MediaManagerError,
    PolicySettingsValidationError,
    PolicySettingsVersionConflictError,
)
from media_manager.app.observability import mount_metrics_endpoint
from media_manager.app.persistence.base import create_db_engine, create_session_factory
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.operator_console import OperatorConsoleReadService
from media_manager.app.persistence.operator_run_trigger import (
    OperatorRunTriggerService,
    RunTriggerCommand,
)
from media_manager.app.persistence.policy_settings import PolicySettingsService, UpdatePolicySettingsCommand
from media_manager.app.persistence.models import MediaFileStatus, TagSource
from media_manager.app.persistence.tag_enrichment import (
    EnrichmentScope,
    TagEnrichmentCommand,
    run_tag_enrichment,
)
from media_manager.app.service_layer import (
    AdminServices,
    OperationServices,
    ReadServices,
    ServiceCache,
    ServiceEnvelope,
    ServiceError,
    iso_now,
    map_exception,
    schema_version,
)

LOGGER = logging.getLogger(__name__)
_MUTATION_SEMAPHORE = threading.BoundedSemaphore(value=4)


@lru_cache(maxsize=1)
def get_operator_console_service() -> OperatorConsoleReadService:
    """Build and cache the read-only Operator Console service."""
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    return OperatorConsoleReadService(session_factory)


@lru_cache(maxsize=1)
def get_policy_settings_service() -> PolicySettingsService:
    """Build and cache the policy settings persistence service."""
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    return PolicySettingsService(session_factory)


@lru_cache(maxsize=1)
def get_operator_run_trigger_service() -> OperatorRunTriggerService:
    """Build and cache the operator run trigger service."""
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    return OperatorRunTriggerService(session_factory)


@lru_cache(maxsize=1)
def get_tag_enrichment_session_factory():
    """Build and cache session factory for manual tag enrichment trigger API."""
    engine = create_db_engine()
    return create_session_factory(engine)


@lru_cache(maxsize=1)
def get_ingest_service() -> IngestService:
    """Build and cache ingest service for validation-only API mode."""
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    return IngestService(session_factory)


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
    preferred_roots: list[str] = Field(default_factory=list)
    recanonicalization_enabled: bool
    version: int


class RunTriggerPayload(BaseModel):
    """Structured payload for operator-initiated run execution."""

    folder_path: str
    policy_name: str
    dry_run: bool = False


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


def _parse_sample_limit(value: int) -> int:
    parsed = int(value)
    if parsed < 1 or parsed > 200:
        raise HTTPException(status_code=400, detail="sample_limit must be within [1, 200].")
    return parsed


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
        LOGGER.exception(
            "v2 mutation failed",
            extra={"operation": name, "error_code": mapped.code, "phase": "operator_console", "action": "V2_MUTATION"},
        )
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
    templates_dir = package_root / "templates"
    static_dir = package_root / "static"

    app = FastAPI(title="Media Manager Operator Console")
    templates = Jinja2Templates(directory=str(templates_dir))
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    mount_metrics_endpoint(app)

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request) -> HTMLResponse:
        """Render the Operator Console dashboard page."""
        return templates.TemplateResponse(request, "dashboard.html", {})

    @app.get("/runs", response_class=HTMLResponse)
    def runs_page(request: Request) -> HTMLResponse:
        """Render the Operator Console run history page."""
        return templates.TemplateResponse(request, "runs.html", {})

    @app.get("/policy", response_class=HTMLResponse)
    def policy_page(request: Request) -> HTMLResponse:
        """Render the Operator Console policy management page."""
        return templates.TemplateResponse(request, "policy.html", {})

    @app.get("/admin", response_class=HTMLResponse)
    def admin_page(request: Request) -> HTMLResponse:
        """Render Operator Console admin page."""
        return templates.TemplateResponse(request, "admin.html", {})

    @app.get("/duplicates", response_class=HTMLResponse)
    def duplicates_page(request: Request) -> HTMLResponse:
        """Render the Operator Console duplicate group browser page."""
        return templates.TemplateResponse(request, "duplicates.html", {})

    @app.get("/gallery", response_class=HTMLResponse)
    def gallery_page(request: Request) -> HTMLResponse:
        """Render the Operator Console canonical gallery page."""
        return templates.TemplateResponse(request, "gallery.html", {})

    @app.get("/ledger", response_class=HTMLResponse)
    def ledger_page(request: Request) -> HTMLResponse:
        """Render read-only media_file ledger explorer page."""
        return templates.TemplateResponse(request, "ledger.html", {})

    @app.get("/discover", response_class=HTMLResponse)
    def discover_page(
        request: Request,
        page: int = 1,
        limit: int = 30,
        tags: str | None = Query(default=None),
        sort_by: str = Query(default="created_at"),
        sort_order: str | None = Query(default=None),
        service: OperatorConsoleReadService = Depends(get_operator_console_service),
    ) -> HTMLResponse:
        """Render read-only discovery explorer with initial SSR payload."""
        parsed = _parse_discovery_query_args(
            page=page,
            limit=limit,
            tags=tags,
            sort_by=sort_by,
            sort_order=sort_order,
            source=None,
            min_confidence=None,
        )
        payload = service.get_canonical_gallery(
            page=parsed.page,
            limit=parsed.limit,
            tags=parsed.tags,
            sort_by=parsed.sort_by,
            sort_order=parsed.sort_order,
        ).to_dict()
        return templates.TemplateResponse(
            request,
            "discover.html",
            {
                "initial_payload": payload,
                "initial_tags_csv": ",".join(parsed.tags),
                "initial_sort_by": parsed.sort_by,
                "initial_sort_order": parsed.sort_order,
            },
        )

    @app.get("/gallery/{file_id}", response_class=HTMLResponse)
    def gallery_detail_page(
        file_id: UUID,
        request: Request,
        page: int = 1,
        service: OperatorConsoleReadService = Depends(get_operator_console_service),
    ) -> HTMLResponse:
        """Render full-page canonical media detail with a gallery back link."""
        detail = service.get_canonical_gallery_detail(file_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Canonical media not found.")
        return templates.TemplateResponse(
            request,
            "gallery_detail.html",
            {
                "item": detail.to_dict(),
                "return_page": max(1, int(page)),
            },
        )

    @app.get("/api/dashboard-summary")
    def dashboard_summary(
        service: OperatorConsoleReadService = Depends(get_operator_console_service),
    ) -> dict[str, int]:
        """Return aggregate library counters for the dashboard."""
        return service.get_dashboard_summary().to_dict()

    @app.get("/api/latest-metrics")
    def latest_metrics(
        service: OperatorConsoleReadService = Depends(get_operator_console_service),
    ) -> dict[str, float | str | None]:
        """Return the latest persisted ingestion/planning/apply performance metrics."""
        return service.get_latest_metrics().to_dict()

    @app.get("/api/runs")
    def runs_history(
        service: OperatorConsoleReadService = Depends(get_operator_console_service),
    ) -> list[dict[str, str | int | float | None]]:
        """Return recent run history rows for the Operator Console."""
        return [item.to_dict() for item in service.get_run_history(limit=50)]

    @app.get("/api/v2/status")
    def status_v2(
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        """Return v2 status metadata envelope."""
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

    @app.get("/api/v2/dashboard-summary")
    def dashboard_summary_v2(
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        return _execute_read("dashboard-summary", services.dashboard_summary)

    @app.get("/api/v2/latest-metrics")
    def latest_metrics_v2(
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        return _execute_read("latest-metrics", services.latest_metrics)

    @app.get("/api/v2/runs")
    def runs_history_v2(
        limit: int = Query(default=50),
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        parsed_limit = max(1, min(200, int(limit)))
        return _execute_read("runs", lambda: services.runs(limit=parsed_limit))

    @app.get("/api/v2/canonical")
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

    @app.get("/api/v2/canonical/tags")
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

    @app.get("/api/v2/duplicates")
    def duplicates_v2(
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        return _execute_read("duplicates", services.duplicates)

    @app.get("/api/v2/media-file/by-hash")
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

    @app.get("/api/v2/media-file/history")
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

    @app.get("/api/v2/media-file/by-status")
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

    @app.get("/api/v2/media-file/reappearances")
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

    @app.get("/api/v2/media-file/analytics")
    def media_file_analytics_v2(
        services: ReadServices = Depends(get_read_services),
    ) -> JSONResponse:
        return _execute_read("media-file-analytics", services.media_file_analytics)

    @app.get("/api/v2/ledger/hash-audit")
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

    @app.get("/api/v2/media-file/dry-run-audit")
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

    @app.get("/api/canonical")
    def canonical_gallery(
        page: int = 1,
        limit: int = 30,
        tags: str | None = Query(default=None),
        sort_by: str = Query(default="created_at"),
        sort_order: str | None = Query(default=None),
        source: str | None = Query(default=None),
        min_confidence: float | None = Query(default=None),
        service: OperatorConsoleReadService = Depends(get_operator_console_service),
    ) -> dict[str, object]:
        """Return paginated canonical media entries for the gallery UI."""
        parsed = _parse_discovery_query_args(
            page=page,
            limit=limit,
            tags=tags,
            sort_by=sort_by,
            sort_order=sort_order,
            source=source,
            min_confidence=min_confidence,
        )

        try:
            return service.get_canonical_gallery(
                page=parsed.page,
                limit=parsed.limit,
                tags=parsed.tags,
                sort_by=parsed.sort_by,
                sort_order=parsed.sort_order,
                source=parsed.source,
                min_confidence=parsed.min_confidence,
            ).to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/canonical/tags")
    def canonical_tag_suggestions(
        q: str | None = Query(default=None),
        limit: int = Query(default=10),
        service: OperatorConsoleReadService = Depends(get_operator_console_service),
    ) -> dict[str, list[str]]:
        """Return deterministic normalized tag suggestions for discover autocomplete."""
        return {"items": list(service.get_tag_suggestions(q=q, limit=limit))}

    @app.get("/api/duplicates")
    def duplicates(
        service: OperatorConsoleReadService = Depends(get_operator_console_service),
    ) -> dict[str, list[dict[str, object]]]:
        """Return duplicate groups and canonical-file mapping for browser UI."""
        return {"groups": [group.to_dict() for group in service.get_duplicate_groups()]}

    @app.get("/api/media-file/by-hash")
    def media_file_by_hash(
        hash_prefix: str | None = Query(default=None),
        page: int = 1,
        limit: int = 30,
        service: OperatorConsoleReadService = Depends(get_operator_console_service),
    ) -> dict[str, object]:
        normalized_hash = _require_non_empty(hash_prefix, "hash_prefix")
        parsed_page, parsed_limit = _parse_paging_args(page=page, limit=limit)
        return service.get_media_file_by_hash_page(
            hash_prefix=normalized_hash,
            page=parsed_page,
            limit=parsed_limit,
        ).to_dict()

    @app.get("/api/media-file/history")
    def media_file_history(
        path: str | None = Query(default=None),
        page: int = 1,
        limit: int = 30,
        service: OperatorConsoleReadService = Depends(get_operator_console_service),
    ) -> dict[str, object]:
        normalized_path = _require_non_empty(path, "path")
        parsed_page, parsed_limit = _parse_paging_args(page=page, limit=limit)
        return service.get_media_file_history_page(
            path=normalized_path,
            page=parsed_page,
            limit=parsed_limit,
        ).to_dict()

    @app.get("/api/media-file/by-status")
    def media_file_by_status(
        status: str | None = Query(default=None),
        page: int = 1,
        limit: int = 30,
        service: OperatorConsoleReadService = Depends(get_operator_console_service),
    ) -> dict[str, object]:
        normalized_status = _require_non_empty(status, "status")
        parsed_page, parsed_limit = _parse_paging_args(page=page, limit=limit)
        try:
            status_value = MediaFileStatus(normalized_status.upper())
        except Exception as exc:
            raise HTTPException(status_code=400, detail="status must be one of: INGESTED, PROCESSED, DELETED.") from exc
        return service.get_media_file_by_status_page(
            status=status_value,
            page=parsed_page,
            limit=parsed_limit,
        ).to_dict()

    @app.get("/api/media-file/reappearances")
    def media_file_reappearances(
        path: str | None = Query(default=None),
        page: int = 1,
        limit: int = 30,
        service: OperatorConsoleReadService = Depends(get_operator_console_service),
    ) -> dict[str, object]:
        normalized_path = _require_non_empty(path, "path")
        parsed_page, parsed_limit = _parse_paging_args(page=page, limit=limit)
        return service.get_media_file_reappearances_page(
            path=normalized_path,
            page=parsed_page,
            limit=parsed_limit,
        ).to_dict()

    @app.get("/api/media-file/analytics")
    def media_file_analytics(
        service: OperatorConsoleReadService = Depends(get_operator_console_service),
    ) -> dict[str, object]:
        """Return all-time Phase 13 ledger analytics for dashboard/reporting views."""
        return service.get_media_file_analytics().to_dict()

    @app.get("/api/v1/ledger/hash-audit")
    @app.get("/api/media-file/hash-audit")
    def media_file_hash_audit(
        root_path: str | None = Query(default=None),
        sample_limit: int = Query(default=20),
        service: OperatorConsoleReadService = Depends(get_operator_console_service),
    ) -> dict[str, object]:
        """Return read-only ledger hash audit metrics and sample paths."""
        normalized_root: str | None = None
        if root_path is not None:
            normalized_root = _require_non_empty(root_path, "root_path")
        parsed_limit = _parse_sample_limit(sample_limit)
        try:
            return service.get_ledger_hash_audit(root_path=normalized_root, sample_limit=parsed_limit).to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/media-file/dry-run-audit")
    def media_file_dry_run_audit(
        start: str | None = Query(default=None),
        end: str | None = Query(default=None),
        limit: int = 50,
        service: OperatorConsoleReadService = Depends(get_operator_console_service),
    ) -> dict[str, object]:
        """Return best-effort historical dry-run side-effect candidates."""
        if limit < 1 or limit > 200:
            raise HTTPException(status_code=400, detail="limit must be within [1, 200].")
        try:
            return service.get_dry_run_side_effect_audit(start=start, end=end, limit=limit).to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/media-file/validate")
    def post_media_file_validate(
        payload: MediaFileValidatePayload,
        ingest_service: IngestService = Depends(get_ingest_service),
    ) -> dict[str, object]:
        """Run read-only ingest validation and return would-change delta report."""
        folder = Path(payload.folder_path)
        if not folder.exists():
            raise HTTPException(status_code=400, detail=f"Folder path does not exist: {folder}")
        if not folder.is_dir():
            raise HTTPException(status_code=400, detail=f"Folder path must be a directory: {folder}")
        return ingest_service.validate_path(folder).to_dict()

    @app.post("/api/v2/media-file/validate")
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

    @app.get("/api/policy")
    def get_policy(
        service: PolicySettingsService = Depends(get_policy_settings_service),
    ) -> dict[str, object]:
        """Return structured operator policy configuration."""
        return service.get_settings().to_dict()

    @app.get("/api/v2/policy")
    def get_policy_v2(
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        return _execute_read("policy-get", services.policy_get)

    @app.post("/api/policy")
    def post_policy(
        payload: PolicyUpdatePayload,
        service: PolicySettingsService = Depends(get_policy_settings_service),
    ) -> dict[str, object]:
        """Persist deterministic operator policy settings."""
        try:
            command = UpdatePolicySettingsCommand(
                selected_policy=payload.selected_policy,
                preferred_roots=tuple(payload.preferred_roots),
                recanonicalization_enabled=payload.recanonicalization_enabled,
                version=payload.version,
            )
            snapshot = service.update_settings(command)
        except PolicySettingsVersionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except PolicySettingsValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        response = snapshot.to_dict()
        response["message"] = "Policy settings saved."
        return response

    @app.post("/api/v2/policy")
    def post_policy_v2(
        payload: PolicyUpdatePayload,
        services: OperationServices = Depends(get_operation_services),
    ) -> JSONResponse:
        return _execute_mutation(
            "policy-set",
            lambda: services.policy_set(
                selected_policy=payload.selected_policy,
                preferred_roots=tuple(payload.preferred_roots),
                recanonicalization_enabled=payload.recanonicalization_enabled,
                version=payload.version,
            ),
        )

    @app.post("/api/run")
    def post_run(
        payload: RunTriggerPayload,
        service: OperatorRunTriggerService = Depends(get_operator_run_trigger_service),
    ) -> dict[str, object]:
        """Trigger an ingest/plan/apply workflow from Operator Console."""
        try:
            command = RunTriggerCommand(
                folder_path=payload.folder_path,
                policy_name=payload.policy_name,
                dry_run=payload.dry_run,
            )
            result = service.trigger_run(command)
            return result.to_dict()
        except (ValueError, MediaManagerError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/api/v2/run")
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
            ),
        )

    @app.post("/api/tag-enrichment")
    def post_tag_enrichment(
        payload: TagEnrichmentPayload,
        session_factory=Depends(get_tag_enrichment_session_factory),
    ) -> dict[str, object]:
        """Trigger deterministic tag enrichment for canonical content ids."""
        if payload.run_all == (payload.canonical_id is not None):
            raise HTTPException(status_code=400, detail="Specify exactly one of all=true or canonical_id.")
        if payload.batch_size <= 0:
            raise HTTPException(status_code=400, detail="batch_size must be > 0.")
        try:
            source = TagSource(payload.source)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid source: {payload.source}") from exc
        canonical_uuid: UUID | None = None
        if payload.canonical_id is not None:
            try:
                canonical_uuid = UUID(payload.canonical_id)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="canonical_id must be a valid UUID.") from exc
        command = TagEnrichmentCommand(
            scope=EnrichmentScope.ALL if payload.run_all else EnrichmentScope.SINGLE,
            canonical_id=canonical_uuid,
            batch_size=int(payload.batch_size),
            source=source,
        )
        try:
            summary = run_tag_enrichment(session_factory, command)
            return summary.to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/api/v2/tag-enrichment")
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

    @app.post("/api/v2/admin/db-reset")
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

    return app


app = create_app()
