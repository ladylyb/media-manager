from __future__ import annotations

from sqlalchemy import select

from media_manager.app.core.errors import PolicySettingsValidationError, PolicySettingsVersionConflictError
from media_manager.app.persistence.models import OperatorPolicySetting
from media_manager.app.persistence.policy_settings import PolicySettingsService, UpdatePolicySettingsCommand


def _command(**overrides) -> UpdatePolicySettingsCommand:
    payload = {
        "selected_policy": "FIRST_SEEN",
        "naming_strategy": "SHARED_CANONICAL_NAME",
        "preferred_roots": (),
        "integrity_scan_default_mode": "FAST",
        "integrity_issue_min_confidence": 0.9,
        "integrity_notify_on_high_confidence": True,
        "duplicate_reclaim_archive_root": "/tmp/media-manager/reclaim",
        "duplicate_reclaim_default_retention_days": 14,
        "duplicate_reclaim_notify_on_reviewed_safe": True,
        "integrity_quarantine_root": "/tmp/media-manager/quarantine",
        "integrity_quarantine_retention_days": 14,
        "recycle_bin_root": "/tmp/media-manager/recycle-bin",
        "recycle_purge_days": 30,
        "automation_mode": "NOTIFY_ONLY",
        "recanonicalization_enabled": False,
        "version": 0,
    }
    payload.update(overrides)
    return UpdatePolicySettingsCommand(**payload)


def test_get_settings_defaults_to_environment_when_row_missing(session_factory, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_CANONICAL_POLICY", "PREFER_ROOT")
    monkeypatch.setenv("MEDIA_PREFERRED_ROOTS", " /z , /a , /z ")
    service = PolicySettingsService(session_factory)

    snapshot = service.get_settings()

    assert snapshot.selected_policy == "PREFER_ROOT"
    assert snapshot.naming_strategy == "SHARED_CANONICAL_NAME"
    assert snapshot.preferred_roots == ("/a", "/z")
    assert snapshot.integrity_scan_default_mode == "FAST"
    assert snapshot.duplicate_reclaim_archive_root == "/tmp/media-manager/reclaim"
    assert snapshot.recycle_bin_root == "/tmp/media-manager/recycle-bin"
    assert snapshot.automation_mode == "NOTIFY_ONLY"
    assert snapshot.recanonicalization_enabled is False
    assert snapshot.version == 0


def test_update_settings_persists_normalized_values(session_factory) -> None:
    service = PolicySettingsService(session_factory)

    created = service.update_settings(
        _command(
            selected_policy="prefer_root",
            naming_strategy="duplicate_owns_date_standardized",
            preferred_roots=(" /mnt/b ", "/mnt/a", "/mnt/b"),
            recanonicalization_enabled=True,
        )
    )

    assert created.selected_policy == "PREFER_ROOT"
    assert created.naming_strategy == "DUPLICATE_OWNS_DATE_STANDARDIZED"
    assert created.preferred_roots == ("/mnt/a", "/mnt/b")
    assert created.integrity_issue_min_confidence == 0.9
    assert created.recanonicalization_enabled is True
    assert created.version == 1

    with session_factory() as session:
        rows = session.scalars(select(OperatorPolicySetting)).all()
        assert len(rows) == 1
        assert rows[0].id == 1


def test_update_settings_accepts_exif_filename_fallback_policy(session_factory) -> None:
    service = PolicySettingsService(session_factory)

    created = service.update_settings(
        _command(
            selected_policy="exif_filename_fallback",
            naming_strategy="shared_canonical_name",
            preferred_roots=("/archive",),
        )
    )

    assert created.selected_policy == "EXIF_FILENAME_FALLBACK"


def test_update_settings_rejects_unknown_policy(session_factory) -> None:
    service = PolicySettingsService(session_factory)

    try:
        service.update_settings(
            _command(selected_policy="UNKNOWN_POLICY")
        )
    except PolicySettingsValidationError as exc:
        assert "Unknown canonical policy" in str(exc)
    else:
        raise AssertionError("Expected PolicySettingsValidationError")


def test_update_settings_rejects_stale_version(session_factory) -> None:
    service = PolicySettingsService(session_factory)

    service.update_settings(
        _command()
    )

    try:
        service.update_settings(
            _command(selected_policy="SHORTEST_PATH")
        )
    except PolicySettingsVersionConflictError as exc:
        assert "version conflict" in str(exc).lower()
    else:
        raise AssertionError("Expected PolicySettingsVersionConflictError")


def test_update_settings_idempotent_values_do_not_diverge(session_factory) -> None:
    service = PolicySettingsService(session_factory)

    first = service.update_settings(
        _command(selected_policy="SHORTEST_PATH", preferred_roots=("/a",))
    )

    second = service.update_settings(
        _command(selected_policy="SHORTEST_PATH", preferred_roots=("/a",), version=first.version)
    )

    assert second.selected_policy == first.selected_policy
    assert second.naming_strategy == first.naming_strategy
    assert second.preferred_roots == first.preferred_roots
    assert second.recanonicalization_enabled == first.recanonicalization_enabled
    assert second.version == first.version + 1


def test_update_settings_rejects_out_of_range_integrity_confidence(session_factory) -> None:
    service = PolicySettingsService(session_factory)

    try:
        service.update_settings(_command(integrity_issue_min_confidence=1.5))
    except PolicySettingsValidationError as exc:
        assert "integrity_issue_min_confidence" in str(exc)
    else:
        raise AssertionError("Expected PolicySettingsValidationError")


def test_update_settings_rejects_non_absolute_policy_paths(session_factory) -> None:
    service = PolicySettingsService(session_factory)

    try:
        service.update_settings(_command(recycle_bin_root="relative/path"))
    except PolicySettingsValidationError as exc:
        assert "recycle_bin_root" in str(exc)
    else:
        raise AssertionError("Expected PolicySettingsValidationError")
