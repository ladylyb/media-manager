from __future__ import annotations

from media_manager.app.persistence.base import create_db_engine, create_session_factory
from media_manager.app.service_layer.versioning import compute_phase_metadata, schema_version


def test_compute_phase_metadata_defaults_to_phase13(test_database_url: str, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    phase = compute_phase_metadata(session_factory)
    assert phase.code_supported_phase == "phase13"
    assert phase.db_schema_phase == "phase13"
    assert phase.last_successful_operational_phase == "phase13"
    assert phase.active_phase == "phase13"


def test_schema_version_returns_string(test_database_url: str, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    value = schema_version(session_factory)
    assert isinstance(value, str)
    assert len(value) > 0
