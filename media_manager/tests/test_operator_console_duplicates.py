from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from media_manager.app.persistence.models import (
    CanonicalAssignment,
    DuplicateBinState,
    DuplicateGroupReview,
    DuplicateReclaimItem,
    DuplicateReclaimRecord,
    DuplicateReclaimStatus,
    FileContent,
    FileInstance,
    FileInstanceStatus,
    IntegrityCheck,
    IntegrityCheckRun,
)
from media_manager.app.persistence.operator_console import OperatorConsoleReadService


def _add_content(session, content_id: UUID, sha256_hash: str, at: datetime) -> None:
    session.add(FileContent(content_id=content_id, sha256_hash=sha256_hash, first_seen_at=at))


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


def _add_integrity_check(
    session,
    *,
    check_id: UUID,
    file_instance_id: UUID,
    status: str,
    at: datetime,
    absolute_path: str,
) -> None:
    run_id = UUID(str(check_id))
    session.add(
        IntegrityCheckRun(
            id=run_id,
            operation_run_id=None,
            scan_mode="FAST",
            status="COMPLETED",
            paths=[absolute_path],
            scanned_count=1,
            issues_found=0 if status == "OK" else 1,
            started_at=at,
            completed_at=at,
            error_message=None,
            created_at=at,
            updated_at=at,
        )
    )
    session.add(
        IntegrityCheck(
            id=check_id,
            latest_run_id=run_id,
            file_instance_id=file_instance_id,
            status=status,
            confidence=0.95,
            readability_ok=status == "OK",
            probe_status="ok",
            decode_status="ok" if status == "OK" else "failed",
            last_completed_scan_mode="FAST",
            last_scanned_absolute_path=absolute_path,
            last_checked_at=at,
            created_at=at,
            updated_at=at,
        )
    )


def test_get_duplicate_groups_orders_groups_and_files_deterministically(session_factory, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_MANAGER_VIDEO_THUMBNAILS_ENABLED", "true")
    service = OperatorConsoleReadService(session_factory)
    base = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)

    content_a = UUID("11111111-1111-1111-1111-111111111111")
    content_b = UUID("22222222-2222-2222-2222-222222222222")
    content_c = UUID("33333333-3333-3333-3333-333333333333")

    a2 = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa2")
    a1 = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1")
    a3 = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa3")
    b1 = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1")
    b2 = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb2")

    with session_factory.begin() as session:
        _add_content(session, content_a, "hash-a", base)
        _add_content(session, content_b, "hash-b", base)
        _add_content(session, content_c, "hash-c", base)
        session.flush()

        _add_instance(
            session,
            file_instance_id=a2,
            content_id=content_a,
            absolute_path="/media/b.jpg",
            first_seen_at=base + timedelta(seconds=5),
        )
        _add_instance(
            session,
            file_instance_id=a1,
            content_id=content_a,
            absolute_path="/media/a.jpg",
            first_seen_at=base,
        )
        _add_instance(
            session,
            file_instance_id=a3,
            content_id=content_a,
            absolute_path="/media/c.mov",
            first_seen_at=base + timedelta(seconds=5),
        )

        _add_instance(
            session,
            file_instance_id=b2,
            content_id=content_b,
            absolute_path="/other/z.png",
            first_seen_at=base + timedelta(seconds=1),
        )
        _add_instance(
            session,
            file_instance_id=b1,
            content_id=content_b,
            absolute_path="/other/y.png",
            first_seen_at=base,
        )

        _add_instance(
            session,
            file_instance_id=UUID("cccccccc-cccc-cccc-cccc-ccccccccccc1"),
            content_id=content_c,
            absolute_path="/single/one.jpg",
            first_seen_at=base,
        )
        _add_instance(
            session,
            file_instance_id=UUID("cccccccc-cccc-cccc-cccc-ccccccccccc2"),
            content_id=content_c,
            absolute_path="/single/two.jpg",
            first_seen_at=base,
            status=FileInstanceStatus.DELETED.value,
        )

        session.add(
            CanonicalAssignment(
                assignment_id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
                content_id=content_a,
                canonical_instance_id=a1,
                policy_name="FIRST_SEEN",
                policy_version="v1",
                assigned_at=base + timedelta(seconds=8),
            )
        )

    groups = service.get_duplicate_groups()

    assert [g.group_id for g in groups] == [str(content_a), str(content_b)]
    assert [f.file_instance_id for f in groups[0].files] == [str(a1), str(a2), str(a3)]
    assert [f.file_instance_id for f in groups[1].files] == [str(b1), str(b2)]
    assert groups[0].canonical_file is not None
    assert groups[0].canonical_file.file_instance_id == str(a1)
    assert groups[1].canonical_file is None
    assert groups[0].files[0].media_type == "IMG"
    assert groups[0].files[2].media_type == "VID"
    assert groups[0].files[0].preview_url == f"/api/thumbnail/{a1}"
    assert groups[0].files[0].thumbnail_url == f"/api/thumbnail/{a1}"
    assert groups[0].files[2].preview_url == f"/api/video-thumbnail/{a3}"
    assert groups[0].files[2].thumbnail_url is None
    assert groups[0].files[0].role == "CANONICAL"
    assert groups[0].files[1].role == "DUPLICATE"
    assert groups[0].files[1].duplicate_index == 1
    assert groups[0].files[2].duplicate_index == 2


def test_get_duplicate_groups_video_preview_absent_when_video_thumbnails_disabled(session_factory, monkeypatch) -> None:
    monkeypatch.delenv("MEDIA_MANAGER_VIDEO_THUMBNAILS_ENABLED", raising=False)
    service = OperatorConsoleReadService(session_factory)
    base = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)

    content_id = UUID("99999999-9999-9999-9999-999999999999")
    a1 = UUID("ffffffff-ffff-ffff-ffff-fffffffffff1")
    a2 = UUID("ffffffff-ffff-ffff-ffff-fffffffffff2")

    with session_factory.begin() as session:
        _add_content(session, content_id, "hash-video", base)
        session.flush()
        _add_instance(
            session,
            file_instance_id=a1,
            content_id=content_id,
            absolute_path="/media/one.mov",
            first_seen_at=base,
        )
        _add_instance(
            session,
            file_instance_id=a2,
            content_id=content_id,
            absolute_path="/media/two.mov",
            first_seen_at=base + timedelta(seconds=1),
        )

    groups = service.get_duplicate_groups()

    assert len(groups) == 1
    assert all(file.preview_url is None for file in groups[0].files)


def test_get_duplicate_groups_canonical_null_when_latest_assignment_not_active(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    base = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    content_id = UUID("44444444-4444-4444-4444-444444444444")
    active_instance = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeee1")
    deleted_instance = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeee2")

    with session_factory.begin() as session:
        _add_content(session, content_id, "hash-d", base)
        session.flush()
        _add_instance(
            session,
            file_instance_id=active_instance,
            content_id=content_id,
            absolute_path="/dupes/live.jpg",
            first_seen_at=base,
        )
        _add_instance(
            session,
            file_instance_id=UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeee3"),
            content_id=content_id,
            absolute_path="/dupes/live2.jpg",
            first_seen_at=base + timedelta(seconds=1),
        )
        _add_instance(
            session,
            file_instance_id=deleted_instance,
            content_id=content_id,
            absolute_path="/dupes/deleted.jpg",
            first_seen_at=base + timedelta(seconds=2),
            status=FileInstanceStatus.DELETED.value,
        )

        session.add(
            CanonicalAssignment(
                assignment_id=UUID("ffffffff-ffff-ffff-ffff-fffffffffff1"),
                content_id=content_id,
                canonical_instance_id=active_instance,
                policy_name="FIRST_SEEN",
                policy_version="v1",
                assigned_at=base,
            )
        )
        session.add(
            CanonicalAssignment(
                assignment_id=UUID("ffffffff-ffff-ffff-ffff-fffffffffff2"),
                content_id=content_id,
                canonical_instance_id=deleted_instance,
                policy_name="FIRST_SEEN",
                policy_version="v2",
                assigned_at=base + timedelta(seconds=3),
            )
        )

    groups = service.get_duplicate_groups()

    assert len(groups) == 1
    assert groups[0].canonical_file is None


def test_get_duplicate_groups_limit_applies(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    now = datetime(2026, 3, 1, 13, 0, tzinfo=UTC)

    with session_factory.begin() as session:
        for idx in range(3):
            content_id = UUID(f"70000000-0000-0000-0000-00000000000{idx}")
            _add_content(session, content_id, f"hash-{idx}", now)
            session.flush()
            _add_instance(
                session,
                file_instance_id=UUID(f"71000000-0000-0000-0000-00000000000{idx}"),
                content_id=content_id,
                absolute_path=f"/limit/{idx}/a.jpg",
                first_seen_at=now,
            )
            _add_instance(
                session,
                file_instance_id=UUID(f"72000000-0000-0000-0000-00000000000{idx}"),
                content_id=content_id,
                absolute_path=f"/limit/{idx}/b.jpg",
                first_seen_at=now + timedelta(seconds=1),
            )

    groups = service.get_duplicate_groups(limit=2)

    assert len(groups) == 2


def test_get_duplicate_groups_exposes_duplicate_reclaim_actionable_false_when_file_content_canonical_missing(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    base = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)
    content_id = UUID("55555555-5555-5555-5555-555555555555")
    canonical_instance = UUID("55555555-5555-5555-5555-555555555556")
    duplicate_instance = UUID("55555555-5555-5555-5555-555555555557")

    with session_factory.begin() as session:
        _add_content(session, content_id, "hash-reclaim", base)
        session.flush()
        _add_instance(
            session,
            file_instance_id=canonical_instance,
            content_id=content_id,
            absolute_path="/dupes/reclaim/canonical.jpg",
            first_seen_at=base,
        )
        _add_instance(
            session,
            file_instance_id=duplicate_instance,
            content_id=content_id,
            absolute_path="/dupes/reclaim/duplicate.jpg",
            first_seen_at=base + timedelta(seconds=1),
        )
        session.add(
            CanonicalAssignment(
                assignment_id=UUID("55555555-5555-5555-5555-555555555558"),
                content_id=content_id,
                canonical_instance_id=canonical_instance,
                policy_name="FIRST_SEEN",
                policy_version="v1",
                assigned_at=base + timedelta(seconds=2),
            )
        )
        session.add(
            DuplicateReclaimRecord(
                content_id=content_id,
                reclaim_status=DuplicateReclaimStatus.REVIEWED_SAFE_TO_RECLAIM.value,
                reviewed_at=base + timedelta(seconds=3),
                reviewed_by="tester",
                restored_at=None,
                created_at=base + timedelta(seconds=3),
                updated_at=base + timedelta(seconds=3),
            )
        )

    groups = service.get_duplicate_groups()

    assert len(groups) == 1
    assert groups[0].canonical_file is not None
    assert groups[0].duplicate_reclaim_actionable is False
    assert groups[0].duplicate_reclaim_unavailable_reason == "missing_canonical_file_content_mapping"


def test_get_duplicate_groups_include_duplicate_recommendation_contract(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    base = datetime(2026, 3, 2, 11, 0, tzinfo=UTC)
    content_id = UUID("56565656-5555-5555-5555-555555555555")
    canonical_instance = UUID("56565656-5555-5555-5555-555555555556")
    duplicate_a = UUID("56565656-5555-5555-5555-555555555557")
    duplicate_b = UUID("56565656-5555-5555-5555-555555555558")

    with session_factory.begin() as session:
        _add_content(session, content_id, "hash-recommendation", base)
        session.flush()
        _add_instance(
            session,
            file_instance_id=canonical_instance,
            content_id=content_id,
            absolute_path="/dupes/recommendation/canonical.jpg",
            first_seen_at=base,
        )
        _add_instance(
            session,
            file_instance_id=duplicate_a,
            content_id=content_id,
            absolute_path="/dupes/recommendation/copy-a.jpg",
            first_seen_at=base + timedelta(seconds=1),
        )
        _add_instance(
            session,
            file_instance_id=duplicate_b,
            content_id=content_id,
            absolute_path="/dupes/recommendation/copy-b.jpg",
            first_seen_at=base + timedelta(seconds=2),
        )
        session.flush()
        session.get(FileContent, content_id).canonical_file_instance_id = canonical_instance
        session.add(
            CanonicalAssignment(
                assignment_id=UUID("56565656-dddd-dddd-dddd-555555555557"),
                content_id=content_id,
                canonical_instance_id=canonical_instance,
                policy_name="FIRST_SEEN",
                policy_version="v1",
                assigned_at=base + timedelta(seconds=3),
            )
        )
        session.add(
            DuplicateGroupReview(
                content_id=content_id,
                review_status="looks_right",
                reviewed_at=base,
                reviewed_by="tester",
                reviewed_canonical_instance_id=canonical_instance,
                group_signature="stale-signature-on-purpose",
                created_at=base,
                updated_at=base,
            )
        )
        _add_integrity_check(
            session,
            check_id=UUID("56565656-aaaa-aaaa-aaaa-555555555557"),
            file_instance_id=canonical_instance,
            status="OK",
            at=base,
            absolute_path="/dupes/recommendation/canonical.jpg",
        )
        _add_integrity_check(
            session,
            check_id=UUID("56565656-bbbb-bbbb-bbbb-555555555557"),
            file_instance_id=duplicate_a,
            status="BROKEN",
            at=base,
            absolute_path="/dupes/recommendation/copy-a.jpg",
        )
        _add_integrity_check(
            session,
            check_id=UUID("56565656-cccc-cccc-cccc-555555555557"),
            file_instance_id=duplicate_b,
            status="SUSPECT",
            at=base,
            absolute_path="/dupes/recommendation/copy-b.jpg",
        )

    groups = service.get_duplicate_groups()

    assert len(groups) == 1
    recommendation = groups[0].duplicate_recommendation
    assert recommendation is not None
    assert recommendation.state == "REVIEW_REQUIRED"
    assert recommendation.classification == "WARN"
    assert recommendation.primary_reason_code == "REVIEW_STALE"
    assert recommendation.reason_codes == ("REVIEW_STALE",)
    assert recommendation.review_is_stale is True
    assert recommendation.integrity_is_stale is False
    assert recommendation.lifecycle_context.already_in_bin is False
    assert recommendation.lifecycle_context.restore_expired is False
    assert recommendation.keep_summary.identity_status == "KNOWN"
    assert recommendation.keep_summary.integrity_status == "OK"
    assert recommendation.extra_summary.health_class == "EXTRAS_ALL_UNHEALTHY"
    assert recommendation.extra_summary.active_count == 2
    assert recommendation.extra_summary.healthy_count == 0
    assert recommendation.extra_summary.suspect_count == 1
    assert recommendation.extra_summary.broken_count == 1

    payload = groups[0].to_dict()
    assert isinstance(payload["duplicate_recommendation"], dict)
    assert payload["duplicate_recommendation"]["state"] == "REVIEW_REQUIRED"
    assert payload["duplicate_recommendation"]["classification"] == "WARN"
    assert payload["duplicate_recommendation"]["primary_reason_code"] == "REVIEW_STALE"
    assert payload["duplicate_recommendation"]["review_is_stale"] is True
    assert payload["duplicate_recommendation"]["integrity_is_stale"] is False


def test_resolve_thumbnail_source_returns_image_for_active_file(session_factory, tmp_path: Path) -> None:
    service = OperatorConsoleReadService(session_factory)
    now = datetime(2026, 3, 1, 14, 0, tzinfo=UTC)
    content_id = UUID("88888888-8888-8888-8888-888888888888")
    file_instance_id = UUID("99999999-9999-9999-9999-999999999999")
    image_path = tmp_path / "thumb.jpg"
    image_path.write_bytes(b"jpeg")

    with session_factory.begin() as session:
        _add_content(session, content_id, "hash-thumb", now)
        session.flush()
        _add_instance(
            session,
            file_instance_id=file_instance_id,
            content_id=content_id,
            absolute_path=str(image_path),
            first_seen_at=now,
        )

    resolved = service.resolve_thumbnail_source(file_instance_id)

    assert resolved is not None
    resolved_path, media_type = resolved
    assert resolved_path == image_path
    assert media_type.startswith("image/")


def test_resolve_thumbnail_source_returns_none_for_non_image_or_missing(session_factory, tmp_path: Path) -> None:
    service = OperatorConsoleReadService(session_factory)
    now = datetime(2026, 3, 1, 15, 0, tzinfo=UTC)
    content_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    non_image_id = UUID("abababab-bbbb-cccc-dddd-eeeeeeeeeeee")
    missing_image_id = UUID("cdcdcdcd-bbbb-cccc-dddd-eeeeeeeeeeee")

    movie_path = tmp_path / "clip.mov"
    movie_path.write_bytes(b"mov")

    with session_factory.begin() as session:
        _add_content(session, content_id, "hash-missing", now)
        session.flush()
        _add_instance(
            session,
            file_instance_id=non_image_id,
            content_id=content_id,
            absolute_path=str(movie_path),
            first_seen_at=now,
        )
        _add_instance(
            session,
            file_instance_id=missing_image_id,
            content_id=content_id,
            absolute_path=str(tmp_path / "missing.jpg"),
            first_seen_at=now + timedelta(seconds=1),
        )

    assert service.resolve_thumbnail_source(non_image_id) is None
    assert service.resolve_thumbnail_source(missing_image_id) is None
    assert service.resolve_thumbnail_source(UUID("ffffffff-eeee-dddd-cccc-bbbbbbbbbbbb")) is None


def test_resolve_thumbnail_source_supports_windows_path_wsl_fallback(
    session_factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = OperatorConsoleReadService(session_factory)
    now = datetime(2026, 3, 1, 16, 0, tzinfo=UTC)
    content_id = UUID("12121212-3434-5656-7878-909090909090")
    file_instance_id = UUID("21212121-4343-6565-8787-101010101010")
    windows_style_path = r"C:\Users\micro\Documents\Better Up\Media-Manager-Test\PIC\ladylyb - Personal Chapters — 2021-09-13_105647.JPG"
    mapped_path = tmp_path / "mnt" / "c" / "Users" / "micro" / "Documents" / "Better Up" / "Media-Manager-Test" / "PIC" / "ladylyb - Personal Chapters — 2021-09-13_105647.JPG"
    mapped_path.parent.mkdir(parents=True, exist_ok=True)
    mapped_path.write_bytes(b"jpeg-data")

    with session_factory.begin() as session:
        _add_content(session, content_id, "hash-win", now)
        session.flush()
        _add_instance(
            session,
            file_instance_id=file_instance_id,
            content_id=content_id,
            absolute_path=windows_style_path,
            first_seen_at=now,
        )

    original_exists = Path.exists
    original_is_file = Path.is_file
    original_open = Path.open

    def fake_exists(path_obj: Path) -> bool:
        path_str = str(path_obj)
        if path_str.startswith("/mnt/c/"):
            translated = tmp_path / path_str.lstrip("/")
            return translated.exists()
        return original_exists(path_obj)

    def fake_is_file(path_obj: Path) -> bool:
        path_str = str(path_obj)
        if path_str.startswith("/mnt/c/"):
            translated = tmp_path / path_str.lstrip("/")
            return translated.is_file()
        return original_is_file(path_obj)

    def fake_open(path_obj: Path, mode: str = "r", *args, **kwargs):
        path_str = str(path_obj)
        if path_str.startswith("/mnt/c/"):
            translated = tmp_path / path_str.lstrip("/")
            return translated.open(mode, *args, **kwargs)
        return original_open(path_obj, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "is_file", fake_is_file)
    monkeypatch.setattr(Path, "open", fake_open)

    resolved = service.resolve_thumbnail_source(file_instance_id)

    assert resolved is not None
    resolved_path, media_type = resolved
    assert str(resolved_path).startswith("/mnt/c/")
    assert media_type.startswith("image/")


def test_duplicate_reclaim_operator_pages_use_bin_native_authority(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    base = datetime(2026, 3, 3, 12, 0, tzinfo=UTC)
    archived_content = UUID("eeeeeeee-1111-1111-1111-111111111111")
    recycled_content = UUID("eeeeeeee-2222-2222-2222-222222222222")
    archived_file = UUID("eeeeeeee-1111-1111-1111-111111111112")
    recycled_file = UUID("eeeeeeee-2222-2222-2222-222222222223")

    with session_factory.begin() as session:
        _add_content(session, archived_content, "hash-archive-page", base)
        _add_content(session, recycled_content, "hash-retention-page", base)
        session.flush()
        _add_instance(
            session,
            file_instance_id=archived_file,
            content_id=archived_content,
            absolute_path="/bin/authoritative-archived.jpg",
            first_seen_at=base,
        )
        _add_instance(
            session,
            file_instance_id=recycled_file,
            content_id=recycled_content,
            absolute_path="/bin/current-recycled.jpg",
            first_seen_at=base + timedelta(seconds=1),
        )
        session.add_all(
            [
                DuplicateReclaimItem(
                    file_instance_id=archived_file,
                    content_id=archived_content,
                    original_path="/library/archived.jpg",
                    archive_path="/bin/legacy-archived.jpg",
                    planned_bin_path="/bin/legacy-archived.jpg",
                    bin_path="/bin/authoritative-archived.jpg",
                    item_status="ARCHIVED",
                    reclaimed_at=base,
                    bin_entered_at=base,
                    expires_at=base + timedelta(days=10),
                    restore_expires_at=base + timedelta(days=2),
                    bin_state=DuplicateBinState.IN_BIN.value,
                    recycle_path=None,
                    recycled_at=None,
                    purge_after_at=None,
                    purged_at=None,
                    restored_at=None,
                    created_at=base,
                    updated_at=base,
                ),
                DuplicateReclaimItem(
                    file_instance_id=recycled_file,
                    content_id=recycled_content,
                    original_path="/library/recycled.jpg",
                    archive_path="/bin/stale-archive-recycled.jpg",
                    planned_bin_path=None,
                    bin_path="/bin/current-recycled.jpg",
                    item_status="RECYCLED",
                    reclaimed_at=base - timedelta(days=4),
                    bin_entered_at=base - timedelta(days=4),
                    expires_at=base + timedelta(days=10),
                    restore_expires_at=base - timedelta(days=1),
                    bin_state=DuplicateBinState.IN_BIN.value,
                    recycle_path="/bin/current-recycled.jpg",
                    recycled_at=base - timedelta(hours=2),
                    purge_after_at=base + timedelta(days=3),
                    purged_at=None,
                    restored_at=None,
                    created_at=base,
                    updated_at=base,
                ),
            ]
        )

    archive_page = service.get_duplicate_reclaim_archive_page(page=1, limit=10)
    retention_page = service.get_retention_recycle_page(page=1, limit=10)

    archive_item = next(item for item in archive_page.items if item.file_instance_id == str(archived_file))
    assert archive_item.archive_path == "/bin/authoritative-archived.jpg"
    assert archive_item.expires_at == (base + timedelta(days=2)).isoformat()

    retention_item = next(item for item in retention_page.items if item.file_instance_id == str(recycled_file))
    assert retention_item.source_path == "/bin/current-recycled.jpg"
    assert retention_item.retention_expires_at == (base - timedelta(days=1)).isoformat()


def test_duplicate_reclaim_archive_page_does_not_fallback_to_legacy_archive_path_for_archived_rows(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    base = datetime(2026, 3, 3, 13, 0, tzinfo=UTC)
    content_id = UUID("eeeeeeee-3333-3333-3333-333333333333")
    file_instance_id = UUID("eeeeeeee-3333-3333-3333-333333333334")

    with session_factory.begin() as session:
        _add_content(session, content_id, "hash-archive-fallback", base)
        session.flush()
        _add_instance(
            session,
            file_instance_id=file_instance_id,
            content_id=content_id,
            absolute_path="/library/archived.jpg",
            first_seen_at=base,
        )
        session.add(
            DuplicateReclaimItem(
                file_instance_id=file_instance_id,
                content_id=content_id,
                original_path="/library/archived.jpg",
                archive_path="/bin/legacy-only-path.jpg",
                planned_bin_path=None,
                bin_path=None,
                item_status="ARCHIVED",
                reclaimed_at=base,
                bin_entered_at=None,
                expires_at=base + timedelta(days=5),
                restore_expires_at=base + timedelta(days=2),
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

    archive_page = service.get_duplicate_reclaim_archive_page(page=1, limit=10)

    archive_item = next(item for item in archive_page.items if item.file_instance_id == str(file_instance_id))
    assert archive_item.archive_path == ""
    assert archive_item.expires_at == (base + timedelta(days=2)).isoformat()
