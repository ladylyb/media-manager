"""Admin service-layer operations for safe development database reset."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from sqlalchemy import inspect, text

from media_manager.app.persistence.base import transactional_session
from media_manager.app.service_layer.errors import ServiceLayerException

LOGGER = logging.getLogger(__name__)

DEFAULT_CHALLENGE_WORD = "media-manager"

# Dependency-safe truncate order (children first, roots last).
RESET_TABLE_ALLOWLIST: tuple[str, ...] = (
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

    def db_reset(self, *, dry_run: bool, challenge_word: str | None) -> dict[str, object]:
        """Reset app data tables in dev/test environments only."""
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
            return {
                "success": True,
                "dry_run": True,
                "affected_tables": list(affected_tables),
                "message": "Dry-run only. No data deleted.",
            }

        try:
            self._execute_reset_transaction(affected_tables=affected_tables)
        except Exception as exc:
            self._log_attempt(
                env=env,
                dry_run=False,
                success=False,
                affected_tables=affected_tables,
                error_code="RESET_FAILED",
            )
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
        return {
            "success": True,
            "dry_run": False,
            "affected_tables": list(affected_tables),
            "message": "Database reset completed.",
        }

    def _validate_environment(self) -> str:
        env = (os.getenv("MEDIA_MANAGER_ENV", "") or "").strip().lower()
        if env not in {"dev", "test"}:
            raise ServiceLayerException(
                code="FORBIDDEN_ENV",
                message="Database reset is allowed only when MEDIA_MANAGER_ENV is dev or test.",
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
            # Execute a single TRUNCATE statement so FK-related tables are handled atomically.
            # Names are sourced from static allowlist + vetted inspector output.
            quoted = ", ".join(f'"{table_name}"' for table_name in affected_tables)
            session.execute(text(f"TRUNCATE TABLE {quoted}"))

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
