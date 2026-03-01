"""Persistence service for deterministic operator policy settings."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.canonical.factory import build_canonical_policy, resolve_default_policy_name
from media_manager.app.core.errors import PolicySettingsValidationError, PolicySettingsVersionConflictError
from media_manager.app.persistence.base import transactional_session
from media_manager.app.persistence.models import OperatorPolicySetting

_POLICY_ROW_ID = 1


@dataclass(frozen=True)
class PolicySettingsSnapshot:
    """Deterministic snapshot for operator policy settings."""

    selected_policy: str
    preferred_roots: tuple[str, ...]
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
    preferred_roots: tuple[str, ...]
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
                    preferred_roots_json=self._serialize_roots(validated.preferred_roots),
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
            row.preferred_roots_json = self._serialize_roots(validated.preferred_roots)
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
            preferred_roots=normalized_roots,
            recanonicalization_enabled=bool(command.recanonicalization_enabled),
            version=int(command.version),
        )

    def _snapshot_from_row(self, row: OperatorPolicySetting) -> PolicySettingsSnapshot:
        return PolicySettingsSnapshot(
            selected_policy=row.selected_policy.strip().upper(),
            preferred_roots=self._deserialize_roots(row.preferred_roots_json),
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
            preferred_roots=normalized,
            recanonicalization_enabled=False,
            updated_at=datetime.fromtimestamp(0, tz=timezone.utc),
            version=0,
        )

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
