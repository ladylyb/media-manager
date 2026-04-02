from __future__ import annotations

import errno
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from media_manager.app.persistence.models import (
    CanonicalAssignment,
    DuplicateBinState,
    DuplicateReclaimItem,
    DuplicateReclaimItemStatus,
    DuplicateReclaimRecord,
    DuplicateReclaimStatus,
    FileContent,
    FileInstance,
    FileInstanceStatus,
)
from media_manager.app.persistence.phase3_actions import Phase3ActionService


def _add_content(session, content_id: UUID, sha256_hash: str, at: datetime, canonical_file_instance_id: UUID | None = None) -> None:
    session.add(
        FileContent(
            content_id=content_id,
            sha256_hash=sha256_hash,
            first_seen_at=at,
            canonical_file_instance_id=canonical_file_instance_id,
        )
    )


def _set_content_canonical_instance(session, *, content_id: UUID, canonical_file_instance_id: UUID) -> None:
    row = session.get(FileContent, content_id)
    assert row is not None
    row.canonical_file_instance_id = canonical_file_instance_id


def _add_instance(
    session,
    *,
    file_instance_id: UUID,
    content_id: UUID,
    absolute_path: str,
    first_seen_at: datetime,
    status: str = FileInstanceStatus.ACTIVE.value,
) -> None:
    session.add(
        FileInstance(
            file_instance_id=file_instance_id,
            content_id=content_id,
            absolute_path=absolute_path,
            filesystem_id="fs-1",
            first_seen_at=first_seen_at,
            last_seen_at=first_seen_at,
            status=status,
        )
    )


def _add_reclaim_record(session, *, content_id: UUID, at: datetime) -> None:
    session.add(
        DuplicateReclaimRecord(
            content_id=content_id,
            reclaim_status=DuplicateReclaimStatus.REVIEWED_SAFE_TO_RECLAIM.value,
            reviewed_at=at,
            reviewed_by="tester",
            archive_path=None,
            reclaimed_at=None,
            expires_at=None,
            restored_at=None,
            created_at=at,
            updated_at=at,
        )
    )


def test_execute_duplicate_reclaim_reports_zero_planned_when_file_content_canonical_mapping_missing(
    session_factory,
    monkeypatch,
    tmp_path: Path,
) -> None:
    reclaim_root = tmp_path / "reclaim-root"
    recycle_root = tmp_path / "recycle-bin-root"
    monkeypatch.setenv("MEDIA_MANAGER_RECLAIM_ROOT", str(reclaim_root))
    monkeypatch.setenv("MEDIA_MANAGER_RECYCLE_BIN_ROOT", str(recycle_root))
    service = Phase3ActionService(session_factory)
    base = datetime(2026, 3, 29, 10, 0, tzinfo=UTC)
    content_id = UUID("0135b1ed-4dc6-4a0d-88d5-81726006507c")
    canonical_instance = UUID("0135b1ed-4dc6-4a0d-88d5-817260065071")
    duplicate_instance = UUID("0135b1ed-4dc6-4a0d-88d5-817260065072")

    canonical_path = tmp_path / "library" / "main.jpg"
    duplicate_path = tmp_path / "library" / "copy.jpg"
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_path.write_bytes(b"main")
    duplicate_path.write_bytes(b"copy")

    with session_factory.begin() as session:
        _add_content(session, content_id, "hash-zero-planned", base)
        session.flush()
        _add_instance(
            session,
            file_instance_id=canonical_instance,
            content_id=content_id,
            absolute_path=str(canonical_path),
            first_seen_at=base,
        )
        _add_instance(
            session,
            file_instance_id=duplicate_instance,
            content_id=content_id,
            absolute_path=str(duplicate_path),
            first_seen_at=base + timedelta(seconds=1),
        )
        session.add(
            CanonicalAssignment(
                assignment_id=UUID("0135b1ed-4dc6-4a0d-88d5-817260065073"),
                content_id=content_id,
                canonical_instance_id=canonical_instance,
                policy_name="FIRST_SEEN",
                policy_version="v1",
                assigned_at=base + timedelta(seconds=2),
            )
        )
        _add_reclaim_record(session, content_id=content_id, at=base + timedelta(seconds=3))

    result = service.execute_duplicate_reclaim(content_ids=[content_id], retention_days=7)

    assert result["summary"]["applied_count"] == 0
    assert result["summary"]["skipped_count"] == 0
    assert result["diagnostics"]["planned_action_count"] == 0
    assert result["diagnostics"]["result_type"] == "zero_planned"
    assert result["diagnostics"]["reclaim_root"] == str(reclaim_root)
    assert result["diagnostics"]["current_move_root"] == str(recycle_root)
    assert result["diagnostics"]["group_results"] == [
        {
            "content_id": str(content_id),
            "reclaim_status": DuplicateReclaimStatus.REVIEWED_SAFE_TO_RECLAIM.value,
            "canonical_file_instance_id": None,
            "candidate_duplicate_file_instance_ids": [str(canonical_instance), str(duplicate_instance)],
            "planned": False,
            "reason": "missing_canonical_file_content_mapping",
        }
    ]
    assert duplicate_path.exists()
    assert not recycle_root.exists()


def test_execute_duplicate_reclaim_reports_planned_skipped_when_apply_cannot_move_source(
    session_factory,
    monkeypatch,
    tmp_path: Path,
) -> None:
    reclaim_root = tmp_path / "reclaim-root"
    recycle_root = tmp_path / "recycle-bin-root"
    monkeypatch.setenv("MEDIA_MANAGER_RECLAIM_ROOT", str(reclaim_root))
    monkeypatch.setenv("MEDIA_MANAGER_RECYCLE_BIN_ROOT", str(recycle_root))
    service = Phase3ActionService(session_factory)
    base = datetime(2026, 3, 29, 11, 0, tzinfo=UTC)
    content_id = UUID("1235b1ed-4dc6-4a0d-88d5-81726006507c")
    canonical_instance = UUID("1235b1ed-4dc6-4a0d-88d5-817260065071")
    duplicate_instance = UUID("1235b1ed-4dc6-4a0d-88d5-817260065072")

    canonical_path = tmp_path / "library" / "main.jpg"
    duplicate_path = tmp_path / "library" / "copy.jpg"
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_path.write_bytes(b"main")

    with session_factory.begin() as session:
        _add_content(session, content_id, "hash-skipped", base)
        session.flush()
        _add_instance(
            session,
            file_instance_id=canonical_instance,
            content_id=content_id,
            absolute_path=str(canonical_path),
            first_seen_at=base,
        )
        _add_instance(
            session,
            file_instance_id=duplicate_instance,
            content_id=content_id,
            absolute_path=str(duplicate_path),
            first_seen_at=base + timedelta(seconds=1),
        )
        session.flush()
        _set_content_canonical_instance(session, content_id=content_id, canonical_file_instance_id=canonical_instance)
        session.add(
            CanonicalAssignment(
                assignment_id=UUID("1235b1ed-4dc6-4a0d-88d5-817260065073"),
                content_id=content_id,
                canonical_instance_id=canonical_instance,
                policy_name="FIRST_SEEN",
                policy_version="v1",
                assigned_at=base + timedelta(seconds=2),
            )
        )
        _add_reclaim_record(session, content_id=content_id, at=base + timedelta(seconds=2))

    result = service.execute_duplicate_reclaim(content_ids=[content_id], retention_days=7)

    assert result["diagnostics"]["planned_action_count"] == 1
    assert result["diagnostics"]["result_type"] == "planned_skipped"
    assert result["summary"]["applied_count"] == 0
    assert result["summary"]["skipped_count"] == 1
    assert result["diagnostics"]["group_results"][0]["planned"] is True

    with session_factory() as session:
        item = session.get(DuplicateReclaimItem, duplicate_instance)
        record = session.get(DuplicateReclaimRecord, content_id)
        file_row = session.get(FileInstance, duplicate_instance)

        assert item is not None
        assert item.item_status == DuplicateReclaimItemStatus.PENDING.value
        assert item.planned_bin_path == str(recycle_root / "duplicates" / str(content_id) / f"{duplicate_instance}-{duplicate_path.name}")
        assert item.restore_expires_at == item.expires_at
        assert item.bin_path is None
        assert item.bin_entered_at is None
        assert item.bin_state == DuplicateBinState.PENDING_MOVE.value
        assert record is not None
        assert record.reclaim_status == DuplicateReclaimStatus.REVIEWED_SAFE_TO_RECLAIM.value
        assert file_row is not None
        assert file_row.absolute_path == str(duplicate_path)
    assert not recycle_root.exists()


def test_execute_duplicate_reclaim_moves_duplicate_and_persists_archived_state(
    session_factory,
    monkeypatch,
    tmp_path: Path,
) -> None:
    reclaim_root = tmp_path / "reclaim-root"
    recycle_root = tmp_path / "recycle-bin-root"
    monkeypatch.setenv("MEDIA_MANAGER_RECLAIM_ROOT", str(reclaim_root))
    monkeypatch.setenv("MEDIA_MANAGER_RECYCLE_BIN_ROOT", str(recycle_root))
    service = Phase3ActionService(session_factory)
    base = datetime(2026, 3, 29, 12, 0, tzinfo=UTC)
    content_id = UUID("2235b1ed-4dc6-4a0d-88d5-81726006507c")
    canonical_instance = UUID("2235b1ed-4dc6-4a0d-88d5-817260065071")
    duplicate_instance = UUID("2235b1ed-4dc6-4a0d-88d5-817260065072")

    canonical_path = tmp_path / "library" / "main.jpg"
    duplicate_path = tmp_path / "library" / "copy.jpg"
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_path.write_bytes(b"main")
    duplicate_path.write_bytes(b"copy")

    with session_factory.begin() as session:
        _add_content(session, content_id, "hash-applied", base)
        session.flush()
        _add_instance(
            session,
            file_instance_id=canonical_instance,
            content_id=content_id,
            absolute_path=str(canonical_path),
            first_seen_at=base,
        )
        _add_instance(
            session,
            file_instance_id=duplicate_instance,
            content_id=content_id,
            absolute_path=str(duplicate_path),
            first_seen_at=base + timedelta(seconds=1),
        )
        session.flush()
        _set_content_canonical_instance(session, content_id=content_id, canonical_file_instance_id=canonical_instance)
        session.add(
            CanonicalAssignment(
                assignment_id=UUID("2235b1ed-4dc6-4a0d-88d5-817260065073"),
                content_id=content_id,
                canonical_instance_id=canonical_instance,
                policy_name="FIRST_SEEN",
                policy_version="v1",
                assigned_at=base + timedelta(seconds=2),
            )
        )
        _add_reclaim_record(session, content_id=content_id, at=base + timedelta(seconds=2))

    result = service.execute_duplicate_reclaim(content_ids=[content_id], retention_days=7)
    target_path = recycle_root / "duplicates" / str(content_id) / f"{duplicate_instance}-{duplicate_path.name}"

    assert result["diagnostics"]["planned_action_count"] == 1
    assert result["diagnostics"]["applied_count"] == 1
    assert result["diagnostics"]["skipped_count"] == 0
    assert result["diagnostics"]["result_type"] == "applied"
    assert result["diagnostics"]["current_move_root"] == str(recycle_root)
    assert not duplicate_path.exists()
    assert target_path.exists()

    with session_factory() as session:
        item = session.get(DuplicateReclaimItem, duplicate_instance)
        record = session.get(DuplicateReclaimRecord, content_id)
        file_row = session.get(FileInstance, duplicate_instance)

        assert item is not None
        assert item.item_status == DuplicateReclaimItemStatus.ARCHIVED.value
        assert item.archive_path == str(target_path)
        assert item.planned_bin_path == str(target_path)
        assert item.bin_path == str(target_path)
        assert item.bin_entered_at is not None
        assert item.restore_expires_at == item.expires_at
        assert item.bin_state == DuplicateBinState.IN_BIN.value
        assert record is not None
        assert record.reclaim_status == DuplicateReclaimStatus.ARCHIVED.value
        assert record.archive_path == str(target_path)
        assert file_row is not None
        assert file_row.absolute_path == str(target_path)


def test_execute_duplicate_reclaim_and_restore_succeed_with_cross_device_fallback(
    session_factory,
    monkeypatch,
    tmp_path: Path,
) -> None:
    reclaim_root = tmp_path / "reclaim-root"
    recycle_root = tmp_path / "recycle-bin-root"
    monkeypatch.setenv("MEDIA_MANAGER_RECLAIM_ROOT", str(reclaim_root))
    monkeypatch.setenv("MEDIA_MANAGER_RECYCLE_BIN_ROOT", str(recycle_root))
    service = Phase3ActionService(session_factory)
    base = datetime(2026, 3, 29, 13, 0, tzinfo=UTC)
    content_id = UUID("3235b1ed-4dc6-4a0d-88d5-81726006507c")
    canonical_instance = UUID("3235b1ed-4dc6-4a0d-88d5-817260065071")
    duplicate_instance = UUID("3235b1ed-4dc6-4a0d-88d5-817260065072")

    canonical_path = tmp_path / "library" / "main.jpg"
    duplicate_path = tmp_path / "library" / "copy.jpg"
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_path.write_bytes(b"main")
    duplicate_path.write_bytes(b"copy")

    with session_factory.begin() as session:
        _add_content(session, content_id, "hash-cross-device", base)
        session.flush()
        _add_instance(
            session,
            file_instance_id=canonical_instance,
            content_id=content_id,
            absolute_path=str(canonical_path),
            first_seen_at=base,
        )
        _add_instance(
            session,
            file_instance_id=duplicate_instance,
            content_id=content_id,
            absolute_path=str(duplicate_path),
            first_seen_at=base + timedelta(seconds=1),
        )
        session.flush()
        _set_content_canonical_instance(session, content_id=content_id, canonical_file_instance_id=canonical_instance)
        session.add(
            CanonicalAssignment(
                assignment_id=UUID("3235b1ed-4dc6-4a0d-88d5-817260065073"),
                content_id=content_id,
                canonical_instance_id=canonical_instance,
                policy_name="FIRST_SEEN",
                policy_version="v1",
                assigned_at=base + timedelta(seconds=2),
            )
        )
        _add_reclaim_record(session, content_id=content_id, at=base + timedelta(seconds=2))

    original_rename = Path.rename

    def raise_cross_device(path_obj: Path, target):  # type: ignore[no-untyped-def]
        target_path = Path(target)
        if str(path_obj) in {str(duplicate_path), str(recycle_root / "duplicates" / str(content_id) / f"{duplicate_instance}-{duplicate_path.name}")}:
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        return original_rename(path_obj, target_path)

    monkeypatch.setattr(Path, "rename", raise_cross_device)

    archive_result = service.execute_duplicate_reclaim(content_ids=[content_id], retention_days=7)
    archive_target = recycle_root / "duplicates" / str(content_id) / f"{duplicate_instance}-{duplicate_path.name}"

    assert archive_result["diagnostics"]["result_type"] == "applied"
    assert archive_result["summary"]["applied_count"] == 1
    assert not duplicate_path.exists()
    assert archive_target.exists()

    restore_result = service.restore_duplicate_reclaim(file_instance_ids=[duplicate_instance])

    assert restore_result["summary"]["applied_count"] == 1
    assert duplicate_path.exists()
    assert not archive_target.exists()

    with session_factory() as session:
        item = session.get(DuplicateReclaimItem, duplicate_instance)
        record = session.get(DuplicateReclaimRecord, content_id)
        file_row = session.get(FileInstance, duplicate_instance)

        assert item is not None
        assert item.item_status == DuplicateReclaimItemStatus.RESTORED.value
        assert item.planned_bin_path == str(archive_target)
        assert item.bin_path == str(archive_target)
        assert item.bin_state == DuplicateBinState.IN_BIN.value
        assert record is not None
        assert record.reclaim_status == DuplicateReclaimStatus.RESTORED.value
        assert file_row is not None
        assert file_row.absolute_path == str(duplicate_path)


def test_recycle_duplicate_reclaim_transitions_bin_root_items_without_second_move(
    session_factory,
    monkeypatch,
    tmp_path: Path,
) -> None:
    reclaim_root = tmp_path / "reclaim-root"
    recycle_root = tmp_path / "recycle-bin-root"
    monkeypatch.setenv("MEDIA_MANAGER_RECLAIM_ROOT", str(reclaim_root))
    monkeypatch.setenv("MEDIA_MANAGER_RECYCLE_BIN_ROOT", str(recycle_root))
    service = Phase3ActionService(session_factory)
    base = datetime(2026, 3, 29, 14, 0, tzinfo=UTC)
    content_id = UUID("4235b1ed-4dc6-4a0d-88d5-81726006507c")
    canonical_instance = UUID("4235b1ed-4dc6-4a0d-88d5-817260065071")
    duplicate_instance = UUID("4235b1ed-4dc6-4a0d-88d5-817260065072")

    original_path = tmp_path / "library" / "copy.jpg"
    archive_path = recycle_root / "duplicates" / str(content_id) / f"{duplicate_instance}-copy.jpg"
    original_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_bytes(b"copy")

    with session_factory.begin() as session:
        _add_content(session, content_id, "hash-recycle", base)
        session.flush()
        _add_instance(
            session,
            file_instance_id=canonical_instance,
            content_id=content_id,
            absolute_path=str(tmp_path / "library" / "main.jpg"),
            first_seen_at=base,
        )
        _add_instance(
            session,
            file_instance_id=duplicate_instance,
            content_id=content_id,
            absolute_path=str(archive_path),
            first_seen_at=base + timedelta(seconds=1),
        )
        session.flush()
        _set_content_canonical_instance(
            session,
            content_id=content_id,
            canonical_file_instance_id=canonical_instance,
        )
        session.add(
            DuplicateReclaimRecord(
                content_id=content_id,
                reclaim_status=DuplicateReclaimStatus.ARCHIVED.value,
                reviewed_at=base,
                reviewed_by="tester",
                archive_path=str(archive_path),
                reclaimed_at=base,
                expires_at=base - timedelta(days=1),
                restored_at=None,
                created_at=base,
                updated_at=base,
            )
        )
        session.add(
            DuplicateReclaimItem(
                file_instance_id=duplicate_instance,
                content_id=content_id,
                original_path=str(original_path),
                archive_path=str(archive_path),
                item_status=DuplicateReclaimItemStatus.ARCHIVED.value,
                reclaimed_at=base,
                expires_at=base - timedelta(days=1),
                recycle_path=None,
                recycled_at=None,
                purge_after_at=None,
                purged_at=None,
                restored_at=None,
                created_at=base,
                updated_at=base,
            )
        )

    result = service.recycle_duplicate_reclaim(file_instance_ids=[duplicate_instance])

    assert result["summary"]["applied_count"] == 1
    assert archive_path.exists()

    with session_factory() as session:
        item = session.get(DuplicateReclaimItem, duplicate_instance)
        record = session.get(DuplicateReclaimRecord, content_id)
        file_row = session.get(FileInstance, duplicate_instance)

        assert item is not None
        assert item.item_status == DuplicateReclaimItemStatus.RECYCLED.value
        assert item.recycle_path == str(archive_path)
        assert item.recycled_at is not None
        assert item.purge_after_at is not None
        assert record is not None
        assert record.reclaim_status == DuplicateReclaimStatus.SCHEDULED_FOR_DELETE.value
        assert record.archive_path == str(archive_path)
        assert file_row is not None
        assert file_row.absolute_path == str(archive_path)


def test_plan_duplicate_reclaim_populates_bin_native_pending_fields(session_factory, monkeypatch, tmp_path: Path) -> None:
    reclaim_root = tmp_path / "reclaim-root"
    recycle_root = tmp_path / "recycle-bin-root"
    monkeypatch.setenv("MEDIA_MANAGER_RECLAIM_ROOT", str(reclaim_root))
    monkeypatch.setenv("MEDIA_MANAGER_RECYCLE_BIN_ROOT", str(recycle_root))
    service = Phase3ActionService(session_factory)
    base = datetime(2026, 3, 29, 15, 0, tzinfo=UTC)
    content_id = UUID("5235b1ed-4dc6-4a0d-88d5-81726006507c")
    canonical_instance = UUID("5235b1ed-4dc6-4a0d-88d5-817260065071")
    duplicate_instance = UUID("5235b1ed-4dc6-4a0d-88d5-817260065072")

    canonical_path = tmp_path / "library" / "main.jpg"
    duplicate_path = tmp_path / "library" / "copy.jpg"
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_path.write_bytes(b"main")
    duplicate_path.write_bytes(b"copy")

    with session_factory.begin() as session:
        _add_content(session, content_id, "hash-plan-only", base)
        session.flush()
        _add_instance(
            session,
            file_instance_id=canonical_instance,
            content_id=content_id,
            absolute_path=str(canonical_path),
            first_seen_at=base,
        )
        _add_instance(
            session,
            file_instance_id=duplicate_instance,
            content_id=content_id,
            absolute_path=str(duplicate_path),
            first_seen_at=base + timedelta(seconds=1),
        )
        session.flush()
        _set_content_canonical_instance(session, content_id=content_id, canonical_file_instance_id=canonical_instance)
        session.add(
            CanonicalAssignment(
                assignment_id=UUID("5235b1ed-4dc6-4a0d-88d5-817260065073"),
                content_id=content_id,
                canonical_instance_id=canonical_instance,
                policy_name="FIRST_SEEN",
                policy_version="v1",
                assigned_at=base + timedelta(seconds=2),
            )
        )
        _add_reclaim_record(session, content_id=content_id, at=base + timedelta(seconds=2))

    result = service._plan_duplicate_reclaim(content_ids=[content_id], retention_days=7)

    assert result["diagnostics"]["planned_action_count"] == 1
    with session_factory() as session:
        item = session.get(DuplicateReclaimItem, duplicate_instance)
        assert item is not None
        expected_path = str(recycle_root / "duplicates" / str(content_id) / f"{duplicate_instance}-{duplicate_path.name}")
        assert item.archive_path == expected_path
        assert item.planned_bin_path == expected_path
        assert item.restore_expires_at == item.expires_at
        assert item.bin_path is None
        assert item.bin_entered_at is None
        assert item.bin_state == DuplicateBinState.PENDING_MOVE.value
        assert item.item_status == DuplicateReclaimItemStatus.PENDING.value


def test_execute_duplicate_reclaim_remains_idempotent_for_bin_native_fields(session_factory, monkeypatch, tmp_path: Path) -> None:
    reclaim_root = tmp_path / "reclaim-root"
    recycle_root = tmp_path / "recycle-bin-root"
    monkeypatch.setenv("MEDIA_MANAGER_RECLAIM_ROOT", str(reclaim_root))
    monkeypatch.setenv("MEDIA_MANAGER_RECYCLE_BIN_ROOT", str(recycle_root))
    service = Phase3ActionService(session_factory)
    base = datetime(2026, 3, 29, 16, 0, tzinfo=UTC)
    content_id = UUID("6235b1ed-4dc6-4a0d-88d5-81726006507c")
    canonical_instance = UUID("6235b1ed-4dc6-4a0d-88d5-817260065071")
    duplicate_instance = UUID("6235b1ed-4dc6-4a0d-88d5-817260065072")

    canonical_path = tmp_path / "library" / "main.jpg"
    duplicate_path = tmp_path / "library" / "copy.jpg"
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_path.write_bytes(b"main")
    duplicate_path.write_bytes(b"copy")

    with session_factory.begin() as session:
        _add_content(session, content_id, "hash-idempotent", base)
        session.flush()
        _add_instance(
            session,
            file_instance_id=canonical_instance,
            content_id=content_id,
            absolute_path=str(canonical_path),
            first_seen_at=base,
        )
        _add_instance(
            session,
            file_instance_id=duplicate_instance,
            content_id=content_id,
            absolute_path=str(duplicate_path),
            first_seen_at=base + timedelta(seconds=1),
        )
        session.flush()
        _set_content_canonical_instance(session, content_id=content_id, canonical_file_instance_id=canonical_instance)
        session.add(
            CanonicalAssignment(
                assignment_id=UUID("6235b1ed-4dc6-4a0d-88d5-817260065073"),
                content_id=content_id,
                canonical_instance_id=canonical_instance,
                policy_name="FIRST_SEEN",
                policy_version="v1",
                assigned_at=base + timedelta(seconds=2),
            )
        )
        _add_reclaim_record(session, content_id=content_id, at=base + timedelta(seconds=2))

    first_result = service.execute_duplicate_reclaim(content_ids=[content_id], retention_days=7)
    second_result = service.execute_duplicate_reclaim(content_ids=[content_id], retention_days=7)

    assert first_result["summary"]["applied_count"] == 1
    assert second_result["diagnostics"]["planned_action_count"] == 0
    assert second_result["summary"]["applied_count"] == 0

    with session_factory() as session:
        item = session.get(DuplicateReclaimItem, duplicate_instance)
        assert item is not None
        expected_path = str(recycle_root / "duplicates" / str(content_id) / f"{duplicate_instance}-{duplicate_path.name}")
        assert item.archive_path == expected_path
        assert item.planned_bin_path == expected_path
        assert item.bin_path == expected_path
        assert item.bin_entered_at is not None
        assert item.restore_expires_at == item.expires_at
        assert item.bin_state == DuplicateBinState.IN_BIN.value
        assert item.item_status == DuplicateReclaimItemStatus.ARCHIVED.value


def test_restore_duplicate_reclaim_still_uses_legacy_archive_path_without_bin_native_fields(
    session_factory,
    monkeypatch,
    tmp_path: Path,
) -> None:
    reclaim_root = tmp_path / "reclaim-root"
    recycle_root = tmp_path / "recycle-bin-root"
    monkeypatch.setenv("MEDIA_MANAGER_RECLAIM_ROOT", str(reclaim_root))
    monkeypatch.setenv("MEDIA_MANAGER_RECYCLE_BIN_ROOT", str(recycle_root))
    service = Phase3ActionService(session_factory)
    base = datetime(2026, 3, 29, 17, 0, tzinfo=UTC)
    content_id = UUID("7235b1ed-4dc6-4a0d-88d5-81726006507c")
    canonical_instance = UUID("7235b1ed-4dc6-4a0d-88d5-817260065071")
    duplicate_instance = UUID("7235b1ed-4dc6-4a0d-88d5-817260065072")

    original_path = tmp_path / "library" / "copy.jpg"
    archive_path = recycle_root / "duplicates" / str(content_id) / f"{duplicate_instance}-copy.jpg"
    original_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_bytes(b"copy")

    with session_factory.begin() as session:
        _add_content(session, content_id, "hash-legacy-restore", base)
        session.flush()
        _add_instance(
            session,
            file_instance_id=canonical_instance,
            content_id=content_id,
            absolute_path=str(tmp_path / "library" / "main.jpg"),
            first_seen_at=base,
        )
        _add_instance(
            session,
            file_instance_id=duplicate_instance,
            content_id=content_id,
            absolute_path=str(archive_path),
            first_seen_at=base + timedelta(seconds=1),
        )
        _set_content_canonical_instance(session, content_id=content_id, canonical_file_instance_id=canonical_instance)
        session.add(
            DuplicateReclaimRecord(
                content_id=content_id,
                reclaim_status=DuplicateReclaimStatus.ARCHIVED.value,
                reviewed_at=base,
                reviewed_by="tester",
                archive_path=str(archive_path),
                reclaimed_at=base,
                expires_at=base + timedelta(days=7),
                restored_at=None,
                created_at=base,
                updated_at=base,
            )
        )
        session.add(
            DuplicateReclaimItem(
                file_instance_id=duplicate_instance,
                content_id=content_id,
                original_path=str(original_path),
                archive_path=str(archive_path),
                planned_bin_path=None,
                bin_path=None,
                item_status=DuplicateReclaimItemStatus.ARCHIVED.value,
                reclaimed_at=base,
                bin_entered_at=None,
                expires_at=base + timedelta(days=7),
                restore_expires_at=None,
                bin_state=None,
                recycle_path=None,
                recycled_at=None,
                purge_after_at=None,
                purged_at=None,
                restored_at=None,
                created_at=base,
                updated_at=base,
            )
        )

    result = service.restore_duplicate_reclaim(file_instance_ids=[duplicate_instance])

    assert result["summary"]["applied_count"] == 1
    assert original_path.exists()
    assert not archive_path.exists()

    with session_factory() as session:
        item = session.get(DuplicateReclaimItem, duplicate_instance)
        assert item is not None
        assert item.item_status == DuplicateReclaimItemStatus.RESTORED.value
        assert item.bin_path is None
        assert item.bin_state is None
