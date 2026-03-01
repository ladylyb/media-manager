"""FastAPI entrypoint for the Media Manager Operator Console."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from media_manager.app.core.errors import (
    MediaManagerError,
    PolicySettingsValidationError,
    PolicySettingsVersionConflictError,
)
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
