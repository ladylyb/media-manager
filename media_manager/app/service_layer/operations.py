"""Mutating/validation façade for API controllers and compatibility adapters."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import time
from uuid import UUID

from media_manager.app.canonical.context import CanonicalContext
from media_manager.app.canonical.factory import build_canonical_policy
from media_manager.app.core.logging_config import get_logger
from media_manager.app.core.naming import DEFAULT_CONTEXT, DEFAULT_OWNER, normalize_naming_strategy
from media_manager.app.persistence.apply import ApplyService
from media_manager.app.persistence.duplicate_reclaim import DuplicateReclaimService
from media_manager.app.persistence.canonicalization import RecomputeMode, recompute_canonical_assignments
from media_manager.app.persistence.duplicate_reviews import DuplicateReviewService
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.integrity import IntegrityService
from media_manager.app.persistence.operation_runs import OperationRunService
from media_manager.app.persistence.phase3_actions import Phase3ActionService
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.policy_settings import PolicySettingsService, UpdatePolicySettingsCommand
from media_manager.app.persistence.models import OperationRunStatus, OperationRunType, TagSource
from media_manager.app.persistence.runs import RunService
from media_manager.app.persistence.tag_enrichment import EnrichmentScope, TagEnrichmentCommand, run_tag_enrichment
from media_manager.app.service_layer.cache import ServiceCache

_WINDOWS_DRIVE_PATH_RE = re.compile(r"^([A-Za-z]):[\\/](.*)$")
_MNT_DRIVE_PATH_RE = re.compile(r"^/mnt/([A-Z])(?:/(.*))?$")
LOGGER = get_logger(__name__)
_DEFAULT_ACTIVE_LIBRARY_SCOPE = "DEFAULT_ACTIVE_LIBRARY"


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


def _nearest_existing_ancestor(path: Path) -> Path:
    current = path
    while not current.exists():
        parent = current.parent
        if parent == current:
            break
        current = parent
    return current


def _validate_duplicate_bin_root_for_execution(root_value: str) -> None:
    root = Path(root_value)
    if root.exists():
        if not root.is_dir():
            raise ValueError(
                "duplicate bin recycle_bin_root must point to a directory path: "
                f"{root_value}"
            )
        if not os.access(root, os.W_OK | os.X_OK):
            raise ValueError(
                "duplicate bin recycle_bin_root is not writable by the current process: "
                f"{root_value}"
            )
        return

    nearest_existing = _nearest_existing_ancestor(root)
    if not nearest_existing.is_dir():
        raise ValueError(
            "duplicate bin recycle_bin_root cannot be created because an ancestor is not a directory: "
            f"{nearest_existing}"
        )
    if not os.access(nearest_existing, os.W_OK | os.X_OK):
        raise ValueError(
            "duplicate bin recycle_bin_root cannot be created because the nearest existing ancestor is not writable: "
            f"{nearest_existing}"
        )


@dataclass
class OperationServices:
    """Shared mutation/validation service entrypoint."""

    session_factory: object
    cache: ServiceCache

    def _op_runs(self) -> OperationRunService:
        return OperationRunService(self.session_factory)

    def _policy(self):
        return PolicySettingsService(self.session_factory).get_settings()

    def _run_integrity_scan_for_paths(
        self,
        *,
        mode: str,
        absolute_paths: list[str],
        trigger: str,
    ) -> dict[str, object]:
        run_log = self._op_runs().start(
            operation_type=OperationRunType.INTEGRITY_SCAN,
            context={"mode": mode, "absolute_paths": absolute_paths, "trigger": trigger},
        )
        try:
            summary = IntegrityService(self.session_factory).scan_paths(
                scan_mode=mode,
                absolute_paths=absolute_paths,
                operation_run_id=UUID(run_log.operation_run_id),
            )
            self._op_runs().complete(UUID(run_log.operation_run_id))
            self.cache.invalidate("integrity_dashboard", "integrity_issues")
            return {**summary.to_dict(), "operation_run_id": run_log.operation_run_id, "trigger": trigger}
        except Exception as exc:
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=str(exc))
            raise

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
            import_integrity_mode = self._policy().integrity_scan_default_mode
            if import_integrity_mode in {"FAST", "DEEP"}:
                imported_paths = [str(path.resolve(strict=False)) for path in service.collect_files(folder)]
                if imported_paths:
                    result["post_ingest_integrity_scan"] = self._run_integrity_scan_for_paths(
                        mode=import_integrity_mode,
                        absolute_paths=imported_paths,
                        trigger="import_pipeline",
                    )
            self._op_runs().complete(UUID(run_log.operation_run_id))
            self.cache.invalidate("dashboard_summary", "latest_metrics", "status", "runs", "home")
            return result
        except Exception as exc:
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=str(exc))
            raise

    def plan(
        self,
        *,
        folder_path: str,
        strict_metadata: bool,
        owner: str = DEFAULT_OWNER,
        context: str = DEFAULT_CONTEXT,
        naming_strategy: str = "SHARED_CANONICAL_NAME",
        owner_context_override_confirmed: bool = False,
    ) -> dict[str, object]:
        folder = normalize_and_resolve_directory(folder_path)
        normalized_strategy = normalize_naming_strategy(naming_strategy)
        run_log = self._op_runs().start(
            operation_type=OperationRunType.PLAN,
            context={
                "folder_path": str(folder),
                "strict_metadata": bool(strict_metadata),
                "owner": owner,
                "context": context,
                "naming_strategy": normalized_strategy,
                "owner_context_override_confirmed": bool(owner_context_override_confirmed),
            },
        )
        ingest = IngestService(self.session_factory)
        run_service = RunService(self.session_factory)
        planner = PlanningService(self.session_factory)
        try:
            files = ingest.collect_files(folder)
            ingest.ingest_paths(files, authoritative_root=folder)
            ingest.classify_paths(
                files,
                owner=owner,
                context=context,
                owner_context_override_confirmed=owner_context_override_confirmed,
            )
            run = run_service.create_run(
                owner=owner,
                context=context,
                naming_strategy=normalized_strategy,
                owner_context_override_confirmed=owner_context_override_confirmed,
            )
            self._op_runs().link_run(UUID(run_log.operation_run_id), linked_run_id=run.id)
            summary = planner.plan_run(run.id, files, ingest_if_needed=False, strict_missing_metadata=strict_metadata)
            self._op_runs().complete(UUID(run_log.operation_run_id))
            self.cache.invalidate("runs", "latest_metrics", "status", "dashboard_summary", "home")
            return {
                "operation": "PLAN",
                "operation_run_id": run_log.operation_run_id,
                "run_id": str(run.id),
                "strict_metadata": strict_metadata,
                "owner": owner,
                "context": context,
                "naming_strategy": normalized_strategy,
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

    def run(
        self,
        *,
        folder_path: str,
        policy_name: str,
        dry_run: bool,
        owner: str = DEFAULT_OWNER,
        context: str = DEFAULT_CONTEXT,
        naming_strategy: str = "SHARED_CANONICAL_NAME",
        owner_context_override_confirmed: bool = False,
    ) -> dict[str, object]:
        folder = normalize_and_resolve_directory(folder_path)
        normalized_strategy = normalize_naming_strategy(naming_strategy)
        run_log = self._op_runs().start(
            operation_type=OperationRunType.OPERATOR_RUN,
            context={
                "folder_path": str(folder),
                "policy_name": policy_name,
                "dry_run": bool(dry_run),
                "owner": owner,
                "context": context,
                "naming_strategy": normalized_strategy,
                "owner_context_override_confirmed": bool(owner_context_override_confirmed),
            },
        )
        try:
            result = self._run_composite(
                folder=folder,
                policy_name=policy_name,
                dry_run=dry_run,
                owner=owner,
                context=context,
                naming_strategy=normalized_strategy,
                owner_context_override_confirmed=owner_context_override_confirmed,
            )
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

    def _run_composite(
        self,
        *,
        folder: Path,
        policy_name: str,
        dry_run: bool,
        owner: str,
        context: str,
        naming_strategy: str,
        owner_context_override_confirmed: bool,
    ) -> dict[str, object]:
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
        ingest_service.classify_paths(
            files,
            owner=owner,
            context=context,
            owner_context_override_confirmed=owner_context_override_confirmed,
        )
        run = RunService(self.session_factory).create_run(
            owner=owner,
            context=context,
            naming_strategy=naming_strategy,
            owner_context_override_confirmed=owner_context_override_confirmed,
        )
        recompute_summary = recompute_canonical_assignments(
            self.session_factory,
            policy=policy,
            context=CanonicalContext(),
            mode=RecomputeMode.APPLY,
        )
        plan_summary = PlanningService(self.session_factory).plan_run(run.id, files, ingest_if_needed=False)
        apply_summary = ApplyService(self.session_factory).apply_run(run.id)
        import_integrity_scan: dict[str, object] | None = None
        import_integrity_mode = self._policy().integrity_scan_default_mode
        if import_integrity_mode in {"FAST", "DEEP"}:
            import_integrity_scan = self._run_integrity_scan_for_paths(
                mode=import_integrity_mode,
                absolute_paths=[str(path.resolve(strict=False)) for path in files],
                trigger="import_pipeline",
            )

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
                "owner": owner,
                "context": context,
                "naming_strategy": naming_strategy,
            },
            "duplicates_found": plan_summary.duplicate_actions,
            "canonical_changes": recompute_summary.changed_count,
            "post_ingest_integrity_scan": import_integrity_scan,
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
                    "optional_fields": ["owner", "context", "naming_strategy", "owner_context_override_confirmed"],
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
                    "operation_id": "integrity_scan",
                    "label": "Integrity Scan",
                    "mutates_state": True,
                    "supports_dry_run": False,
                    "defaults": {"mode": "FAST", "file_instance_ids": []},
                    "required_fields": [],
                },
                {
                    "operation_id": "integrity_quarantine",
                    "label": "Integrity Quarantine",
                    "mutates_state": True,
                    "supports_dry_run": False,
                    "required_fields": ["check_id"],
                },
                {
                    "operation_id": "integrity_restore",
                    "label": "Integrity Restore",
                    "mutates_state": True,
                    "supports_dry_run": False,
                    "required_fields": ["file_instance_id"],
                },
                {
                    "operation_id": "duplicate_reclaim_execute",
                    "label": "Duplicate Reclaim Execute",
                    "mutates_state": True,
                    "supports_dry_run": False,
                    "defaults": {"content_ids": [], "retention_days": 14},
                    "required_fields": [],
                },
                {
                    "operation_id": "duplicate_reclaim_restore",
                    "label": "Duplicate Reclaim Restore",
                    "mutates_state": True,
                    "supports_dry_run": False,
                    "defaults": {"file_instance_ids": []},
                    "required_fields": [],
                },
                {
                    "operation_id": "retention_recycle",
                    "label": "Retention Recycle",
                    "mutates_state": True,
                    "supports_dry_run": False,
                    "required_fields": [],
                },
                {
                    "operation_id": "retention_purge",
                    "label": "Retention Purge",
                    "mutates_state": True,
                    "supports_dry_run": False,
                    "required_fields": [],
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
                    "defaults": {
                        "dry_run": True,
                        "owner": DEFAULT_OWNER,
                        "context": DEFAULT_CONTEXT,
                        "naming_strategy": "SHARED_CANONICAL_NAME",
                    },
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
        naming_strategy: str,
        preferred_roots: tuple[str, ...],
        integrity_scan_default_mode: str,
        integrity_issue_min_confidence: float,
        integrity_notify_on_high_confidence: bool,
        duplicate_reclaim_archive_root: str,
        duplicate_reclaim_default_retention_days: int,
        duplicate_reclaim_notify_on_reviewed_safe: bool,
        integrity_quarantine_root: str,
        integrity_quarantine_retention_days: int,
        recycle_bin_root: str,
        recycle_purge_days: int,
        automation_mode: str,
        recanonicalization_enabled: bool,
        version: int,
    ) -> dict[str, object]:
        result = PolicySettingsService(self.session_factory).update_settings(
            UpdatePolicySettingsCommand(
                selected_policy=selected_policy,
                naming_strategy=naming_strategy,
                preferred_roots=preferred_roots,
                integrity_scan_default_mode=integrity_scan_default_mode,
                integrity_issue_min_confidence=integrity_issue_min_confidence,
                integrity_notify_on_high_confidence=integrity_notify_on_high_confidence,
                duplicate_reclaim_archive_root=duplicate_reclaim_archive_root,
                duplicate_reclaim_default_retention_days=duplicate_reclaim_default_retention_days,
                duplicate_reclaim_notify_on_reviewed_safe=duplicate_reclaim_notify_on_reviewed_safe,
                integrity_quarantine_root=integrity_quarantine_root,
                integrity_quarantine_retention_days=integrity_quarantine_retention_days,
                recycle_bin_root=recycle_bin_root,
                recycle_purge_days=recycle_purge_days,
                automation_mode=automation_mode,
                recanonicalization_enabled=recanonicalization_enabled,
                version=version,
            )
        ).to_dict()
        self.cache.invalidate("status", "policy_snapshot")
        return result

    def duplicate_review_set(
        self,
        *,
        content_id: str,
        review_status: str,
        reviewed_canonical_instance_id: str,
        reviewed_by: str | None = None,
    ) -> dict[str, object]:
        try:
            parsed_content_id = UUID(content_id)
        except ValueError as exc:
            raise ValueError(f"content_id must be a valid UUID: {content_id}") from exc
        try:
            parsed_canonical_instance_id = UUID(reviewed_canonical_instance_id)
        except ValueError as exc:
            raise ValueError(
                "reviewed_canonical_instance_id must be a valid UUID: "
                f"{reviewed_canonical_instance_id}"
            ) from exc

        result = DuplicateReviewService(self.session_factory).upsert_review(
            content_id=parsed_content_id,
            review_status=review_status,
            reviewed_canonical_instance_id=parsed_canonical_instance_id,
            reviewed_by=reviewed_by,
        )
        self.cache.invalidate("duplicates")
        return result

    def duplicate_bin_policy_get(self) -> dict[str, object]:
        """Return only the duplicate-bin-facing policy facts needed by workflow callers."""
        policy = self._policy()
        return {
            "current_move_root": policy.recycle_bin_root,
            "current_retention_days": policy.duplicate_reclaim_default_retention_days,
            "target_recycle_bin_root": policy.recycle_bin_root,
            "implementation": "reclaim_compatibility",
        }

    def duplicate_reclaim_set(
        self,
        *,
        content_id: str,
        reclaim_status: str,
        reviewed_by: str | None = None,
    ) -> dict[str, object]:
        try:
            parsed_content_id = UUID(content_id)
        except ValueError as exc:
            raise ValueError(f"content_id must be a valid UUID: {content_id}") from exc

        run_log = self._op_runs().start(
            operation_type=OperationRunType.DUPLICATE_RECLAIM_REVIEW,
            context={
                "content_id": str(parsed_content_id),
                "reclaim_status": reclaim_status,
                "reviewed_by": reviewed_by,
            },
        )
        LOGGER.debug(
            "duplicate_reclaim_debug: review sync request",
            extra={
                "stage": "duplicate_reclaim_review_request",
                "content_id": str(parsed_content_id),
                "reclaim_status": reclaim_status,
                "reviewed_by": reviewed_by or "",
            },
        )
        try:
            result = DuplicateReclaimService(self.session_factory).set_reclaim_status(
                content_id=parsed_content_id,
                reclaim_status=reclaim_status,
                reviewed_by=reviewed_by,
            )
            LOGGER.debug(
                "duplicate_reclaim_debug: review sync result",
                extra={
                    "stage": "duplicate_reclaim_review_result",
                    "content_id": str(parsed_content_id),
                    "result": result,
                },
            )
            self._op_runs().complete(UUID(run_log.operation_run_id))
            self.cache.invalidate("duplicates")
            return result
        except Exception as exc:
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=str(exc))
            raise

    def integrity_scan(
        self,
        *,
        mode: str,
        file_instance_ids: list[str] | None = None,
        full_rescan: bool = False,
        trigger: str = "manual",
    ) -> dict[str, object]:
        parsed_file_ids: list[UUID] | None = None
        if file_instance_ids:
            parsed_file_ids = []
            for file_id in file_instance_ids:
                try:
                    parsed_file_ids.append(UUID(file_id))
                except ValueError as exc:
                    raise ValueError(f"file_instance_id must be a valid UUID: {file_id}") from exc

        run_log = self._op_runs().start(
            operation_type=OperationRunType.INTEGRITY_SCAN,
            context={
                "mode": mode,
                "file_instance_ids": [str(item) for item in parsed_file_ids or []],
                "full_rescan": bool(full_rescan),
                "trigger": trigger,
            },
        )
        requested_file_count = len(parsed_file_ids or [])
        scan_scope = "EXPLICIT_FILE_IDS" if parsed_file_ids else _DEFAULT_ACTIVE_LIBRARY_SCOPE
        started_at = time.perf_counter()

        def _log_manual_progress(processed_count: int, eligible_file_count: int, issues_found_so_far: int) -> None:
            elapsed_seconds = round(time.perf_counter() - started_at, 2)
            progress_percent = (processed_count / eligible_file_count) * 100.0 if eligible_file_count > 0 else 0.0
            throughput_fps = processed_count / elapsed_seconds if elapsed_seconds > 0 else 0.0
            LOGGER.info(
                (
                    f"Manual integrity scan progress: mode={mode.strip().upper()} scan_scope={scan_scope} "
                    f"processed_count={processed_count}/{eligible_file_count} "
                    f"issues_found_so_far={issues_found_so_far} elapsed_seconds={elapsed_seconds} "
                    f"Progress: {processed_count}/{eligible_file_count} files ({progress_percent:.1f}%) | "
                    f"{throughput_fps:.1f} files/sec | elapsed {elapsed_seconds:.1f}s"
                ),
                extra={
                    "run_id": run_log.operation_run_id,
                    "phase": "integrity",
                    "stage": "manual_scan",
                    "status": "running",
                    "action": "manual_integrity_scan_progress",
                    "action_type": OperationRunType.INTEGRITY_SCAN.value,
                    "scope": scan_scope,
                    "processed_count": processed_count,
                    "total_count": eligible_file_count,
                    "progress_percent": progress_percent,
                    "throughput_fps": throughput_fps,
                    "elapsed_seconds": elapsed_seconds,
                },
            )

        if trigger == "manual":
            LOGGER.info(
                (
                    f"Manual integrity scan started: mode={mode.strip().upper()} "
                    f"requested_file_count={requested_file_count} scan_scope={scan_scope} full_rescan={full_rescan}"
                ),
                extra={
                    "run_id": run_log.operation_run_id,
                    "phase": "integrity",
                    "stage": "manual_scan",
                    "status": "running",
                    "action": "manual_integrity_scan",
                    "action_type": OperationRunType.INTEGRITY_SCAN.value,
                    "total_count": requested_file_count,
                    "scope": scan_scope,
                    "full_rescan": bool(full_rescan),
                },
            )
        try:
            summary = IntegrityService(self.session_factory).scan(
                scan_mode=mode,
                file_instance_ids=parsed_file_ids,
                operation_run_id=UUID(run_log.operation_run_id),
                on_progress=_log_manual_progress if trigger == "manual" else None,
                full_rescan=full_rescan,
            )
            self._op_runs().complete(UUID(run_log.operation_run_id))
            self.cache.invalidate("integrity_dashboard", "integrity_issues")
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            if trigger == "manual":
                LOGGER.info(
                    (
                        f"Manual integrity scan completed: mode={summary.scan_mode} "
                        f"requested_file_count={requested_file_count} "
                        f"scan_scope={scan_scope} "
                        f"eligible_file_count={summary.eligible_file_count} "
                        f"scanned_count={summary.scanned_count} issues_found={summary.issues_found} "
                        f"skipped_count={summary.skipped_count} full_rescan={summary.full_rescan} "
                        f"duration_ms={duration_ms}"
                    ),
                    extra={
                        "run_id": run_log.operation_run_id,
                        "phase": "integrity",
                        "stage": "manual_scan",
                        "status": "completed",
                        "action": "manual_integrity_scan",
                        "action_type": OperationRunType.INTEGRITY_SCAN.value,
                        "total_count": requested_file_count,
                        "scope": scan_scope,
                        "files_count": summary.eligible_file_count,
                        "scanned": summary.scanned_count,
                        "skipped_count": summary.skipped_count,
                        "full_rescan": summary.full_rescan,
                        "duration_ms": duration_ms,
                    },
                )
            return {**summary.to_dict(), "trigger": trigger}
        except Exception as exc:
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=str(exc))
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            if trigger == "manual":
                LOGGER.exception(
                    (
                        f"Manual integrity scan failed: mode={mode.strip().upper()} "
                        f"requested_file_count={requested_file_count} "
                        f"scan_scope={scan_scope} full_rescan={full_rescan} duration_ms={duration_ms}"
                    ),
                    extra={
                        "run_id": run_log.operation_run_id,
                        "phase": "integrity",
                        "stage": "manual_scan",
                        "status": "failed",
                        "action": "manual_integrity_scan",
                        "action_type": OperationRunType.INTEGRITY_SCAN.value,
                        "total_count": requested_file_count,
                        "scope": scan_scope,
                        "full_rescan": bool(full_rescan),
                        "duration_ms": duration_ms,
                    },
                )
            raise

    def integrity_playback_failure(self, *, file_instance_id: str) -> dict[str, object]:
        return self.integrity_scan(
            mode="FAST",
            file_instance_ids=[file_instance_id],
            full_rescan=True,
            trigger="playback_failure",
        )

    def integrity_review_set(
        self,
        *,
        check_id: str,
        decision: str,
        reviewed_by: str | None = None,
    ) -> dict[str, object]:
        try:
            parsed_check_id = UUID(check_id)
        except ValueError as exc:
            raise ValueError(f"check_id must be a valid UUID: {check_id}") from exc

        result = IntegrityService(self.session_factory).set_review_decision(
            check_id=parsed_check_id,
            decision=decision,
            reviewed_by=reviewed_by,
        )
        self.cache.invalidate("integrity_dashboard", "integrity_issues")
        return result

    def integrity_quarantine(self, *, check_id: str) -> dict[str, object]:
        try:
            parsed_check_id = UUID(check_id)
        except ValueError as exc:
            raise ValueError(f"check_id must be a valid UUID: {check_id}") from exc
        run_log = self._op_runs().start(
            operation_type=OperationRunType.INTEGRITY_QUARANTINE,
            context={"check_id": str(parsed_check_id)},
        )
        try:
            result = Phase3ActionService(self.session_factory).quarantine_integrity_issue(check_id=parsed_check_id)
            linked_run_id = result.get("run_id")
            if isinstance(linked_run_id, str):
                self._op_runs().link_run(UUID(run_log.operation_run_id), linked_run_id=UUID(linked_run_id))
            self._op_runs().complete(UUID(run_log.operation_run_id))
            self.cache.invalidate("integrity_dashboard", "integrity_issues", "integrity_quarantine", "duplicates", "analytics")
            return result
        except Exception as exc:
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=str(exc))
            raise

    def integrity_restore(self, *, file_instance_id: str) -> dict[str, object]:
        try:
            parsed_file_instance_id = UUID(file_instance_id)
        except ValueError as exc:
            raise ValueError(f"file_instance_id must be a valid UUID: {file_instance_id}") from exc
        run_log = self._op_runs().start(
            operation_type=OperationRunType.INTEGRITY_RESTORE,
            context={"file_instance_id": str(parsed_file_instance_id)},
        )
        try:
            result = Phase3ActionService(self.session_factory).restore_integrity_quarantine(file_instance_id=parsed_file_instance_id)
            linked_run_id = result.get("run_id")
            if isinstance(linked_run_id, str):
                self._op_runs().link_run(UUID(run_log.operation_run_id), linked_run_id=UUID(linked_run_id))
            self._op_runs().complete(UUID(run_log.operation_run_id))
            self.cache.invalidate("integrity_dashboard", "integrity_issues", "integrity_quarantine", "duplicates", "analytics")
            return result
        except Exception as exc:
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=str(exc))
            raise

    def duplicate_bin_execute(
        self,
        *,
        content_ids: list[str] | None = None,
        retention_days: int | None = None,
    ) -> dict[str, object]:
        """Bin-centered duplicate move entrypoint backed by reclaim compatibility internals."""
        policy = self._policy()
        _validate_duplicate_bin_root_for_execution(policy.recycle_bin_root)
        effective_retention_days = retention_days or policy.duplicate_reclaim_default_retention_days
        parsed_content_ids: list[UUID] | None = None
        if content_ids:
            parsed_content_ids = []
            for content_id in content_ids:
                try:
                    parsed_content_ids.append(UUID(content_id))
                except ValueError as exc:
                    raise ValueError(f"content_id must be a valid UUID: {content_id}") from exc
        LOGGER.debug(
            "duplicate_reclaim_debug: execute request",
            extra={
                "stage": "duplicate_reclaim_execute_request",
                "requested_content_ids": [str(item) for item in parsed_content_ids or []],
                "retention_days": effective_retention_days,
                "duplicate_reclaim_archive_root": policy.duplicate_reclaim_archive_root,
                "duplicate_reclaim_default_retention_days": policy.duplicate_reclaim_default_retention_days,
                "recycle_bin_root": policy.recycle_bin_root,
                "recycle_purge_days": policy.recycle_purge_days,
                "policy_source": "persisted_policy_row" if policy.version > 0 else "default_snapshot",
                "policy_version": policy.version,
            },
        )
        run_log = self._op_runs().start(
            operation_type=OperationRunType.DUPLICATE_RECLAIM_EXECUTE,
            context={
                "content_ids": [str(item) for item in parsed_content_ids or []],
                "retention_days": effective_retention_days,
            },
        )
        try:
            result = Phase3ActionService(self.session_factory).execute_duplicate_reclaim(
                content_ids=parsed_content_ids,
                retention_days=effective_retention_days,
            )
            LOGGER.debug(
                "duplicate_reclaim_debug: execute result",
                extra={
                    "stage": "duplicate_reclaim_execute_result",
                    "requested_content_ids": [str(item) for item in parsed_content_ids or []],
                    "summary": result.get("summary", {}),
                    "diagnostics": result.get("diagnostics", {}),
                },
            )
            linked_run_id = result.get("run_id")
            if isinstance(linked_run_id, str):
                self._op_runs().link_run(UUID(run_log.operation_run_id), linked_run_id=UUID(linked_run_id))
            self._op_runs().complete(UUID(run_log.operation_run_id))
            self.cache.invalidate("duplicates", "duplicate_reclaim_items", "analytics")
            return {**result, "retention_days": effective_retention_days}
        except Exception as exc:
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=str(exc))
            raise

    def duplicate_reclaim_execute(
        self,
        *,
        content_ids: list[str] | None = None,
        retention_days: int | None = None,
    ) -> dict[str, object]:
        """Compatibility wrapper: keep reclaim naming stable while the service boundary shifts to bin-centered terms."""
        return self.duplicate_bin_execute(content_ids=content_ids, retention_days=retention_days)

    def duplicate_bin_restore(self, *, file_instance_ids: list[str] | None = None) -> dict[str, object]:
        """Bin-centered duplicate restore entrypoint backed by reclaim compatibility internals."""
        parsed_file_ids: list[UUID] | None = None
        if file_instance_ids:
            parsed_file_ids = []
            for file_id in file_instance_ids:
                try:
                    parsed_file_ids.append(UUID(file_id))
                except ValueError as exc:
                    raise ValueError(f"file_instance_id must be a valid UUID: {file_id}") from exc
        LOGGER.debug(
            "duplicate_reclaim_debug: restore request",
            extra={
                "stage": "duplicate_reclaim_restore_request",
                "requested_file_instance_ids": [str(item) for item in parsed_file_ids or []],
            },
        )
        run_log = self._op_runs().start(
            operation_type=OperationRunType.DUPLICATE_RECLAIM_RESTORE,
            context={"file_instance_ids": [str(item) for item in parsed_file_ids or []]},
        )
        try:
            result = Phase3ActionService(self.session_factory).restore_duplicate_reclaim(file_instance_ids=parsed_file_ids)
            LOGGER.debug(
                "duplicate_reclaim_debug: restore result",
                extra={
                    "stage": "duplicate_reclaim_restore_result",
                    "requested_file_instance_ids": [str(item) for item in parsed_file_ids or []],
                    "summary": result.get("summary", {}),
                },
            )
            linked_run_id = result.get("run_id")
            if isinstance(linked_run_id, str):
                self._op_runs().link_run(UUID(run_log.operation_run_id), linked_run_id=UUID(linked_run_id))
            self._op_runs().complete(UUID(run_log.operation_run_id))
            self.cache.invalidate("duplicates", "duplicate_reclaim_items", "analytics")
            return result
        except Exception as exc:
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=str(exc))
            raise

    def duplicate_reclaim_restore(self, *, file_instance_ids: list[str] | None = None) -> dict[str, object]:
        """Compatibility wrapper: keep reclaim naming stable while the service boundary shifts to bin-centered terms."""
        return self.duplicate_bin_restore(file_instance_ids=file_instance_ids)

    def retention_recycle_duplicates(self, *, file_instance_ids: list[str] | None = None) -> dict[str, object]:
        parsed_file_ids: list[UUID] | None = None
        if file_instance_ids:
            parsed_file_ids = []
            for file_id in file_instance_ids:
                try:
                    parsed_file_ids.append(UUID(file_id))
                except ValueError as exc:
                    raise ValueError(f"file_instance_id must be a valid UUID: {file_id}") from exc
        run_log = self._op_runs().start(
            operation_type=OperationRunType.RETENTION_RECYCLE,
            context={"scope": "duplicates", "file_instance_ids": [str(item) for item in parsed_file_ids or []]},
        )
        try:
            result = Phase3ActionService(self.session_factory).recycle_duplicate_reclaim(file_instance_ids=parsed_file_ids)
            linked_run_id = result.get("run_id")
            if isinstance(linked_run_id, str):
                self._op_runs().link_run(UUID(run_log.operation_run_id), linked_run_id=UUID(linked_run_id))
            self._op_runs().complete(UUID(run_log.operation_run_id))
            self.cache.invalidate("duplicates", "duplicate_reclaim_items", "retention_recycle_items", "analytics")
            return result
        except Exception as exc:
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=str(exc))
            raise

    def retention_recycle_integrity(self, *, file_instance_ids: list[str] | None = None) -> dict[str, object]:
        parsed_file_ids: list[UUID] | None = None
        if file_instance_ids:
            parsed_file_ids = []
            for file_id in file_instance_ids:
                try:
                    parsed_file_ids.append(UUID(file_id))
                except ValueError as exc:
                    raise ValueError(f"file_instance_id must be a valid UUID: {file_id}") from exc
        run_log = self._op_runs().start(
            operation_type=OperationRunType.RETENTION_RECYCLE,
            context={"scope": "integrity", "file_instance_ids": [str(item) for item in parsed_file_ids or []]},
        )
        try:
            result = Phase3ActionService(self.session_factory).recycle_integrity_quarantine(file_instance_ids=parsed_file_ids)
            linked_run_id = result.get("run_id")
            if isinstance(linked_run_id, str):
                self._op_runs().link_run(UUID(run_log.operation_run_id), linked_run_id=UUID(linked_run_id))
            self._op_runs().complete(UUID(run_log.operation_run_id))
            self.cache.invalidate("integrity_dashboard", "integrity_quarantine", "retention_recycle_items", "analytics")
            return result
        except Exception as exc:
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=str(exc))
            raise

    def retention_purge_duplicates(self, *, file_instance_ids: list[str] | None = None) -> dict[str, object]:
        parsed_file_ids: list[UUID] | None = None
        if file_instance_ids:
            parsed_file_ids = []
            for file_id in file_instance_ids:
                try:
                    parsed_file_ids.append(UUID(file_id))
                except ValueError as exc:
                    raise ValueError(f"file_instance_id must be a valid UUID: {file_id}") from exc
        run_log = self._op_runs().start(
            operation_type=OperationRunType.RETENTION_PURGE,
            context={"scope": "duplicates", "file_instance_ids": [str(item) for item in parsed_file_ids or []]},
        )
        try:
            result = Phase3ActionService(self.session_factory).purge_duplicate_reclaim(file_instance_ids=parsed_file_ids)
            linked_run_id = result.get("run_id")
            if isinstance(linked_run_id, str):
                self._op_runs().link_run(UUID(run_log.operation_run_id), linked_run_id=UUID(linked_run_id))
            self._op_runs().complete(UUID(run_log.operation_run_id))
            self.cache.invalidate("duplicates", "duplicate_reclaim_items", "retention_recycle_items", "analytics")
            return result
        except Exception as exc:
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=str(exc))
            raise

    def retention_purge_integrity(self, *, file_instance_ids: list[str] | None = None) -> dict[str, object]:
        parsed_file_ids: list[UUID] | None = None
        if file_instance_ids:
            parsed_file_ids = []
            for file_id in file_instance_ids:
                try:
                    parsed_file_ids.append(UUID(file_id))
                except ValueError as exc:
                    raise ValueError(f"file_instance_id must be a valid UUID: {file_id}") from exc
        run_log = self._op_runs().start(
            operation_type=OperationRunType.RETENTION_PURGE,
            context={"scope": "integrity", "file_instance_ids": [str(item) for item in parsed_file_ids or []]},
        )
        try:
            result = Phase3ActionService(self.session_factory).purge_integrity_quarantine(file_instance_ids=parsed_file_ids)
            linked_run_id = result.get("run_id")
            if isinstance(linked_run_id, str):
                self._op_runs().link_run(UUID(run_log.operation_run_id), linked_run_id=UUID(linked_run_id))
            self._op_runs().complete(UUID(run_log.operation_run_id))
            self.cache.invalidate("integrity_dashboard", "integrity_quarantine", "retention_recycle_items", "analytics")
            return result
        except Exception as exc:
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=str(exc))
            raise

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
