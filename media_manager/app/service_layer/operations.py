"""Mutating/validation façade for Operator Console and CLI adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from media_manager.app.canonical.context import CanonicalContext
from media_manager.app.canonical.factory import build_canonical_policy
from media_manager.app.persistence.apply import ApplyService
from media_manager.app.persistence.canonicalization import RecomputeMode, recompute_canonical_assignments
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.operator_run_trigger import OperatorRunTriggerService, RunTriggerCommand
from media_manager.app.persistence.policy_settings import PolicySettingsService, UpdatePolicySettingsCommand
from media_manager.app.persistence.models import TagSource
from media_manager.app.persistence.runs import RunService
from media_manager.app.persistence.tag_enrichment import EnrichmentScope, TagEnrichmentCommand, run_tag_enrichment
from media_manager.app.service_layer.cache import ServiceCache


@dataclass
class OperationServices:
    """Shared mutation/validation service entrypoint."""

    session_factory: object
    cache: ServiceCache

    def ingest(self, *, folder_path: str, dry_run: bool) -> dict[str, object]:
        folder = Path(folder_path)
        if not folder.exists():
            raise ValueError(f"Folder path does not exist: {folder}")
        if not folder.is_dir():
            raise ValueError(f"Folder path must be a directory: {folder}")
        service = IngestService(self.session_factory)
        if dry_run:
            return {
                "mode": "VALIDATION_ONLY",
                "operation": "INGEST",
                "report": service.validate_path(folder).to_dict(),
            }
        result = {
            "mode": "EXECUTION",
            "operation": "INGEST",
            "summary": service.ingest_path(folder).to_dict(),
        }
        self.cache.invalidate("dashboard_summary", "latest_metrics", "status")
        return result

    def plan(self, *, folder_path: str, strict_metadata: bool) -> dict[str, object]:
        folder = Path(folder_path)
        if not folder.exists():
            raise ValueError(f"Folder path does not exist: {folder}")
        if not folder.is_dir():
            raise ValueError(f"Folder path must be a directory: {folder}")
        ingest = IngestService(self.session_factory)
        run_service = RunService(self.session_factory)
        planner = PlanningService(self.session_factory)
        files = ingest.collect_files(folder)
        ingest.ingest_paths(files, authoritative_root=folder)
        run = run_service.create_run()
        summary = planner.plan_run(run.id, files, ingest_if_needed=False, strict_missing_metadata=strict_metadata)
        self.cache.invalidate("runs", "latest_metrics", "status", "dashboard_summary")
        return {
            "operation": "PLAN",
            "run_id": str(run.id),
            "strict_metadata": strict_metadata,
            "summary": summary.to_dict(),
        }

    def apply(self, *, run_id: str, collision_mode: str) -> dict[str, object]:
        try:
            parsed_run_id = UUID(run_id)
        except ValueError as exc:
            raise ValueError(f"run_id must be a valid UUID: {run_id}") from exc
        if collision_mode not in {"rename", "skip", "fail"}:
            raise ValueError("collision_mode must be one of: rename, skip, fail.")
        summary = ApplyService(self.session_factory).apply_run(parsed_run_id, collision_mode=collision_mode)  # type: ignore[arg-type]
        self.cache.invalidate("dashboard_summary", "latest_metrics", "runs", "status")
        return {
            "operation": "APPLY",
            "run_id": str(parsed_run_id),
            "collision_mode": collision_mode,
            "summary": summary.to_dict(),
        }

    def canonical_recompute(
        self,
        *,
        policy_name: str,
        dry_run: bool,
        preferred_roots: tuple[str, ...],
    ) -> dict[str, object]:
        policy = build_canonical_policy(policy_name)
        context = CanonicalContext(preferred_roots=tuple(Path(root) for root in preferred_roots))
        mode = RecomputeMode.DRY_RUN if dry_run else RecomputeMode.APPLY
        summary = recompute_canonical_assignments(
            self.session_factory,
            policy=policy,
            context=context,
            mode=mode,
        )
        if not dry_run:
            self.cache.invalidate("latest_metrics", "status")
        return {
            "operation": "CANONICAL_RECOMPUTE",
            "mode": mode.value,
            "policy_name": policy.name,
            "policy_version": policy.version,
            "summary": {
                "run_id": str(summary.run_id),
                "status": summary.status,
                "scanned_count": summary.scanned_count,
                "changed_count": summary.changed_count,
                "applied_count": summary.applied_count,
                "failed_count": summary.failed_count,
                "changed_content_ids": list(summary.changed_content_ids),
                "failed_content_ids": list(summary.failed_content_ids),
            },
        }

    def operator_run(self, *, folder_path: str, policy_name: str, dry_run: bool) -> dict[str, object]:
        return self.run(folder_path=folder_path, policy_name=policy_name, dry_run=dry_run)

    def run(self, *, folder_path: str, policy_name: str, dry_run: bool) -> dict[str, object]:
        result = OperatorRunTriggerService(self.session_factory).trigger_run(
            RunTriggerCommand(folder_path=folder_path, policy_name=policy_name, dry_run=dry_run)
        ).to_dict()
        self.cache.invalidate("dashboard_summary", "latest_metrics", "status")
        return result

    def operations_catalog(self) -> dict[str, object]:
        return {
            "items": [
                {
                    "operation_id": "ingest",
                    "label": "Ingest",
                    "mutates_state": True,
                    "supports_dry_run": True,
                    "defaults": {"dry_run": True},
                    "required_fields": ["folder_path"],
                },
                {
                    "operation_id": "plan",
                    "label": "Plan",
                    "mutates_state": True,
                    "supports_dry_run": False,
                    "defaults": {"strict_metadata": False},
                    "required_fields": ["folder_path"],
                },
                {
                    "operation_id": "apply",
                    "label": "Apply",
                    "mutates_state": True,
                    "supports_dry_run": False,
                    "defaults": {"collision_mode": "rename"},
                    "required_fields": ["run_id"],
                },
                {
                    "operation_id": "canonical_recompute",
                    "label": "Canonical Recompute",
                    "mutates_state": True,
                    "supports_dry_run": True,
                    "defaults": {"dry_run": True, "preferred_roots": []},
                    "required_fields": ["policy_name"],
                },
                {
                    "operation_id": "tag_enrichment",
                    "label": "Tag Enrichment",
                    "mutates_state": True,
                    "supports_dry_run": False,
                    "defaults": {"all": True, "batch_size": 100, "source": TagSource.SYSTEM.value},
                    "required_fields": [],
                },
                {
                    "operation_id": "operator_run",
                    "label": "Composite Run (Legacy)",
                    "mutates_state": True,
                    "supports_dry_run": True,
                    "defaults": {"dry_run": True},
                    "required_fields": ["folder_path", "policy_name"],
                },
            ]
        }

    def policy_get(self) -> dict[str, object]:
        return PolicySettingsService(self.session_factory).get_settings().to_dict()

    def policy_set(
        self,
        *,
        selected_policy: str,
        preferred_roots: tuple[str, ...],
        recanonicalization_enabled: bool,
        version: int,
    ) -> dict[str, object]:
        result = PolicySettingsService(self.session_factory).update_settings(
            UpdatePolicySettingsCommand(
                selected_policy=selected_policy,
                preferred_roots=preferred_roots,
                recanonicalization_enabled=recanonicalization_enabled,
                version=version,
            )
        ).to_dict()
        self.cache.invalidate("status", "policy_snapshot")
        return result

    def tag_enrichment(self, *, run_all: bool, canonical_id: str | None, batch_size: int, source: str) -> dict[str, object]:
        canonical_uuid: UUID | None = None
        if canonical_id is not None:
            canonical_uuid = UUID(canonical_id)
        summary = run_tag_enrichment(
            self.session_factory,
            TagEnrichmentCommand(
                scope=EnrichmentScope.ALL if run_all else EnrichmentScope.SINGLE,
                canonical_id=canonical_uuid,
                batch_size=batch_size,
                source=TagSource(source),
            ),
        )
        self.cache.invalidate("latest_metrics", "status")
        return summary.to_dict()

    def media_file_validate(self, *, folder_path: str) -> dict[str, object]:
        folder = Path(folder_path)
        if not folder.exists():
            raise ValueError(f"Folder path does not exist: {folder}")
        if not folder.is_dir():
            raise ValueError(f"Folder path must be a directory: {folder}")
        return IngestService(self.session_factory).validate_path(folder).to_dict()
