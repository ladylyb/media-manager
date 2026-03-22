"""Operator Console run-trigger orchestration using existing deterministic services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from media_manager.app.canonical.context import CanonicalContext
from media_manager.app.canonical.factory import build_canonical_policy
from media_manager.app.core.naming import DEFAULT_CONTEXT, DEFAULT_OWNER
from media_manager.app.core.errors import MediaManagerError
from media_manager.app.persistence.apply import ApplyService, ApplySummary
from media_manager.app.persistence.canonicalization import RecomputeMode, recompute_canonical_assignments
from media_manager.app.persistence.ingest import IngestService, IngestSummary, IngestValidationReport
from media_manager.app.persistence.planner import PlanningService, PlanningSummary
from media_manager.app.persistence.runs import RunService


@dataclass(frozen=True)
class RunTriggerCommand:
    """Input command for operator-triggered run execution."""

    folder_path: str
    policy_name: str
    dry_run: bool
    owner: str = DEFAULT_OWNER
    context: str = DEFAULT_CONTEXT
    naming_strategy: str = "SHARED_CANONICAL_NAME"
    owner_context_override_confirmed: bool = False


@dataclass(frozen=True)
class RunTriggerResult:
    """Structured API result for a triggered run."""

    run_id: str
    summary_metrics: dict[str, object]
    duplicates_found: int
    canonical_changes: int

    def to_dict(self) -> dict[str, object]:
        """Return JSON-serializable result payload."""
        return {
            "mode": "EXECUTION",
            "run_id": self.run_id,
            "summary_metrics": self.summary_metrics,
            "duplicates_found": self.duplicates_found,
            "canonical_changes": self.canonical_changes,
        }


@dataclass(frozen=True)
class RunValidationResult:
    """Structured API result for dry-run validation-only execution."""

    validation_report: IngestValidationReport

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": "VALIDATION_ONLY",
            "validation_report": self.validation_report.to_dict(),
        }


class OperatorRunTriggerService:
    """Run-trigger orchestration service for Operator Console actions."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def trigger_run(self, command: RunTriggerCommand) -> RunTriggerResult | RunValidationResult:
        """Execute ingest/recompute/plan/(optional apply) deterministically."""
        root = Path(command.folder_path)
        if not root.exists():
            raise ValueError(f"Folder path does not exist: {root}")
        if not root.is_dir():
            raise ValueError(f"Folder path must be a directory: {root}")

        ingest_service = IngestService(self._session_factory)
        files = IngestService.collect_files(root)
        if command.dry_run:
            # Dry-run is strict validation mode: no durable mutations anywhere.
            validation_report = ingest_service.validate_paths(files, authoritative_root=root)
            return RunValidationResult(validation_report=validation_report)

        policy = build_canonical_policy(command.policy_name)
        run_service = RunService(self._session_factory)
        planner = PlanningService(self._session_factory)
        apply_service = ApplyService(self._session_factory)
        ingest_summary = ingest_service.ingest_paths(
            files,
            owner=command.owner,
            context=command.context,
            owner_context_override_confirmed=command.owner_context_override_confirmed,
        )

        run = run_service.create_run(
            owner=command.owner,
            context=command.context,
            naming_strategy=command.naming_strategy,
            owner_context_override_confirmed=command.owner_context_override_confirmed,
        )
        recompute_mode = RecomputeMode.APPLY
        recompute_summary = recompute_canonical_assignments(
            self._session_factory,
            policy=policy,
            context=CanonicalContext(),
            mode=recompute_mode,
        )
        plan_summary = planner.plan_run(
            run.id,
            files,
            ingest_if_needed=False,
        )

        apply_summary = apply_service.apply_run(run.id)

        return RunTriggerResult(
            run_id=str(run.id),
            summary_metrics=self._summary_metrics_payload(
                command=command,
                ingest_summary=ingest_summary,
                plan_summary=plan_summary,
                apply_summary=apply_summary,
            ),
            duplicates_found=plan_summary.duplicate_actions,
            canonical_changes=recompute_summary.changed_count,
        )

    def _summary_metrics_payload(
        self,
        *,
        command: RunTriggerCommand,
        ingest_summary: IngestSummary,
        plan_summary: PlanningSummary,
        apply_summary: ApplySummary | None,
    ) -> dict[str, object]:
        apply_payload: dict[str, int] | None
        if apply_summary is None:
            apply_payload = None
        else:
            apply_payload = {
                "applied_count": apply_summary.applied_count,
                "moves_count": apply_summary.moves_count,
                "duplicates_count": apply_summary.duplicates_count,
                "noop_count": apply_summary.noop_count,
                "errors_count": apply_summary.errors_count,
                "skipped_count": apply_summary.skipped_count,
            }

        return {
            "ingest": {
                "files_scanned": ingest_summary.files_scanned,
                "new_contents": ingest_summary.new_contents,
                "new_instances": ingest_summary.new_instances,
                "duplicates_detected": ingest_summary.duplicates_detected,
                "metadata_extracted": ingest_summary.metadata_extracted,
            },
            "plan": {
                "scanned_count": plan_summary.scanned_count,
                "move_actions": plan_summary.move_actions,
                "duplicate_actions": plan_summary.duplicate_actions,
                "noop_actions": plan_summary.noop_actions,
                "skipped_count": plan_summary.skipped_count,
            },
            "apply": apply_payload,
            "dry_run": command.dry_run,
            "policy_name": policy_name_or_upper(command.policy_name),
            "owner": command.owner,
            "context": command.context,
            "naming_strategy": command.naming_strategy,
        }


def policy_name_or_upper(raw: str) -> str:
    """Normalize a policy name string for stable summary payload output."""
    try:
        return raw.strip().upper()
    except Exception as exc:  # pragma: no cover - defensive only.
        raise MediaManagerError("Invalid policy_name payload") from exc
