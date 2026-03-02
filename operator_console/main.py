"""FastAPI entrypoint for the Media Manager Operator Console."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from media_manager.app.core.errors import (
    MediaManagerError,
    PolicySettingsValidationError,
    PolicySettingsVersionConflictError,
)
from media_manager.app.observability import mount_metrics_endpoint
from media_manager.app.persistence.base import create_db_engine, create_session_factory
from media_manager.app.persistence.operator_console import OperatorConsoleReadService
from media_manager.app.persistence.operator_run_trigger import (
    OperatorRunTriggerService,
    RunTriggerCommand,
)
from media_manager.app.persistence.policy_settings import PolicySettingsService, UpdatePolicySettingsCommand


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

    @app.get("/duplicates", response_class=HTMLResponse)
    def duplicates_page(request: Request) -> HTMLResponse:
        """Render the Operator Console duplicate group browser page."""
        return templates.TemplateResponse(request, "duplicates.html", {})

    @app.get("/gallery", response_class=HTMLResponse)
    def gallery_page(request: Request) -> HTMLResponse:
        """Render the Operator Console canonical gallery page."""
        return templates.TemplateResponse(request, "gallery.html", {})

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

    @app.get("/api/canonical")
    def canonical_gallery(
        page: int = 1,
        limit: int = 30,
        service: OperatorConsoleReadService = Depends(get_operator_console_service),
    ) -> dict[str, int | list[dict[str, str]]]:
        """Return paginated canonical media entries for the gallery UI."""
        return service.get_canonical_gallery(page=page, limit=limit).to_dict()

    @app.get("/api/duplicates")
    def duplicates(
        service: OperatorConsoleReadService = Depends(get_operator_console_service),
    ) -> dict[str, list[dict[str, object]]]:
        """Return duplicate groups and canonical-file mapping for browser UI."""
        return {"groups": [group.to_dict() for group in service.get_duplicate_groups()]}

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

    return app


app = create_app()
