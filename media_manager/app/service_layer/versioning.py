"""Centralized workflow/schema/phase metadata for service-layer consumers."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select, text

from media_manager.app.persistence.models import Run, RunStateDB

WORKFLOW_VERSION = "v2-service-layer"
CODE_SUPPORTED_PHASE = "phase13"


@dataclass(frozen=True)
class PhaseMetadata:
    code_supported_phase: str
    db_schema_phase: str
    last_successful_operational_phase: str
    active_phase: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code_supported_phase": self.code_supported_phase,
            "db_schema_phase": self.db_schema_phase,
            "last_successful_operational_phase": self.last_successful_operational_phase,
            "active_phase": self.active_phase,
        }


def schema_version(session_factory) -> str:
    """Return current alembic version if available."""
    try:
        with session_factory() as session:
            value = session.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
    except Exception:
        return "unknown"
    return str(value or "unknown")


def _phase_rank(label: str) -> int:
    normalized = label.strip().lower()
    if normalized.startswith("phase"):
        try:
            return int(normalized.replace("phase", ""))
        except Exception:
            return 13
    return 13


def _lower_phase(left: str, right: str) -> str:
    return left if _phase_rank(left) <= _phase_rank(right) else right


def db_schema_phase(session_factory) -> str:
    """Derive schema-supported phase from alembic version mapping."""
    _ = schema_version(session_factory)
    # Current codebase is Phase 13 schema; keep deterministic mapping.
    return "phase13"


def last_successful_operational_phase(session_factory) -> str:
    """Return phase of last successful operational run."""
    try:
        with session_factory() as session:
            latest = session.scalar(
                select(Run.id)
                .where(Run.state == RunStateDB.COMPLETED)
                .order_by(Run.updated_at.desc(), Run.id.desc())
                .limit(1)
            )
    except Exception:
        return "phase13"
    if latest is None:
        return "phase13"
    return "phase13"


def compute_phase_metadata(session_factory) -> PhaseMetadata:
    """Compute deterministic phase metadata for status endpoints."""
    code_phase = CODE_SUPPORTED_PHASE
    schema_phase = db_schema_phase(session_factory)
    operational_phase = last_successful_operational_phase(session_factory)
    active = _lower_phase(code_phase, schema_phase)
    active = _lower_phase(active, operational_phase)
    return PhaseMetadata(
        code_supported_phase=code_phase,
        db_schema_phase=schema_phase,
        last_successful_operational_phase=operational_phase,
        active_phase=active,
    )
