from __future__ import annotations

from datetime import UTC, datetime, timedelta

from media_manager.app.persistence.models import CanonicalRecomputeRun, MediaFile, MediaFileStatus, Run, RunStateDB
from media_manager.app.persistence.operator_console import OperatorConsoleReadService


def test_dry_run_audit_returns_best_effort_candidates(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)
    started = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)

    with session_factory.begin() as session:
        run = Run(state=RunStateDB.PLANNED, created_at=started, updated_at=started + timedelta(minutes=1))
        session.add(run)
        session.flush()
        session.add(
            CanonicalRecomputeRun(
                policy_name="FIRST_SEEN",
                policy_version="v1",
                mode="DRY_RUN",
                status="COMPLETED",
                started_at=started + timedelta(seconds=30),
                completed_at=started + timedelta(minutes=1),
                scanned_count=1,
                changed_count=0,
                failed_count=0,
                applied_count=0,
            )
        )
        session.add(
            MediaFile(
                discovered_path="/dataset/a.jpg",
                current_path="/dataset/a.jpg",
                size_bytes=10,
                hash_sha256="a" * 64,
                status=MediaFileStatus.INGESTED.value,
                discovered_at=started + timedelta(seconds=10),
                ingested_at=started + timedelta(seconds=40),
            )
        )

    payload = service.get_dry_run_side_effect_audit(limit=10).to_dict()

    assert payload["coverage"] == "BEST_EFFORT"
    assert payload["candidates"]
    assert payload["candidates"][0]["confidence"] in {"LOW", "MEDIUM"}
    assert payload["limitations"]


def test_dry_run_audit_rejects_invalid_window_order(session_factory) -> None:
    service = OperatorConsoleReadService(session_factory)

    try:
        service.get_dry_run_side_effect_audit(start="2026-03-02T00:00:00+00:00", end="2026-03-01T00:00:00+00:00")
    except ValueError as exc:
        assert "start must be <= end" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid time window ordering")
