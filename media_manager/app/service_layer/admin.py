"""Admin service-layer operations for safe development admin workflows."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import inspect, text

from media_manager.app.persistence.base import transactional_session
from media_manager.app.persistence.benchmark_runs import BenchmarkRunStore
from media_manager.app.persistence.models import BenchmarkRunType, OperationRunType
from media_manager.app.persistence.operation_runs import OperationRunService
from media_manager.app.service_layer.errors import ServiceLayerException

LOGGER = logging.getLogger(__name__)

DEFAULT_CHALLENGE_WORD = "media-manager"
DEFAULT_BENCHMARK_MAX_ITEMS = 10_000
DEFAULT_BENCHMARK_METADATA_BATCH_SIZE = 1_000

# Dependency-safe truncate order (children first, roots last).
RESET_TABLE_ALLOWLIST: tuple[str, ...] = (
    "benchmark_runs",
    "failure_events",
    "apply_audit_items",
    "apply_audit_runs",
    "planned_actions",
    "canonical_recompute_items",
    "canonical_recompute_runs",
    "tag_enrichment_items",
    "tag_enrichment_runs",
    "canonical_tags",
    "tags",
    "media_metadata",
    "metadata_codes",
    "canonical_assignments",
    "media_file",
    "file_instances",
    "file_contents",
    "files",
    "content_objects",
    "runs",
    "operation_runs",
    "operator_policy_settings",
)

PROTECTED_TABLES: frozenset[str] = frozenset(
    {
        "alembic_version",
        "spatial_ref_sys",
        "geography_columns",
        "geometry_columns",
        "raster_columns",
        "raster_overviews",
    }
)


def _flag_enabled(name: str) -> bool:
    return (os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class AdminServices:
    """Admin service entrypoint with explicit destructive-operation safeguards."""

    session_factory: object

    def _op_runs(self) -> OperationRunService:
        return OperationRunService(self.session_factory)

    def _benchmark_runs(self) -> BenchmarkRunStore:
        return BenchmarkRunStore(self.session_factory)

    def db_reset(self, *, dry_run: bool, challenge_word: str | None) -> dict[str, object]:
        """Reset app data tables in dev/test environments only."""
        env = (os.getenv("MEDIA_MANAGER_ENV", "") or "").strip().lower() or "<unknown>"
        affected_tables: tuple[str, ...] = ()
        run_log = self._op_runs().start(
            operation_type=OperationRunType.DB_RESET,
            context={"dry_run": bool(dry_run), "challenge_word_present": bool((challenge_word or "").strip())},
        )
        try:
            env = self._validate_environment()
            self._validate_challenge(dry_run=dry_run, challenge_word=challenge_word)
            affected_tables = self._build_reset_plan()

            if dry_run:
                self._log_attempt(
                    env=env,
                    dry_run=True,
                    success=True,
                    affected_tables=affected_tables,
                    error_code=None,
                )
                self._op_runs().complete(UUID(run_log.operation_run_id))
                return {
                    "success": True,
                    "dry_run": True,
                    "affected_tables": list(affected_tables),
                    "message": "Dry-run only. No data deleted.",
                }

            self._execute_reset_transaction(affected_tables=affected_tables)
        except ServiceLayerException as exc:
            self._log_attempt(
                env=env,
                dry_run=bool(dry_run),
                success=False,
                affected_tables=affected_tables,
                error_code=exc.code,
            )
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=exc.message)
            raise
        except Exception as exc:
            self._log_attempt(
                env=env,
                dry_run=bool(dry_run),
                success=False,
                affected_tables=affected_tables,
                error_code="RESET_FAILED",
            )
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=str(exc))
            raise ServiceLayerException(
                code="INTERNAL_ERROR",
                message=f"Database reset failed: {exc}",
                http_status=500,
            ) from exc

        self._log_attempt(
            env=env,
            dry_run=False,
            success=True,
            affected_tables=affected_tables,
            error_code=None,
        )
        if not self._reset_wipes_operation_history(affected_tables):
            self._op_runs().complete(UUID(run_log.operation_run_id))
        return {
            "success": True,
            "dry_run": False,
            "affected_tables": list(affected_tables),
            "message": "Database reset completed.",
        }

    def benchmark_metadata_queue(
        self,
        *,
        items: int,
        batch_size: int,
        challenge_word: str | None,
    ) -> dict[str, object]:
        validated_items = self._validate_benchmark_request(items=items, challenge_word=challenge_word)
        validated_batch_size = int(batch_size)
        if validated_batch_size < 1 or validated_batch_size > validated_items:
            raise ServiceLayerException(
                code="VALIDATION_ERROR",
                message=f"batch_size must be within [1, {validated_items}].",
                http_status=400,
            )
        return self._queue_benchmark(
            benchmark_type=BenchmarkRunType.METADATA,
            operation_type=OperationRunType.BENCHMARK_METADATA,
            parameters={
                "items": validated_items,
                "batch_size": validated_batch_size,
            },
        )

    def benchmark_discovery_queue(
        self,
        *,
        items: int,
        challenge_word: str | None,
    ) -> dict[str, object]:
        validated_items = self._validate_benchmark_request(items=items, challenge_word=challenge_word)
        return self._queue_benchmark(
            benchmark_type=BenchmarkRunType.DISCOVERY,
            operation_type=OperationRunType.BENCHMARK_DISCOVERY,
            parameters={"items": validated_items},
        )

    def benchmark_runs(self, *, limit: int = 50) -> list[dict[str, object]]:
        return [item.to_dict() for item in self._benchmark_runs().list_history(limit=limit)]

    def benchmark_run_detail(self, *, operation_run_id: str) -> dict[str, object]:
        parsed = self._parse_operation_run_id(operation_run_id)
        snapshot = self._benchmark_runs().get(parsed)
        if snapshot is None:
            raise ServiceLayerException(
                code="NOT_FOUND",
                message=f"Benchmark run not found: {operation_run_id}",
                http_status=404,
            )
        return snapshot.to_dict()

    def benchmark_run_cancel(self, *, operation_run_id: str) -> dict[str, object]:
        parsed = self._parse_operation_run_id(operation_run_id)
        existing = self._benchmark_runs().get(parsed)
        if existing is None:
            raise ServiceLayerException(
                code="NOT_FOUND",
                message=f"Benchmark run not found: {operation_run_id}",
                http_status=404,
            )
        snapshot = self._benchmark_runs().request_cancel(parsed)
        if existing.status == "QUEUED":
            self._op_runs().fail(parsed, error_message="Benchmark cancelled before execution.")
        return snapshot.to_dict()

    def _queue_benchmark(
        self,
        *,
        benchmark_type: BenchmarkRunType,
        operation_type: OperationRunType,
        parameters: dict[str, object],
    ) -> dict[str, object]:
        run_log = self._op_runs().start(operation_type=operation_type, context=dict(parameters))
        try:
            snapshot = self._benchmark_runs().create(
                operation_run_id=UUID(run_log.operation_run_id),
                benchmark_type=benchmark_type,
                parameters=parameters,
            )
            return {
                "queued": True,
                "operation_run_id": run_log.operation_run_id,
                "benchmark": snapshot.to_dict(),
            }
        except Exception as exc:
            self._op_runs().fail(UUID(run_log.operation_run_id), error_message=str(exc))
            raise

    def _validate_benchmark_request(self, *, items: int, challenge_word: str | None) -> int:
        env = self._validate_environment()
        if not _flag_enabled("MEDIA_MANAGER_BENCHMARKS_ENABLED"):
            raise ServiceLayerException(
                code="FEATURE_DISABLED",
                message="Benchmarks are disabled. Set MEDIA_MANAGER_BENCHMARKS_ENABLED=true to enable them.",
                http_status=403,
                details={"media_manager_env": env},
            )
        self._validate_challenge(dry_run=False, challenge_word=challenge_word)
        parsed_items = int(items)
        max_items = int(os.getenv("MEDIA_MANAGER_BENCHMARK_MAX_ITEMS", str(DEFAULT_BENCHMARK_MAX_ITEMS)))
        if parsed_items < 1 or parsed_items > max_items:
            raise ServiceLayerException(
                code="VALIDATION_ERROR",
                message=f"benchmark items must be within [1, {max_items}].",
                http_status=400,
            )
        return parsed_items

    def _parse_operation_run_id(self, operation_run_id: str) -> UUID:
        try:
            return UUID(operation_run_id)
        except ValueError as exc:
            raise ServiceLayerException(
                code="VALIDATION_ERROR",
                message=f"operation_run_id must be a valid UUID: {operation_run_id}",
                http_status=400,
            ) from exc

    def _validate_environment(self) -> str:
        env = (os.getenv("MEDIA_MANAGER_ENV", "") or "").strip().lower()
        if env not in {"dev", "test"}:
            raise ServiceLayerException(
                code="FORBIDDEN_ENV",
                message="Admin destructive operations are allowed only when MEDIA_MANAGER_ENV is dev or test.",
                http_status=403,
                details={"media_manager_env": env or "<unset>"},
            )
        return env

    def _validate_challenge(self, *, dry_run: bool, challenge_word: str | None) -> None:
        if dry_run:
            return
        expected = os.getenv("MEDIA_MANAGER_DB_RESET_CHALLENGE_WORD", DEFAULT_CHALLENGE_WORD)
        received = (challenge_word or "").strip()
        if not received:
            raise ServiceLayerException(
                code="VALIDATION_ERROR",
                message="challenge_word is required when dry_run is false.",
                http_status=400,
            )
        if received != expected:
            raise ServiceLayerException(
                code="VALIDATION_ERROR",
                message="challenge_word is incorrect.",
                http_status=400,
            )

    def _build_reset_plan(self) -> tuple[str, ...]:
        tables = list(RESET_TABLE_ALLOWLIST)
        if _flag_enabled("MEDIA_MANAGER_DB_RESET_INCLUDE_DYNAMIC"):
            with self.session_factory() as session:
                inspector = inspect(session.get_bind())
                all_tables = set(inspector.get_table_names(schema="public"))
            extras = sorted(table for table in all_tables if table not in PROTECTED_TABLES and table not in tables)
            if extras:
                LOGGER.warning(
                    "Database reset dynamic extras included",
                    extra={
                        "phase": "admin",
                        "action": "DB_RESET_DYNAMIC_EXTRAS",
                        "extra_tables": extras,
                    },
                )
                tables.extend(extras)
        return tuple(tables)

    def _execute_reset_transaction(self, *, affected_tables: tuple[str, ...]) -> None:
        with transactional_session(self.session_factory) as session:
            quoted = ", ".join(f'"{table_name}"' for table_name in affected_tables)
            session.execute(text(f"TRUNCATE TABLE {quoted} CASCADE"))

    def _reset_wipes_operation_history(self, affected_tables: tuple[str, ...]) -> bool:
        return "operation_runs" in affected_tables or "runs" in affected_tables

    def _log_attempt(
        self,
        *,
        env: str,
        dry_run: bool,
        success: bool,
        affected_tables: tuple[str, ...],
        error_code: str | None,
    ) -> None:
        level = logging.INFO if success else logging.WARNING
        LOGGER.log(
            level,
            "Database reset attempt",
            extra={
                "phase": "admin",
                "action": "DB_RESET",
                "allowed_env": env,
                "dry_run": dry_run,
                "success": success,
                "affected_tables_count": len(affected_tables),
                "affected_tables": list(affected_tables),
                "error_code": error_code,
            },
        )
