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
from media_manager.app.persistence.operation_runs import OperationRunService
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.operator_run_trigger import OperatorRunTriggerService, RunTriggerCommand
from media_manager.app.persistence.policy_settings import PolicySettingsService, UpdatePolicySettingsCommand
from media_manager.app.persistence.models import OperationRunStatus, OperationRunType, TagSource
from media_manager.app.persistence.runs import RunService
from media_manager.app.persistence.tag_enrichment import EnrichmentScope, TagEnrichmentCommand, run_tag_enrichment
from media_manager.app.service_layer.cache import ServiceCache


@dataclass
class OperationServices:
    """Shared mutation/validation service entrypoint."""

    session_factory: object
    cache: ServiceCache

    def _op_runs(self) -> OperationRunService:
        return OperationRunService(self.session_factory)

    def ingest(self, *, folder_path: str, dry_run: bool) -> dict[str, object]:
        folder = Path(folder_path)
        if not folder.exists():
            raise ValueError(f"Folder path does not exist: {folder}")
        if not folder.is_dir():
            raise ValueError(f"Folder path must be a directory: {folder}")
        run_log = self._op_runs().start(
            operation_type=OperationRunType.INGEST,
            context={"folder_path": str(folder), "dry_run": bool(dry_run)},
        )
        service = IngestService(self.session_factory)
        try:
            if dry_run:
                result = {
                    "mode": "VALIDATION_ONLY",
                    "operation": "INGEST",
                    "operation_run_id": run_log.operation_run_id,
                    "report": service.validate_path(folder).to_dict(),
                }
                self._op_runs().complete(UUID(run_log.operation_run_id))
                return result
            result = {
                "mode": "EXECUTION",
                "operation": "INGEST",
                "operation_run_id": run_log.operation_run_id,
                "summary": service.ingest_path(folder).to_dict(),
            }
            self._op_runs().complete(UUID(run_log.operation_run_id))
            self.cache.invalidate("dashboard_summary", "latest_metrics", "status", "runs")
            return result
        except Exception as exc:
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=str(exc))
            raise

    def plan(self, *, folder_path: str, strict_metadata: bool) -> dict[str, object]:
        folder = Path(folder_path)
        if not folder.exists():
            raise ValueError(f"Folder path does not exist: {folder}")
        if not folder.is_dir():
            raise ValueError(f"Folder path must be a directory: {folder}")
        run_log = self._op_runs().start(
            operation_type=OperationRunType.PLAN,
            context={"folder_path": str(folder), "strict_metadata": bool(strict_metadata)},
        )
        ingest = IngestService(self.session_factory)
        run_service = RunService(self.session_factory)
        planner = PlanningService(self.session_factory)
        try:
            files = ingest.collect_files(folder)
            ingest.ingest_paths(files, authoritative_root=folder)
            run = run_service.create_run()
            self._op_runs().link_run(UUID(run_log.operation_run_id), linked_run_id=run.id)
            summary = planner.plan_run(run.id, files, ingest_if_needed=False, strict_missing_metadata=strict_metadata)
            self._op_runs().complete(UUID(run_log.operation_run_id))
            self.cache.invalidate("runs", "latest_metrics", "status", "dashboard_summary")
            return {
                "operation": "PLAN",
                "operation_run_id": run_log.operation_run_id,
                "run_id": str(run.id),
                "strict_metadata": strict_metadata,
                "summary": summary.to_dict(),
            }
        except Exception as exc:
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=str(exc))
            raise

    def apply(self, *, run_id: str, collision_mode: str) -> dict[str, object]:
        try:
            parsed_run_id = UUID(run_id)
        except ValueError as exc:
            raise ValueError(f"run_id must be a valid UUID: {run_id}") from exc
        if collision_mode not in {"rename", "skip", "fail"}:
            raise ValueError("collision_mode must be one of: rename, skip, fail.")
        run_log = self._op_runs().start(
            operation_type=OperationRunType.APPLY,
            context={"run_id": str(parsed_run_id), "collision_mode": collision_mode},
            linked_run_id=parsed_run_id,
        )
        try:
            summary = ApplyService(self.session_factory).apply_run(parsed_run_id, collision_mode=collision_mode)  # type: ignore[arg-type]
            self._op_runs().complete(UUID(run_log.operation_run_id))
            self.cache.invalidate("dashboard_summary", "latest_metrics", "runs", "status")
            return {
                "operation": "APPLY",
                "operation_run_id": run_log.operation_run_id,
                "run_id": str(parsed_run_id),
                "collision_mode": collision_mode,
                "summary": summary.to_dict(),
            }
        except Exception as exc:
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=str(exc))
            raise

    def canonical_recompute(
        self,
        *,
        policy_name: str,
        dry_run: bool,
        preferred_roots: tuple[str, ...],
    ) -> dict[str, object]:
        run_log = self._op_runs().start(
            operation_type=OperationRunType.CANONICAL_RECOMPUTE,
            context={
                "policy_name": policy_name,
                "dry_run": bool(dry_run),
                "preferred_roots": list(preferred_roots),
            },
        )
        policy = build_canonical_policy(policy_name)
        context = CanonicalContext(preferred_roots=tuple(Path(root) for root in preferred_roots))
        mode = RecomputeMode.DRY_RUN if dry_run else RecomputeMode.APPLY
        try:
            summary = recompute_canonical_assignments(
                self.session_factory,
                policy=policy,
                context=context,
                mode=mode,
            )
            self._op_runs().complete(UUID(run_log.operation_run_id))
            if not dry_run:
                self.cache.invalidate("latest_metrics", "status", "runs")
            return {
                "operation": "CANONICAL_RECOMPUTE",
                "operation_run_id": run_log.operation_run_id,
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
        except Exception as exc:
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=str(exc))
            raise

    def operator_run(self, *, folder_path: str, policy_name: str, dry_run: bool) -> dict[str, object]:
        return self.run(folder_path=folder_path, policy_name=policy_name, dry_run=dry_run)

    def run(self, *, folder_path: str, policy_name: str, dry_run: bool) -> dict[str, object]:
        run_log = self._op_runs().start(
            operation_type=OperationRunType.OPERATOR_RUN,
            context={"folder_path": folder_path, "policy_name": policy_name, "dry_run": bool(dry_run)},
        )
        try:
            result = OperatorRunTriggerService(self.session_factory).trigger_run(
                RunTriggerCommand(folder_path=folder_path, policy_name=policy_name, dry_run=dry_run)
            ).to_dict()
            linked_run_id = result.get("run_id")
            if isinstance(linked_run_id, str):
                try:
                    self._op_runs().link_run(UUID(run_log.operation_run_id), linked_run_id=UUID(linked_run_id))
                except Exception:
                    pass
            self._op_runs().complete(UUID(run_log.operation_run_id))
            self.cache.invalidate("dashboard_summary", "latest_metrics", "status", "runs")
            return {**result, "operation_run_id": run_log.operation_run_id}
        except Exception as exc:
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=str(exc))
            raise

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
        run_log = self._op_runs().start(
            operation_type=OperationRunType.TAG_ENRICHMENT,
            context={
                "run_all": bool(run_all),
                "canonical_id": canonical_id,
                "batch_size": int(batch_size),
                "source": source,
            },
        )
        try:
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
            self._op_runs().complete(UUID(run_log.operation_run_id))
            self.cache.invalidate("latest_metrics", "status", "runs")
            return {**summary.to_dict(), "operation_run_id": run_log.operation_run_id}
        except Exception as exc:
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=str(exc))
            raise

    def operation_runs(
        self,
        *,
        limit: int,
        operation_type: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, object]]:
        type_filter = OperationRunType(operation_type.strip().upper()) if operation_type else None
        status_filter = OperationRunStatus(status.strip().upper()) if status else None
        return [
            row.to_dict()
            for row in self._op_runs().list_history(limit=limit, operation_type=type_filter, status=status_filter)
        ]

    def media_file_validate(self, *, folder_path: str) -> dict[str, object]:
        folder = Path(folder_path)
        if not folder.exists():
            raise ValueError(f"Folder path does not exist: {folder}")
        if not folder.is_dir():
            raise ValueError(f"Folder path must be a directory: {folder}")
        return IngestService(self.session_factory).validate_path(folder).to_dict()
