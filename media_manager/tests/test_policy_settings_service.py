from __future__ import annotations

from sqlalchemy import select

from media_manager.app.core.errors import PolicySettingsValidationError, PolicySettingsVersionConflictError
from media_manager.app.persistence.models import OperatorPolicySetting
from media_manager.app.persistence.policy_settings import PolicySettingsService, UpdatePolicySettingsCommand


def test_get_settings_defaults_to_environment_when_row_missing(session_factory, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_CANONICAL_POLICY", "PREFER_ROOT")
    monkeypatch.setenv("MEDIA_PREFERRED_ROOTS", " /z , /a , /z ")
    service = PolicySettingsService(session_factory)

    snapshot = service.get_settings()

    assert snapshot.selected_policy == "PREFER_ROOT"
    assert snapshot.preferred_roots == ("/a", "/z")
    assert snapshot.recanonicalization_enabled is False
    assert snapshot.version == 0


def test_update_settings_persists_normalized_values(session_factory) -> None:
    service = PolicySettingsService(session_factory)

    created = service.update_settings(
        UpdatePolicySettingsCommand(
            selected_policy="prefer_root",
            preferred_roots=(" /mnt/b ", "/mnt/a", "/mnt/b"),
            recanonicalization_enabled=True,
            version=0,
        )
    )

    assert created.selected_policy == "PREFER_ROOT"
    assert created.preferred_roots == ("/mnt/a", "/mnt/b")
    assert created.recanonicalization_enabled is True
    assert created.version == 1

    with session_factory() as session:
        rows = session.scalars(select(OperatorPolicySetting)).all()
        assert len(rows) == 1
        assert rows[0].id == 1


def test_update_settings_rejects_unknown_policy(session_factory) -> None:
    service = PolicySettingsService(session_factory)

    try:
        service.update_settings(
            UpdatePolicySettingsCommand(
                selected_policy="UNKNOWN_POLICY",
                preferred_roots=(),
                recanonicalization_enabled=False,
                version=0,
            )
        )
    except PolicySettingsValidationError as exc:
        assert "Unknown canonical policy" in str(exc)
    else:
        raise AssertionError("Expected PolicySettingsValidationError")


def test_update_settings_rejects_stale_version(session_factory) -> None:
    service = PolicySettingsService(session_factory)

    service.update_settings(
        UpdatePolicySettingsCommand(
            selected_policy="FIRST_SEEN",
            preferred_roots=(),
            recanonicalization_enabled=False,
            version=0,
        )
    )

    try:
        service.update_settings(
            UpdatePolicySettingsCommand(
                selected_policy="SHORTEST_PATH",
                preferred_roots=(),
                recanonicalization_enabled=False,
                version=0,
            )
        )
    except PolicySettingsVersionConflictError as exc:
        assert "version conflict" in str(exc).lower()
    else:
        raise AssertionError("Expected PolicySettingsVersionConflictError")


def test_update_settings_idempotent_values_do_not_diverge(session_factory) -> None:
    service = PolicySettingsService(session_factory)

    first = service.update_settings(
        UpdatePolicySettingsCommand(
            selected_policy="SHORTEST_PATH",
            preferred_roots=("/a",),
            recanonicalization_enabled=False,
            version=0,
        )
    )

    second = service.update_settings(
        UpdatePolicySettingsCommand(
            selected_policy="SHORTEST_PATH",
            preferred_roots=("/a",),
            recanonicalization_enabled=False,
            version=first.version,
        )
    )

    assert second.selected_policy == first.selected_policy
    assert second.preferred_roots == first.preferred_roots
    assert second.recanonicalization_enabled == first.recanonicalization_enabled
    assert second.version == first.version + 1
