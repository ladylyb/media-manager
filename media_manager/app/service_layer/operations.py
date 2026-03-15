"""Mutating/validation façade for API controllers and compatibility adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from uuid import UUID

from media_manager.app.canonical.context import CanonicalContext
from media_manager.app.canonical.factory import build_canonical_policy
from media_manager.app.persistence.apply import ApplyService
from media_manager.app.persistence.canonicalization import RecomputeMode, recompute_canonical_assignments
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.operation_runs import OperationRunService
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.policy_settings import PolicySettingsService, UpdatePolicySettingsCommand
from media_manager.app.persistence.models import OperationRunStatus, OperationRunType, TagSource
from media_manager.app.persistence.runs import RunService
from media_manager.app.persistence.tag_enrichment import EnrichmentScope, TagEnrichmentCommand, run_tag_enrichment
from media_manager.app.service_layer.cache import ServiceCache

_WINDOWS_DRIVE_PATH_RE = re.compile(r"^([A-Za-z]):[\\/](.*)$")
_MNT_DRIVE_PATH_RE = re.compile(r"^/mnt/([A-Z])(?:/(.*))?$")


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1].strip()
    return value


def _iter_normalized_directory_candidates(raw: str) -> list[Path]:
    """Return deterministic candidate directories for GUI-provided path variants."""
    normalized = _strip_wrapping_quotes(raw.strip())
    if not normalized:
        raise ValueError("folder_path is required.")

    candidates: list[Path] = [Path(normalized)]

    mnt_match = _MNT_DRIVE_PATH_RE.match(normalized)
    if mnt_match is not None:
        drive = mnt_match.group(1).lower()
        tail = mnt_match.group(2) or ""
        mapped = Path("/mnt") / drive
        if tail:
            mapped = mapped / tail
        candidates.append(mapped)

    win_match = _WINDOWS_DRIVE_PATH_RE.match(normalized)
    if win_match is not None:
        drive = win_match.group(1).lower()
        tail = win_match.group(2).replace("\\", "/").lstrip("/")
        mapped = Path("/mnt") / drive
        if tail:
            mapped = mapped / tail
        candidates.append(mapped)

    # Keep order stable and remove duplicates while preserving first occurrence.
    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def normalize_and_resolve_directory(raw: str) -> Path:
    """Normalize common GUI path forms and resolve a readable directory."""
    candidates = _iter_normalized_directory_candidates(raw)
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate

    normalized_input = _strip_wrapping_quotes(raw.strip())
    raise ValueError(
        "Folder path does not exist or is not a directory: "
        f"{normalized_input}. Accepted examples: /mnt/c/path/to/folder, C:\\path\\to\\folder "
        "(auto-mapped on WSL), and unquoted absolute paths."
    )


@dataclass
class OperationServices:
    """Shared mutation/validation service entrypoint."""

    session_factory: object
    cache: ServiceCache

    def _op_runs(self) -> OperationRunService:
        return OperationRunService(self.session_factory)

    def ingest(self, *, folder_path: str, dry_run: bool) -> dict[str, object]:
        folder = normalize_and_resolve_directory(folder_path)
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
            self.cache.invalidate("dashboard_summary", "latest_metrics", "status", "runs", "home")
            return result
        except Exception as exc:
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=str(exc))
            raise

    def plan(self, *, folder_path: str, strict_metadata: bool) -> dict[str, object]:
        folder = normalize_and_resolve_directory(folder_path)
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
            self.cache.invalidate("runs", "latest_metrics", "status", "dashboard_summary", "home")
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
            self.cache.invalidate("dashboard_summary", "latest_metrics", "runs", "status", "home")
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
                self.cache.invalidate("latest_metrics", "status", "runs", "home")
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
        folder = normalize_and_resolve_directory(folder_path)
        run_log = self._op_runs().start(
            operation_type=OperationRunType.OPERATOR_RUN,
            context={"folder_path": str(folder), "policy_name": policy_name, "dry_run": bool(dry_run)},
        )
        try:
            result = self._run_composite(folder=folder, policy_name=policy_name, dry_run=dry_run)
            linked_run_id = result.get("run_id")
            if isinstance(linked_run_id, str):
                try:
                    self._op_runs().link_run(UUID(run_log.operation_run_id), linked_run_id=UUID(linked_run_id))
                except Exception:
                    pass
            self._op_runs().complete(UUID(run_log.operation_run_id))
            self.cache.invalidate("dashboard_summary", "latest_metrics", "status", "runs", "home")
            return {**result, "operation_run_id": run_log.operation_run_id}
        except Exception as exc:
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=str(exc))
            raise

    def _run_composite(self, *, folder: Path, policy_name: str, dry_run: bool) -> dict[str, object]:
        ingest_service = IngestService(self.session_factory)
        files = IngestService.collect_files(folder)
        if dry_run:
            validation_report = ingest_service.validate_paths(files, authoritative_root=folder)
            return {
                "mode": "VALIDATION_ONLY",
                "validation_report": validation_report.to_dict(),
            }

        policy = build_canonical_policy(policy_name)
        ingest_summary = ingest_service.ingest_paths(files)
        run = RunService(self.session_factory).create_run()
        recompute_summary = recompute_canonical_assignments(
            self.session_factory,
            policy=policy,
            context=CanonicalContext(),
            mode=RecomputeMode.APPLY,
        )
        plan_summary = PlanningService(self.session_factory).plan_run(run.id, files, ingest_if_needed=False)
        apply_summary = ApplyService(self.session_factory).apply_run(run.id)

        return {
            "mode": "EXECUTION",
            "run_id": str(run.id),
            "summary_metrics": {
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
                "apply": {
                    "applied_count": apply_summary.applied_count,
                    "moves_count": apply_summary.moves_count,
                    "duplicates_count": apply_summary.duplicates_count,
                    "noop_count": apply_summary.noop_count,
                    "errors_count": apply_summary.errors_count,
                    "skipped_count": apply_summary.skipped_count,
                },
                "dry_run": dry_run,
                "policy_name": policy_name.strip().upper(),
            },
            "duplicates_found": plan_summary.duplicate_actions,
            "canonical_changes": recompute_summary.changed_count,
        }

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
                    "label": "Composite Run (Compatibility)",
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
            if run_all == (canonical_id is not None):
                raise ValueError("Specify exactly one of all=true or canonical_id.")
            if int(batch_size) <= 0:
                raise ValueError("batch_size must be > 0.")
            try:
                source_value = TagSource(source)
            except Exception as exc:
                raise ValueError(f"Invalid source: {source}") from exc
            canonical_uuid: UUID | None = None
            if canonical_id is not None:
                canonical_uuid = UUID(canonical_id)
            summary = run_tag_enrichment(
                self.session_factory,
                TagEnrichmentCommand(
                    scope=EnrichmentScope.ALL if run_all else EnrichmentScope.SINGLE,
                    canonical_id=canonical_uuid,
                    batch_size=batch_size,
                    source=source_value,
                ),
            )
            self._op_runs().complete(UUID(run_log.operation_run_id))
            self.cache.invalidate("latest_metrics", "status", "runs", "home")
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
        folder = normalize_and_resolve_directory(folder_path)
        return IngestService(self.session_factory).validate_path(folder).to_dict()
