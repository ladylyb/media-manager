from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from media_manager.app.persistence.models import CanonicalAssignment, FileContent, FileInstance, FileInstanceStatus
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


def test_get_duplicate_groups_orders_groups_and_files_deterministically(session_factory) -> None:
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
    assert groups[0].files[0].thumbnail_url == f"/api/thumbnail/{a1}"
    assert groups[0].files[2].thumbnail_url is None


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

