from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from media_manager.app.persistence.models import CanonicalAssignment, FileContent, FileInstance, FileInstanceStatus
from media_manager.app.persistence.models import TagSource
from media_manager.app.persistence.tagging import upsert_canonical_tag
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


def _add_assignment(
    session,
    *,
    assignment_id: UUID,
    content_id: UUID,
    canonical_instance_id: UUID,
    assigned_at: datetime,
    policy_name: str = "FIRST_SEEN",
    policy_version: str = "v1",
) -> None:
    session.add(
        CanonicalAssignment(
            assignment_id=assignment_id,
            content_id=content_id,
            canonical_instance_id=canonical_instance_id,
            policy_name=policy_name,
            policy_version=policy_version,
            assigned_at=assigned_at,
        )
    )


def test_get_canonical_gallery_orders_latest_assignments_and_maps_media_types(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    base = datetime(2026, 3, 2, 10, 0, tzinfo=UTC)

    content_a = UUID("10000000-0000-0000-0000-000000000001")
    content_b = UUID("10000000-0000-0000-0000-000000000002")
    content_c = UUID("10000000-0000-0000-0000-000000000003")

    a_img = UUID("20000000-0000-0000-0000-000000000001")
    b_vid = UUID("20000000-0000-0000-0000-000000000002")
    c_txt = UUID("20000000-0000-0000-0000-000000000003")

    with session_factory.begin() as session:
        _add_content(session, content_a, "hash-a", base)
        _add_content(session, content_b, "hash-b", base)
        _add_content(session, content_c, "hash-c", base)
        session.flush()

        _add_instance(
            session,
            file_instance_id=a_img,
            content_id=content_a,
            absolute_path="/gallery/a.jpg",
            first_seen_at=base,
        )
        _add_instance(
            session,
            file_instance_id=b_vid,
            content_id=content_b,
            absolute_path="/gallery/b.mov",
            first_seen_at=base,
        )
        _add_instance(
            session,
            file_instance_id=c_txt,
            content_id=content_c,
            absolute_path="/gallery/c.txt",
            first_seen_at=base,
        )

        _add_assignment(
            session,
            assignment_id=UUID("30000000-0000-0000-0000-000000000001"),
            content_id=content_a,
            canonical_instance_id=a_img,
            assigned_at=base + timedelta(minutes=2),
        )
        _add_assignment(
            session,
            assignment_id=UUID("30000000-0000-0000-0000-000000000002"),
            content_id=content_b,
            canonical_instance_id=b_vid,
            assigned_at=base + timedelta(minutes=1),
        )
        _add_assignment(
            session,
            assignment_id=UUID("30000000-0000-0000-0000-000000000003"),
            content_id=content_c,
            canonical_instance_id=c_txt,
            assigned_at=base,
        )

    page = service.get_canonical_gallery(page=1, limit=30)

    assert page.total_count == 2
    assert page.page == 1
    assert page.limit == 30
    assert page.total_pages == 1
    assert [item.id for item in page.items] == [str(a_img), str(b_vid)]
    assert [item.file_type for item in page.items] == ["image", "video"]
    assert page.items[0].media_url == f"/media/{a_img}"


def test_get_canonical_gallery_uses_latest_assignment_per_content(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    base = datetime(2026, 3, 2, 11, 0, tzinfo=UTC)

    content_id = UUID("40000000-0000-0000-0000-000000000001")
    old_instance = UUID("41000000-0000-0000-0000-000000000001")
    new_instance = UUID("42000000-0000-0000-0000-000000000001")

    with session_factory.begin() as session:
        _add_content(session, content_id, "hash-latest", base)
        session.flush()

        _add_instance(
            session,
            file_instance_id=old_instance,
            content_id=content_id,
            absolute_path="/gallery/old.jpg",
            first_seen_at=base,
        )
        _add_instance(
            session,
            file_instance_id=new_instance,
            content_id=content_id,
            absolute_path="/gallery/new.jpg",
            first_seen_at=base + timedelta(seconds=1),
        )

        _add_assignment(
            session,
            assignment_id=UUID("43000000-0000-0000-0000-000000000001"),
            content_id=content_id,
            canonical_instance_id=old_instance,
            assigned_at=base,
        )
        _add_assignment(
            session,
            assignment_id=UUID("43000000-0000-0000-0000-000000000002"),
            content_id=content_id,
            canonical_instance_id=new_instance,
            assigned_at=base + timedelta(seconds=2),
        )

    page = service.get_canonical_gallery()

    assert len(page.items) == 1
    assert page.items[0].id == str(new_instance)
    assert page.items[0].filename == "new.jpg"


def test_get_canonical_gallery_excludes_inactive_canonical_instances(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    base = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)

    content_id = UUID("50000000-0000-0000-0000-000000000001")
    inactive = UUID("51000000-0000-0000-0000-000000000001")

    with session_factory.begin() as session:
        _add_content(session, content_id, "hash-inactive", base)
        session.flush()
        _add_instance(
            session,
            file_instance_id=inactive,
            content_id=content_id,
            absolute_path="/gallery/inactive.jpg",
            first_seen_at=base,
            status=FileInstanceStatus.DELETED.value,
        )
        _add_assignment(
            session,
            assignment_id=UUID("52000000-0000-0000-0000-000000000001"),
            content_id=content_id,
            canonical_instance_id=inactive,
            assigned_at=base,
        )

    page = service.get_canonical_gallery()

    assert page.total_count == 0
    assert page.items == ()


def test_get_canonical_gallery_pagination_and_out_of_range(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    base = datetime(2026, 3, 2, 13, 0, tzinfo=UTC)

    with session_factory.begin() as session:
        for idx in range(3):
            content_id = UUID(f"60000000-0000-0000-0000-00000000000{idx}")
            instance_id = UUID(f"61000000-0000-0000-0000-00000000000{idx}")
            _add_content(session, content_id, f"hash-{idx}", base)
            session.flush()
            _add_instance(
                session,
                file_instance_id=instance_id,
                content_id=content_id,
                absolute_path=f"/gallery/{idx}.jpg",
                first_seen_at=base,
            )
            _add_assignment(
                session,
                assignment_id=UUID(f"62000000-0000-0000-0000-00000000000{idx}"),
                content_id=content_id,
                canonical_instance_id=instance_id,
                assigned_at=base + timedelta(seconds=idx),
            )

    page1 = service.get_canonical_gallery(page=1, limit=2)
    page2 = service.get_canonical_gallery(page=2, limit=2)
    page3 = service.get_canonical_gallery(page=9, limit=2)

    assert page1.total_count == 3
    assert page1.limit == 2
    assert page1.total_pages == 2
    assert len(page1.items) == 2
    assert len(page2.items) == 1
    assert page3.page == 9
    assert page3.items == ()


def test_get_canonical_gallery_sanitizes_page_and_limit_bounds(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)

    page = service.get_canonical_gallery(page=0, limit=0)

    assert page.page == 1
    assert page.total_pages == 0
    assert page.items == ()


def test_get_canonical_gallery_supports_tag_filter_and_discovery_fields(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    base = datetime(2026, 3, 2, 13, 30, tzinfo=UTC)

    content_a = UUID("62000000-0000-0000-0000-000000000001")
    content_b = UUID("62000000-0000-0000-0000-000000000002")
    a_id = UUID("63000000-0000-0000-0000-000000000001")
    b_id = UUID("63000000-0000-0000-0000-000000000002")

    with session_factory.begin() as session:
        _add_content(session, content_a, "hash-ta", base)
        _add_content(session, content_b, "hash-tb", base + timedelta(seconds=1))
        session.flush()
        _add_instance(
            session,
            file_instance_id=a_id,
            content_id=content_a,
            absolute_path="/gallery/filter-a.jpg",
            first_seen_at=base,
        )
        _add_instance(
            session,
            file_instance_id=b_id,
            content_id=content_b,
            absolute_path="/gallery/filter-b.jpg",
            first_seen_at=base + timedelta(seconds=1),
        )
        _add_assignment(
            session,
            assignment_id=UUID("64000000-0000-0000-0000-000000000001"),
            content_id=content_a,
            canonical_instance_id=a_id,
            assigned_at=base,
        )
        _add_assignment(
            session,
            assignment_id=UUID("64000000-0000-0000-0000-000000000002"),
            content_id=content_b,
            canonical_instance_id=b_id,
            assigned_at=base + timedelta(seconds=1),
        )
        session.flush()
        upsert_canonical_tag(
            session,
            canonical_id=content_a,
            tag_name="city",
            source=TagSource.AI,
            confidence_score=0.8,
            enrichment_version=1,
        )
        upsert_canonical_tag(
            session,
            canonical_id=content_a,
            tag_name="travel",
            source=TagSource.AI,
            confidence_score=0.9,
            enrichment_version=1,
        )
        upsert_canonical_tag(
            session,
            canonical_id=content_b,
            tag_name="city",
            source=TagSource.MANUAL,
            confidence_score=1.0,
            enrichment_version=1,
        )

    page = service.get_canonical_gallery(tags=("city", "travel"), sort_by="confidence_score", sort_order="desc")
    assert page.total_count == 1
    assert page.items[0].id == str(a_id)
    assert page.items[0].matched_tags == ("city", "travel")
    assert page.items[0].top_confidence_score == 0.9
    assert page.items[0].sort_tag_name == "city"


def test_get_canonical_gallery_supports_source_filter(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    base = datetime(2026, 3, 2, 13, 40, tzinfo=UTC)

    content_a = UUID("65000000-0000-0000-0000-000000000001")
    content_b = UUID("65000000-0000-0000-0000-000000000002")
    a_id = UUID("66000000-0000-0000-0000-000000000001")
    b_id = UUID("66000000-0000-0000-0000-000000000002")

    with session_factory.begin() as session:
        _add_content(session, content_a, "hash-sa", base)
        _add_content(session, content_b, "hash-sb", base + timedelta(seconds=1))
        session.flush()
        _add_instance(session, file_instance_id=a_id, content_id=content_a, absolute_path="/gallery/sa.jpg", first_seen_at=base)
        _add_instance(session, file_instance_id=b_id, content_id=content_b, absolute_path="/gallery/sb.jpg", first_seen_at=base)
        _add_assignment(
            session,
            assignment_id=UUID("67000000-0000-0000-0000-000000000001"),
            content_id=content_a,
            canonical_instance_id=a_id,
            assigned_at=base,
        )
        _add_assignment(
            session,
            assignment_id=UUID("67000000-0000-0000-0000-000000000002"),
            content_id=content_b,
            canonical_instance_id=b_id,
            assigned_at=base + timedelta(seconds=1),
        )
        session.flush()
        upsert_canonical_tag(
            session,
            canonical_id=content_a,
            tag_name="x",
            source=TagSource.AI,
            confidence_score=0.7,
            enrichment_version=1,
        )
        upsert_canonical_tag(
            session,
            canonical_id=content_b,
            tag_name="y",
            source=TagSource.MANUAL,
            confidence_score=1.0,
            enrichment_version=1,
        )

    page = service.get_canonical_gallery(source=TagSource.MANUAL)
    assert page.total_count == 1
    assert page.items[0].id == str(b_id)


def test_resolve_media_source_returns_media_for_active_image_and_video(session_factory, tmp_path: Path) -> None:
    service = OperatorConsoleReadService(session_factory)
    now = datetime(2026, 3, 2, 14, 0, tzinfo=UTC)

    content_img = UUID("70000000-0000-0000-0000-000000000001")
    file_img = UUID("71000000-0000-0000-0000-000000000001")
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"img")

    content_vid = UUID("70000000-0000-0000-0000-000000000002")
    file_vid = UUID("71000000-0000-0000-0000-000000000002")
    video_path = tmp_path / "video.mov"
    video_path.write_bytes(b"vid")

    with session_factory.begin() as session:
        _add_content(session, content_img, "hash-img", now)
        _add_content(session, content_vid, "hash-vid", now)
        session.flush()
        _add_instance(
            session,
            file_instance_id=file_img,
            content_id=content_img,
            absolute_path=str(image_path),
            first_seen_at=now,
        )
        _add_instance(
            session,
            file_instance_id=file_vid,
            content_id=content_vid,
            absolute_path=str(video_path),
            first_seen_at=now,
        )

    resolved_img = service.resolve_media_source(file_img)
    resolved_vid = service.resolve_media_source(file_vid)

    assert resolved_img is not None
    assert resolved_vid is not None
    assert resolved_img[0] == image_path
    assert resolved_vid[0] == video_path


def test_resolve_media_source_returns_none_for_invalid_rows_or_paths(session_factory, tmp_path: Path) -> None:
    service = OperatorConsoleReadService(session_factory)
    now = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)

    content_id = UUID("80000000-0000-0000-0000-000000000001")
    inactive_id = UUID("81000000-0000-0000-0000-000000000001")
    missing_id = UUID("81000000-0000-0000-0000-000000000002")
    unsupported_id = UUID("81000000-0000-0000-0000-000000000003")

    unsupported_path = tmp_path / "note.txt"
    unsupported_path.write_text("x", encoding="utf-8")

    with session_factory.begin() as session:
        _add_content(session, content_id, "hash-bad", now)
        session.flush()
        _add_instance(
            session,
            file_instance_id=inactive_id,
            content_id=content_id,
            absolute_path=str(tmp_path / "inactive.jpg"),
            first_seen_at=now,
            status=FileInstanceStatus.DELETED.value,
        )
        _add_instance(
            session,
            file_instance_id=missing_id,
            content_id=content_id,
            absolute_path=str(tmp_path / "missing.jpg"),
            first_seen_at=now + timedelta(seconds=1),
        )
        _add_instance(
            session,
            file_instance_id=unsupported_id,
            content_id=content_id,
            absolute_path=str(unsupported_path),
            first_seen_at=now + timedelta(seconds=2),
        )

    assert service.resolve_media_source(inactive_id) is None
    assert service.resolve_media_source(missing_id) is None
    assert service.resolve_media_source(unsupported_id) is None
    assert service.resolve_media_source(UUID("ffffffff-eeee-dddd-cccc-bbbbbbbbbbbb")) is None


def test_resolve_media_source_supports_windows_path_wsl_fallback(
    session_factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = OperatorConsoleReadService(session_factory)
    now = datetime(2026, 3, 2, 16, 0, tzinfo=UTC)
    content_id = UUID("90000000-0000-0000-0000-000000000001")
    file_instance_id = UUID("91000000-0000-0000-0000-000000000001")
    windows_path = r"C:\Users\micro\Documents\Better Up\Media-Manager-Test\PIC\gallery_frame.jpg"
    mapped_path = tmp_path / "mnt" / "c" / "Users" / "micro" / "Documents" / "Better Up" / "Media-Manager-Test" / "PIC" / "gallery_frame.jpg"
    mapped_path.parent.mkdir(parents=True, exist_ok=True)
    mapped_path.write_bytes(b"img")

    with session_factory.begin() as session:
        _add_content(session, content_id, "hash-win", now)
        session.flush()
        _add_instance(
            session,
            file_instance_id=file_instance_id,
            content_id=content_id,
            absolute_path=windows_path,
            first_seen_at=now,
        )

    original_exists = Path.exists
    original_is_file = Path.is_file
    original_open = Path.open

    def fake_exists(path_obj: Path) -> bool:
        raw = str(path_obj)
        if raw.startswith("/mnt/c/"):
            return (tmp_path / raw.lstrip("/")).exists()
        return original_exists(path_obj)

    def fake_is_file(path_obj: Path) -> bool:
        raw = str(path_obj)
        if raw.startswith("/mnt/c/"):
            return (tmp_path / raw.lstrip("/")).is_file()
        return original_is_file(path_obj)

    def fake_open(path_obj: Path, mode: str = "r", *args, **kwargs):
        raw = str(path_obj)
        if raw.startswith("/mnt/c/"):
            return (tmp_path / raw.lstrip("/")).open(mode, *args, **kwargs)
        return original_open(path_obj, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "is_file", fake_is_file)
    monkeypatch.setattr(Path, "open", fake_open)

    resolved = service.resolve_media_source(file_instance_id)

    assert resolved is not None
    assert str(resolved[0]).startswith("/mnt/c/")


def test_get_canonical_gallery_detail_returns_detail_for_active_canonical(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    now = datetime(2026, 3, 2, 17, 0, tzinfo=UTC)
    content_id = UUID("a0000000-0000-0000-0000-000000000001")
    instance_id = UUID("a1000000-0000-0000-0000-000000000001")

    with session_factory.begin() as session:
        _add_content(session, content_id, "hash-detail", now)
        session.flush()
        _add_instance(
            session,
            file_instance_id=instance_id,
            content_id=content_id,
            absolute_path="/gallery/detail.jpg",
            first_seen_at=now,
        )
        _add_assignment(
            session,
            assignment_id=UUID("a2000000-0000-0000-0000-000000000001"),
            content_id=content_id,
            canonical_instance_id=instance_id,
            assigned_at=now,
        )

    detail = service.get_canonical_gallery_detail(instance_id)

    assert detail is not None
    assert detail.id == str(instance_id)
    assert detail.file_type == "image"
    assert detail.filename == "detail.jpg"
    assert detail.media_url == f"/media/{instance_id}"


def test_get_canonical_gallery_detail_returns_none_for_noncanonical_or_inactive(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    now = datetime(2026, 3, 2, 18, 0, tzinfo=UTC)
    content_id = UUID("b0000000-0000-0000-0000-000000000001")
    canonical_id = UUID("b1000000-0000-0000-0000-000000000001")
    inactive_canonical_id = UUID("b2000000-0000-0000-0000-000000000001")
    noncanonical_id = UUID("b3000000-0000-0000-0000-000000000001")

    with session_factory.begin() as session:
        _add_content(session, content_id, "hash-detail-none", now)
        session.flush()
        _add_instance(
            session,
            file_instance_id=canonical_id,
            content_id=content_id,
            absolute_path="/gallery/canonical.jpg",
            first_seen_at=now,
        )
        _add_instance(
            session,
            file_instance_id=inactive_canonical_id,
            content_id=content_id,
            absolute_path="/gallery/inactive.jpg",
            first_seen_at=now + timedelta(seconds=1),
            status=FileInstanceStatus.DELETED.value,
        )
        _add_instance(
            session,
            file_instance_id=noncanonical_id,
            content_id=content_id,
            absolute_path="/gallery/noncanonical.jpg",
            first_seen_at=now + timedelta(seconds=2),
        )
        _add_assignment(
            session,
            assignment_id=UUID("b4000000-0000-0000-0000-000000000001"),
            content_id=content_id,
            canonical_instance_id=inactive_canonical_id,
            assigned_at=now + timedelta(seconds=3),
        )

    assert service.get_canonical_gallery_detail(noncanonical_id) is None
    assert service.get_canonical_gallery_detail(inactive_canonical_id) is None
    assert service.get_canonical_gallery_detail(UUID("ffffffff-eeee-dddd-cccc-bbbbbbbbbbbb")) is None
