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
    hash_sha256: str,
    discovered_path: str | None = None,
    deleted_at: datetime | None = None,
) -> None:
    session.add(
        MediaFile(
            current_path=current_path,
            discovered_path=discovered_path if discovered_path is not None else current_path,
            size_bytes=10,
            hash_sha256=hash_sha256,
            discovered_at=discovered_at,
            ingested_at=discovered_at,
            status=status.value,
            deleted_at=deleted_at,
        )
    )


def test_media_file_analytics_empty_dataset(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)

    analytics = service.get_media_file_analytics()

    payload = analytics.to_dict()
    assert payload["totals"] == {"files_tracked": 0, "duplicate_hash_groups": 0}
    assert payload["by_status"] == {"INGESTED": 0, "PROCESSED": 0, "DELETED": 0}
    assert payload["ingested_per_day"] == []
    assert payload["deleted_per_day"] == []
    assert payload["reappearances_per_day"] == []
    assert payload["window"] == {"mode": "all_time"}


def test_media_file_analytics_counts_and_status_distribution(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    base = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)

    with session_factory.begin() as session:
        _add_media_file(
            session,
            current_path="/a.jpg",
            discovered_at=base,
            status=MediaFileStatus.INGESTED,
            hash_sha256="h1" * 32,
        )
        _add_media_file(
            session,
            current_path="/b.jpg",
            discovered_at=base + timedelta(minutes=1),
            status=MediaFileStatus.PROCESSED,
            hash_sha256="h2" * 32,
        )
        _add_media_file(
            session,
            current_path="/c.jpg",
            discovered_at=base + timedelta(minutes=2),
            status=MediaFileStatus.DELETED,
            hash_sha256="h3" * 32,
            deleted_at=base + timedelta(minutes=2),
        )

    analytics = service.get_media_file_analytics().to_dict()

    assert analytics["totals"]["files_tracked"] == 3
    assert analytics["by_status"] == {"INGESTED": 1, "PROCESSED": 1, "DELETED": 1}


def test_media_file_analytics_time_series_and_hash_groups(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    d1 = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
    d2 = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)

    with session_factory.begin() as session:
        # Duplicate hash group across two distinct paths.
        _add_media_file(
            session,
            current_path="/dup/one.jpg",
            discovered_at=d1,
            status=MediaFileStatus.INGESTED,
            hash_sha256="a" * 64,
        )
        _add_media_file(
            session,
            current_path="/dup/two.jpg",
            discovered_at=d2,
            status=MediaFileStatus.PROCESSED,
            hash_sha256="a" * 64,
        )
        # Non-duplicate hash.
        _add_media_file(
            session,
            current_path="/single/three.jpg",
            discovered_at=d2,
            status=MediaFileStatus.DELETED,
            hash_sha256="b" * 64,
            deleted_at=d2,
        )

    analytics = service.get_media_file_analytics().to_dict()

    assert analytics["totals"]["duplicate_hash_groups"] == 1
    assert analytics["ingested_per_day"] == [
        {"day": "2026-03-01", "count": 1},
        {"day": "2026-03-02", "count": 1},
    ]
    assert analytics["deleted_per_day"] == [{"day": "2026-03-02", "count": 1}]


def test_media_file_analytics_reappearances_per_day_counts_events(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    base = datetime(2026, 3, 5, 8, 0, tzinfo=UTC)
    target = "/reappear/a.jpg"

    with session_factory.begin() as session:
        _add_media_file(
            session,
            current_path=target,
            discovered_at=base,
            status=MediaFileStatus.DELETED,
            hash_sha256="d" * 64,
            deleted_at=base,
        )
        _add_media_file(
            session,
            current_path=target,
            discovered_at=base + timedelta(hours=1),
            status=MediaFileStatus.INGESTED,
            hash_sha256="e" * 64,
        )
        _add_media_file(
            session,
            current_path="/reappear/a-renamed.jpg",
            discovered_path=target,
            discovered_at=base + timedelta(days=1),
            status=MediaFileStatus.PROCESSED,
            hash_sha256="f" * 64,
        )

    analytics = service.get_media_file_analytics().to_dict()

    assert analytics["reappearances_per_day"] == [
        {"day": "2026-03-05", "count": 1},
        {"day": "2026-03-06", "count": 1},
    ]
