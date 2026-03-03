from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from media_manager.app.persistence.media_file_queries import (
    get_history_by_path,
    get_reappearances_after_deleted,
    get_rows_by_hash,
    get_rows_by_status,
)
from media_manager.app.persistence.models import MediaFile, MediaFileStatus


BASE_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _add_media_file(
    session,
    *,
    current_path: str,
    discovered_path: str | None = None,
    status: MediaFileStatus = MediaFileStatus.INGESTED,
    discovered_at: datetime,
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


def test_get_rows_by_hash_exact_match_returns_rows(session_factory) -> None:
    exact_hash = "a" * 64
    with session_factory.begin() as session:
        first = _add_media_file(
            session,
            current_path="/data/a.jpg",
            discovered_at=BASE_TS,
            hash_sha256=exact_hash,
        )
        _add_media_file(
            session,
            current_path="/data/b.jpg",
            discovered_at=BASE_TS + timedelta(seconds=1),
            hash_sha256="b" * 64,
        )

    with session_factory() as session:
        rows = get_rows_by_hash(session, exact_hash)
    assert [row.id for row in rows] == [first.id]


def test_get_rows_by_hash_prefix_match_returns_rows(session_factory) -> None:
    with session_factory.begin() as session:
        first = _add_media_file(
            session,
            current_path="/data/a.jpg",
            discovered_at=BASE_TS,
            hash_sha256="abc" + "1" * 61,
        )
        second = _add_media_file(
            session,
            current_path="/data/b.jpg",
            discovered_at=BASE_TS + timedelta(seconds=1),
            hash_sha256="abc" + "2" * 61,
        )
        _add_media_file(
            session,
            current_path="/data/c.jpg",
            discovered_at=BASE_TS + timedelta(seconds=2),
            hash_sha256="def" + "3" * 61,
        )

    with session_factory() as session:
        rows = get_rows_by_hash(session, "ABC")
    assert [row.id for row in rows] == [first.id, second.id]


def test_get_rows_by_hash_empty_prefix_returns_empty(session_factory) -> None:
    with session_factory.begin() as session:
        _add_media_file(
            session,
            current_path="/data/a.jpg",
            discovered_at=BASE_TS,
            hash_sha256="a" * 64,
        )

    with session_factory() as session:
        rows = get_rows_by_hash(session, "   ")
    assert rows == []


def test_get_history_by_path_includes_current_and_discovered_matches_ordered(session_factory) -> None:
    target = "/archive/file.jpg"
    with session_factory.begin() as session:
        first = _add_media_file(
            session,
            current_path=target,
            discovered_at=BASE_TS,
            hash_sha256="a" * 64,
        )
        second = _add_media_file(
            session,
            current_path="/renamed/file.jpg",
            discovered_path=target,
            discovered_at=BASE_TS + timedelta(seconds=2),
            hash_sha256="b" * 64,
        )
        _add_media_file(
            session,
            current_path="/other/file.jpg",
            discovered_at=BASE_TS + timedelta(seconds=1),
            hash_sha256="c" * 64,
        )

    with session_factory() as session:
        rows = get_history_by_path(session, target)
    assert [row.id for row in rows] == [first.id, second.id]


def test_get_rows_by_status_filters_correctly(session_factory) -> None:
    with session_factory.begin() as session:
        ingested = _add_media_file(
            session,
            current_path="/data/i.jpg",
            discovered_at=BASE_TS,
            status=MediaFileStatus.INGESTED,
            hash_sha256="1" * 64,
        )
        processed = _add_media_file(
            session,
            current_path="/data/p.jpg",
            discovered_at=BASE_TS + timedelta(seconds=1),
            status=MediaFileStatus.PROCESSED,
            hash_sha256="2" * 64,
        )
        _add_media_file(
            session,
            current_path="/data/d.jpg",
            discovered_at=BASE_TS + timedelta(seconds=2),
            status=MediaFileStatus.DELETED,
            deleted_at=BASE_TS + timedelta(seconds=2),
            hash_sha256="3" * 64,
        )

    with session_factory() as session:
        rows = get_rows_by_status(session, MediaFileStatus.INGESTED)
    assert [row.id for row in rows] == [ingested.id]
    assert processed.id not in [row.id for row in rows]


def test_get_reappearances_after_deleted_uses_latest_delete_boundary(session_factory) -> None:
    target = "/dataset/a.jpg"
    with session_factory.begin() as session:
        _add_media_file(
            session,
            current_path=target,
            discovered_at=BASE_TS + timedelta(minutes=1),
            status=MediaFileStatus.DELETED,
            deleted_at=BASE_TS + timedelta(minutes=1),
            hash_sha256="a" * 64,
        )
        _add_media_file(
            session,
            current_path=target,
            discovered_at=BASE_TS + timedelta(minutes=3),
            status=MediaFileStatus.DELETED,
            deleted_at=BASE_TS + timedelta(minutes=3),
            hash_sha256="b" * 64,
        )
        latest_1 = _add_media_file(
            session,
            current_path=target,
            discovered_at=BASE_TS + timedelta(minutes=4),
            status=MediaFileStatus.INGESTED,
            hash_sha256="c" * 64,
        )
        latest_2 = _add_media_file(
            session,
            current_path="/dataset/a-renamed.jpg",
            discovered_path=target,
            discovered_at=BASE_TS + timedelta(minutes=5),
            status=MediaFileStatus.PROCESSED,
            hash_sha256="d" * 64,
        )

    with session_factory() as session:
        rows = get_reappearances_after_deleted(session, target)
    assert [row.id for row in rows] == [latest_1.id, latest_2.id]


def test_get_reappearances_after_deleted_returns_empty_without_deleted_row(session_factory) -> None:
    target = "/dataset/never-deleted.jpg"
    with session_factory.begin() as session:
        _add_media_file(
            session,
            current_path=target,
            discovered_at=BASE_TS,
            status=MediaFileStatus.INGESTED,
            hash_sha256="a" * 64,
        )

    with session_factory() as session:
        rows = get_reappearances_after_deleted(session, target)
    assert rows == []


def test_query_helpers_are_read_only_no_mutation(session_factory) -> None:
    target = "/dataset/readonly.jpg"
    with session_factory.begin() as session:
        _add_media_file(
            session,
            current_path=target,
            discovered_at=BASE_TS,
            status=MediaFileStatus.INGESTED,
            hash_sha256="a" * 64,
        )
        _add_media_file(
            session,
            current_path=target,
            discovered_at=BASE_TS + timedelta(minutes=1),
            status=MediaFileStatus.DELETED,
            deleted_at=BASE_TS + timedelta(minutes=1),
            hash_sha256="b" * 64,
        )

    with session_factory() as session:
        before_rows = session.scalars(select(MediaFile).order_by(MediaFile.discovered_at.asc(), MediaFile.id.asc())).all()
        before_state = [
            (row.id, row.status, row.hash_sha256, row.discovered_at, row.deleted_at, row.current_path, row.discovered_path)
            for row in before_rows
        ]

        get_rows_by_hash(session, "a")
        get_history_by_path(session, target)
        get_rows_by_status(session, MediaFileStatus.INGESTED)
        get_reappearances_after_deleted(session, target)

        after_rows = session.scalars(select(MediaFile).order_by(MediaFile.discovered_at.asc(), MediaFile.id.asc())).all()
        after_state = [
            (row.id, row.status, row.hash_sha256, row.discovered_at, row.deleted_at, row.current_path, row.discovered_path)
            for row in after_rows
        ]

    assert before_state == after_state
