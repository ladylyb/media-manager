"""Mutating/validation façade for Operator Console and CLI adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.operator_run_trigger import OperatorRunTriggerService, RunTriggerCommand
from media_manager.app.persistence.policy_settings import PolicySettingsService, UpdatePolicySettingsCommand
from media_manager.app.persistence.models import TagSource
from media_manager.app.persistence.tag_enrichment import EnrichmentScope, TagEnrichmentCommand, run_tag_enrichment
from media_manager.app.service_layer.cache import ServiceCache


@dataclass
class OperationServices:
    """Shared mutation/validation service entrypoint."""

    session_factory: object
    cache: ServiceCache

    def run(self, *, folder_path: str, policy_name: str, dry_run: bool) -> dict[str, object]:
        result = OperatorRunTriggerService(self.session_factory).trigger_run(
            RunTriggerCommand(folder_path=folder_path, policy_name=policy_name, dry_run=dry_run)
        ).to_dict()
        self.cache.invalidate("dashboard_summary", "latest_metrics", "status")
        return result

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
