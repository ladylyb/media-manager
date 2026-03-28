"""Persistence service for deterministic operator policy settings."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.canonical.factory import build_canonical_policy, resolve_default_policy_name
from media_manager.app.core.naming import normalize_naming_strategy
from media_manager.app.core.errors import PolicySettingsValidationError, PolicySettingsVersionConflictError
from media_manager.app.persistence.base import transactional_session
from media_manager.app.persistence.models import NamingStrategyDB, OperatorPolicySetting

_POLICY_ROW_ID = 1


@dataclass(frozen=True)
class PolicySettingsSnapshot:
    """Deterministic snapshot for operator policy settings."""

    selected_policy: str
    naming_strategy: str
    preferred_roots: tuple[str, ...]
    integrity_scan_default_mode: str
    integrity_issue_min_confidence: float
    integrity_notify_on_high_confidence: bool
    duplicate_reclaim_archive_root: str
    duplicate_reclaim_default_retention_days: int
    duplicate_reclaim_notify_on_reviewed_safe: bool
    integrity_quarantine_root: str
    integrity_quarantine_retention_days: int
    recycle_bin_root: str
    recycle_purge_days: int
    automation_mode: str
    recanonicalization_enabled: bool
    updated_at: datetime
    version: int

    def tie_breaker_rules(self) -> dict[str, str | list[str]]:
        """Return fixed tie-breaker ordering for the selected policy."""
        policy = build_canonical_policy(self.selected_policy)
        normalized = self.selected_policy.upper()
        if normalized == "FIRST_SEEN":
            order = ["first_seen_at ASC", "file_instance_id ASC"]
        elif normalized == "PREFER_ROOT":
            order = [
                "preferred_root_match DESC",
                "first_seen_at ASC",
                "file_instance_id ASC",
            ]
        elif normalized == "EXIF_FILENAME_FALLBACK":
            order = [
                "embedded_metadata_evidence DESC",
                "filename_date_evidence DESC",
                "preferred_root_match DESC",
                "first_seen_at ASC",
                "file_instance_id ASC",
            ]
        else:
            order = [
                "absolute_path_length ASC",
                "absolute_path ASC",
                "first_seen_at ASC",
                "file_instance_id ASC",
            ]
        return {
            "effective_order": order,
            "policy_name": policy.name,
            "policy_version": policy.version,
        }

    def to_dict(self) -> dict[str, object]:
        """Return structured JSON payload for Operator Console APIs."""
        return {
            "canonical_priority": {
                "selected_policy": self.selected_policy,
                "preferred_roots": list(self.preferred_roots),
            },
            "integrity": {
                "default_scan_mode": self.integrity_scan_default_mode,
                "issue_min_confidence": self.integrity_issue_min_confidence,
                "notify_on_high_confidence": self.integrity_notify_on_high_confidence,
            },
            "duplicate_reclaim": {
                "archive_root": self.duplicate_reclaim_archive_root,
                "default_retention_days": self.duplicate_reclaim_default_retention_days,
                "notify_on_reviewed_safe": self.duplicate_reclaim_notify_on_reviewed_safe,
            },
            "retention": {
                "quarantine_root": self.integrity_quarantine_root,
                "recycle_bin_root": self.recycle_bin_root,
                "quarantine_retention_days": self.integrity_quarantine_retention_days,
                "recycle_purge_days": self.recycle_purge_days,
            },
            "automation": {
                "mode": self.automation_mode,
            },
            "naming": {
                "strategy": self.naming_strategy,
            },
            "tie_breaker_rules": self.tie_breaker_rules(),
            "recanonicalization": {
                "enabled": self.recanonicalization_enabled,
            },
            "metadata": {
                "updated_at": self.updated_at.astimezone(timezone.utc).isoformat(),
                "version": self.version,
            },
        }


@dataclass(frozen=True)
class UpdatePolicySettingsCommand:
    """Validated command object for operator policy updates."""

    selected_policy: str
    naming_strategy: str
    preferred_roots: tuple[str, ...]
    integrity_scan_default_mode: str
    integrity_issue_min_confidence: float
    integrity_notify_on_high_confidence: bool
    duplicate_reclaim_archive_root: str
    duplicate_reclaim_default_retention_days: int
    duplicate_reclaim_notify_on_reviewed_safe: bool
    integrity_quarantine_root: str
    integrity_quarantine_retention_days: int
    recycle_bin_root: str
    recycle_purge_days: int
    automation_mode: str
    recanonicalization_enabled: bool
    version: int


class PolicySettingsService:
    """Durable policy settings service with explicit optimistic versioning."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_settings(self) -> PolicySettingsSnapshot:
        """Load persisted policy settings or deterministic environment defaults."""
        with self._session_factory() as session:
            row = session.get(OperatorPolicySetting, _POLICY_ROW_ID)
            if row is None:
                return self._default_snapshot()
            return self._snapshot_from_row(row)

    def update_settings(self, command: UpdatePolicySettingsCommand) -> PolicySettingsSnapshot:
        """Persist policy settings using optimistic version checks."""
        validated = self._validate_command(command)
        with transactional_session(self._session_factory) as session:
            row = session.scalar(
                select(OperatorPolicySetting)
                .where(OperatorPolicySetting.id == _POLICY_ROW_ID)
                .with_for_update()
            )
            now = datetime.now(timezone.utc)

            if row is None:
                if validated.version != 0:
                    raise PolicySettingsVersionConflictError(
                        f"Policy settings version conflict: expected 0 for create, got {validated.version}."
                    )
                row = OperatorPolicySetting(
                    id=_POLICY_ROW_ID,
                    selected_policy=validated.selected_policy,
                    naming_strategy=validated.naming_strategy,
                    preferred_roots_json=self._serialize_roots(validated.preferred_roots),
                    integrity_scan_default_mode=validated.integrity_scan_default_mode,
                    integrity_issue_min_confidence=validated.integrity_issue_min_confidence,
                    duplicate_reclaim_default_retention_days=validated.duplicate_reclaim_default_retention_days,
                    integrity_quarantine_retention_days=validated.integrity_quarantine_retention_days,
                    recycle_purge_days=validated.recycle_purge_days,
                    recycle_bin_root=validated.recycle_bin_root,
                    duplicate_reclaim_archive_root=validated.duplicate_reclaim_archive_root,
                    integrity_quarantine_root=validated.integrity_quarantine_root,
                    integrity_notify_on_high_confidence=validated.integrity_notify_on_high_confidence,
                    duplicate_reclaim_notify_on_reviewed_safe=validated.duplicate_reclaim_notify_on_reviewed_safe,
                    automation_mode=validated.automation_mode,
                    recanonicalization_enabled=validated.recanonicalization_enabled,
                    version=1,
                    updated_at=now,
                )
                session.add(row)
                session.flush()
                return self._snapshot_from_row(row)

            if row.version != validated.version:
                raise PolicySettingsVersionConflictError(
                    f"Policy settings version conflict: expected {row.version}, got {validated.version}."
                )

            row.selected_policy = validated.selected_policy
            row.naming_strategy = validated.naming_strategy
            row.preferred_roots_json = self._serialize_roots(validated.preferred_roots)
            row.integrity_scan_default_mode = validated.integrity_scan_default_mode
            row.integrity_issue_min_confidence = validated.integrity_issue_min_confidence
            row.duplicate_reclaim_default_retention_days = validated.duplicate_reclaim_default_retention_days
            row.integrity_quarantine_retention_days = validated.integrity_quarantine_retention_days
            row.recycle_purge_days = validated.recycle_purge_days
            row.recycle_bin_root = validated.recycle_bin_root
            row.duplicate_reclaim_archive_root = validated.duplicate_reclaim_archive_root
            row.integrity_quarantine_root = validated.integrity_quarantine_root
            row.integrity_notify_on_high_confidence = validated.integrity_notify_on_high_confidence
            row.duplicate_reclaim_notify_on_reviewed_safe = validated.duplicate_reclaim_notify_on_reviewed_safe
            row.automation_mode = validated.automation_mode
            row.recanonicalization_enabled = validated.recanonicalization_enabled
            row.version += 1
            row.updated_at = now
            session.flush()
            return self._snapshot_from_row(row)

    def _validate_command(self, command: UpdatePolicySettingsCommand) -> UpdatePolicySettingsCommand:
        try:
            selected_policy = command.selected_policy.strip().upper()
        except Exception as exc:
            raise PolicySettingsValidationError("selected_policy must be a string.") from exc

        if command.version < 0:
            raise PolicySettingsValidationError("version must be >= 0.")

        try:
            build_canonical_policy(selected_policy)
        except Exception as exc:
            raise PolicySettingsValidationError(str(exc)) from exc

        normalized_roots = self._normalize_roots(command.preferred_roots)
        return UpdatePolicySettingsCommand(
            selected_policy=selected_policy,
            naming_strategy=self._validate_naming_strategy(command.naming_strategy),
            preferred_roots=normalized_roots,
            integrity_scan_default_mode=self._validate_scan_mode(command.integrity_scan_default_mode),
            integrity_issue_min_confidence=self._validate_confidence(command.integrity_issue_min_confidence),
            integrity_notify_on_high_confidence=bool(command.integrity_notify_on_high_confidence),
            duplicate_reclaim_archive_root=self._validate_absolute_path(command.duplicate_reclaim_archive_root, "duplicate_reclaim_archive_root"),
            duplicate_reclaim_default_retention_days=self._validate_positive_int(
                command.duplicate_reclaim_default_retention_days,
                "duplicate_reclaim_default_retention_days",
            ),
            duplicate_reclaim_notify_on_reviewed_safe=bool(command.duplicate_reclaim_notify_on_reviewed_safe),
            integrity_quarantine_root=self._validate_absolute_path(command.integrity_quarantine_root, "integrity_quarantine_root"),
            integrity_quarantine_retention_days=self._validate_positive_int(
                command.integrity_quarantine_retention_days,
                "integrity_quarantine_retention_days",
            ),
            recycle_bin_root=self._validate_absolute_path(command.recycle_bin_root, "recycle_bin_root"),
            recycle_purge_days=self._validate_positive_int(command.recycle_purge_days, "recycle_purge_days"),
            automation_mode=self._validate_automation_mode(command.automation_mode),
            recanonicalization_enabled=bool(command.recanonicalization_enabled),
            version=int(command.version),
        )

    def _snapshot_from_row(self, row: OperatorPolicySetting) -> PolicySettingsSnapshot:
        return PolicySettingsSnapshot(
            selected_policy=row.selected_policy.strip().upper(),
            naming_strategy=(
                row.naming_strategy.value
                if isinstance(row.naming_strategy, NamingStrategyDB)
                else str(row.naming_strategy).strip().upper()
            ),
            preferred_roots=self._deserialize_roots(row.preferred_roots_json),
            integrity_scan_default_mode=str(row.integrity_scan_default_mode).strip().upper(),
            integrity_issue_min_confidence=float(row.integrity_issue_min_confidence),
            integrity_notify_on_high_confidence=bool(row.integrity_notify_on_high_confidence),
            duplicate_reclaim_archive_root=str(row.duplicate_reclaim_archive_root),
            duplicate_reclaim_default_retention_days=int(row.duplicate_reclaim_default_retention_days),
            duplicate_reclaim_notify_on_reviewed_safe=bool(row.duplicate_reclaim_notify_on_reviewed_safe),
            integrity_quarantine_root=str(row.integrity_quarantine_root),
            integrity_quarantine_retention_days=int(row.integrity_quarantine_retention_days),
            recycle_bin_root=str(row.recycle_bin_root),
            recycle_purge_days=int(row.recycle_purge_days),
            automation_mode=str(row.automation_mode).strip().upper(),
            recanonicalization_enabled=bool(row.recanonicalization_enabled),
            updated_at=row.updated_at,
            version=int(row.version),
        )

    def _default_snapshot(self) -> PolicySettingsSnapshot:
        selected_policy = resolve_default_policy_name()
        preferred_roots_env = os.getenv("MEDIA_PREFERRED_ROOTS", "")
        preferred_roots = tuple(item.strip() for item in preferred_roots_env.split(",") if item.strip())
        normalized = self._normalize_roots(preferred_roots)
        return PolicySettingsSnapshot(
            selected_policy=selected_policy,
            naming_strategy=NamingStrategyDB.SHARED_CANONICAL_NAME.value,
            preferred_roots=normalized,
            integrity_scan_default_mode=self._default_scan_mode(),
            integrity_issue_min_confidence=0.9,
            integrity_notify_on_high_confidence=True,
            duplicate_reclaim_archive_root=self._default_path("MEDIA_MANAGER_RECLAIM_ROOT", "/tmp/media-manager/reclaim"),
            duplicate_reclaim_default_retention_days=14,
            duplicate_reclaim_notify_on_reviewed_safe=True,
            integrity_quarantine_root=self._default_path("MEDIA_MANAGER_QUARANTINE_ROOT", "/tmp/media-manager/quarantine"),
            integrity_quarantine_retention_days=self._default_days("MEDIA_MANAGER_QUARANTINE_RETENTION_DAYS", 14),
            recycle_bin_root=self._default_path("MEDIA_MANAGER_RECYCLE_BIN_ROOT", "/tmp/media-manager/recycle-bin"),
            recycle_purge_days=self._default_days("MEDIA_MANAGER_RECYCLE_PURGE_DAYS", 30),
            automation_mode="NOTIFY_ONLY",
            recanonicalization_enabled=False,
            updated_at=datetime.fromtimestamp(0, tz=timezone.utc),
            version=0,
        )

    def _validate_naming_strategy(self, raw: str) -> str:
        try:
            return normalize_naming_strategy(raw)
        except ValueError as exc:
            raise PolicySettingsValidationError(str(exc)) from exc

    def _validate_scan_mode(self, raw: str) -> str:
        value = str(raw).strip().upper()
        if value not in {"FAST", "DEEP"}:
            raise PolicySettingsValidationError("integrity_scan_default_mode must be FAST or DEEP.")
        return value

    def _validate_confidence(self, raw: float) -> float:
        value = float(raw)
        if not 0.0 <= value <= 1.0:
            raise PolicySettingsValidationError("integrity_issue_min_confidence must be within [0.0, 1.0].")
        return round(value, 4)

    def _validate_positive_int(self, raw: int, field_name: str) -> int:
        value = int(raw)
        if value <= 0:
            raise PolicySettingsValidationError(f"{field_name} must be > 0.")
        return value

    def _validate_absolute_path(self, raw: str, field_name: str) -> str:
        value = str(raw).strip()
        if not value:
            raise PolicySettingsValidationError(f"{field_name} must not be empty.")
        if not Path(value).is_absolute():
            raise PolicySettingsValidationError(f"{field_name} must be an absolute path.")
        return value

    def _validate_automation_mode(self, raw: str) -> str:
        value = str(raw).strip().upper()
        if value != "NOTIFY_ONLY":
            raise PolicySettingsValidationError("automation_mode must be NOTIFY_ONLY.")
        return value

    def _normalize_roots(self, preferred_roots: tuple[str, ...]) -> tuple[str, ...]:
        values: set[str] = set()
        for raw in preferred_roots:
            if not isinstance(raw, str):
                raise PolicySettingsValidationError("preferred_roots must contain strings only.")
            cleaned = raw.strip()
            if cleaned:
                values.add(cleaned)
        return tuple(sorted(values))

    def _serialize_roots(self, preferred_roots: tuple[str, ...]) -> str:
        return json.dumps(list(preferred_roots), separators=(",", ":"), sort_keys=False)

    def _deserialize_roots(self, payload: str) -> tuple[str, ...]:
        try:
            decoded = json.loads(payload)
        except Exception:
            return ()
        if not isinstance(decoded, list):
            return ()
        values: list[str] = []
        for item in decoded:
            if isinstance(item, str):
                cleaned = item.strip()
                if cleaned:
                    values.append(cleaned)
        return tuple(sorted(set(values)))

    def _default_scan_mode(self) -> str:
        raw = (os.getenv("MEDIA_MANAGER_IMPORT_INTEGRITY_SCAN_MODE", "") or "").strip().upper()
        return raw if raw in {"FAST", "DEEP"} else "FAST"

    def _default_path(self, env_name: str, fallback: str) -> str:
        raw = (os.getenv(env_name, "") or "").strip()
        return raw if raw else fallback

    def _default_days(self, env_name: str, fallback: int) -> int:
        raw = (os.getenv(env_name, "") or "").strip()
        try:
            return max(1, int(raw)) if raw else fallback
        except ValueError:
            return fallback
