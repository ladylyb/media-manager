from __future__ import annotations

from datetime import UTC, datetime, timedelta

from media_manager.app.persistence.models import MediaFile, MediaFileStatus
from media_manager.app.persistence.operator_console import OperatorConsoleReadService


def _add_media_file(
    session,
    *,
    current_path: str,
    discovered_at: datetime,
    status: MediaFileStatus,
    discovered_path: str | None = None,
    hash_sha256: str | None = None,
    deleted_at: datetime | None = None,
) -> MediaFile:
    row = MediaFile(
        current_path=current_path,
        discovered_path=discovered_path if discovered_path is not None else current_path,
        size_bytes=10,
        hash_sha256=hash_sha256,
        discovered_at=discovered_at,
        ingested_at=discovered_at,
        status=status.value,
        deleted_at=deleted_at,
    )
    session.add(row)
    session.flush()
    return row


def test_get_media_file_by_hash_page_returns_expected_rows(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    base = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)

    with session_factory.begin() as session:
        first = _add_media_file(
            session,
            current_path="/mf/a.jpg",
            discovered_at=base,
            status=MediaFileStatus.INGESTED,
            hash_sha256="abc" + "1" * 61,
        )
        _add_media_file(
            session,
            current_path="/mf/b.jpg",
            discovered_at=base + timedelta(seconds=1),
            status=MediaFileStatus.INGESTED,
            hash_sha256="def" + "2" * 61,
        )

    page = service.get_media_file_by_hash_page(hash_prefix="abc", page=1, limit=30)

    assert page.total_count == 1
    assert [item.id for item in page.items] == [str(first.id)]


def test_get_media_file_history_page_includes_current_and_discovered_path_matches(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    base = datetime(2026, 3, 2, 10, 0, tzinfo=UTC)
    target = "/mf/history.jpg"

    with session_factory.begin() as session:
        first = _add_media_file(
            session,
            current_path=target,
            discovered_at=base,
            status=MediaFileStatus.INGESTED,
            hash_sha256="a" * 64,
        )
        second = _add_media_file(
            session,
            current_path="/mf/renamed.jpg",
            discovered_path=target,
            discovered_at=base + timedelta(seconds=1),
            status=MediaFileStatus.PROCESSED,
            hash_sha256="b" * 64,
        )

    page = service.get_media_file_history_page(path=target, page=1, limit=30)

    assert page.total_count == 2
    assert [item.id for item in page.items] == [str(first.id), str(second.id)]


def test_get_media_file_by_status_page_filters_status(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    base = datetime(2026, 3, 2, 11, 0, tzinfo=UTC)

    with session_factory.begin() as session:
        first = _add_media_file(
            session,
            current_path="/mf/one.jpg",
            discovered_at=base,
            status=MediaFileStatus.INGESTED,
            hash_sha256="1" * 64,
        )
        _add_media_file(
            session,
            current_path="/mf/two.jpg",
            discovered_at=base + timedelta(seconds=1),
            status=MediaFileStatus.PROCESSED,
            hash_sha256="2" * 64,
        )

    page = service.get_media_file_by_status_page(status=MediaFileStatus.INGESTED, page=1, limit=30)

    assert page.total_count == 1
    assert [item.id for item in page.items] == [str(first.id)]
    assert page.items[0].status == MediaFileStatus.INGESTED.value


def test_get_media_file_reappearances_page_uses_latest_deleted_boundary(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    base = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)
    target = "/mf/reappear.jpg"

    with session_factory.begin() as session:
        _add_media_file(
            session,
            current_path=target,
            discovered_at=base,
            status=MediaFileStatus.DELETED,
            hash_sha256="a" * 64,
            deleted_at=base,
        )
        _add_media_file(
            session,
            current_path=target,
            discovered_at=base + timedelta(minutes=1),
            status=MediaFileStatus.DELETED,
            hash_sha256="b" * 64,
            deleted_at=base + timedelta(minutes=1),
        )
        after_latest = _add_media_file(
            session,
            current_path=target,
            discovered_at=base + timedelta(minutes=2),
            status=MediaFileStatus.INGESTED,
            hash_sha256="c" * 64,
        )
        after_latest_renamed = _add_media_file(
            session,
            current_path="/mf/reappear-renamed.jpg",
            discovered_path=target,
            discovered_at=base + timedelta(minutes=3),
            status=MediaFileStatus.PROCESSED,
            hash_sha256="d" * 64,
        )

    page = service.get_media_file_reappearances_page(path=target, page=1, limit=30)

    assert page.total_count == 2
    assert [item.id for item in page.items] == [str(after_latest.id), str(after_latest_renamed.id)]


def test_media_file_ledger_paging_is_deterministic(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    base = datetime(2026, 3, 2, 13, 0, tzinfo=UTC)

    with session_factory.begin() as session:
        first = _add_media_file(
            session,
            current_path="/mf/p1.jpg",
            discovered_at=base,
            status=MediaFileStatus.INGESTED,
            hash_sha256="abc" + "1" * 61,
        )
        second = _add_media_file(
            session,
            current_path="/mf/p2.jpg",
            discovered_at=base + timedelta(seconds=1),
            status=MediaFileStatus.INGESTED,
            hash_sha256="abc" + "2" * 61,
        )
        third = _add_media_file(
            session,
            current_path="/mf/p3.jpg",
            discovered_at=base + timedelta(seconds=2),
            status=MediaFileStatus.INGESTED,
            hash_sha256="abc" + "3" * 61,
        )

    page1 = service.get_media_file_by_hash_page(hash_prefix="abc", page=1, limit=2)
    page2 = service.get_media_file_by_hash_page(hash_prefix="abc", page=2, limit=2)

    assert page1.total_count == 3
    assert page1.total_pages == 2
    assert [item.id for item in page1.items] == [str(first.id), str(second.id)]
    assert [item.id for item in page2.items] == [str(third.id)]
