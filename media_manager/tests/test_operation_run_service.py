from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from media_manager.app.persistence.models import OperationRun
from media_manager.app.persistence.models import OperationRunStatus, OperationRunType
from media_manager.app.persistence.operation_runs import OperationRunService


def test_operation_run_service_start_complete_and_fail(session_factory) -> None:
    service = OperationRunService(session_factory)

    started = service.start(
        operation_type=OperationRunType.INGEST,
        context={"folder_path": "/dataset", "dry_run": True},
    )
    assert started.status == OperationRunStatus.STARTED.value
    operation_run_id = UUID(started.operation_run_id)

    completed = service.complete(operation_run_id)
    assert completed.status == OperationRunStatus.COMPLETED.value
    assert completed.completed_at is not None

    started_fail = service.start(
        operation_type=OperationRunType.APPLY,
        context={"run_id": "00000000-0000-0000-0000-000000000000"},
    )
    failed = service.fail(UUID(started_fail.operation_run_id), error_message="boom")
    assert failed.status == OperationRunStatus.FAILED.value
    assert failed.error_message == "boom"


def test_operation_run_service_history_filters(session_factory) -> None:
    service = OperationRunService(session_factory)

    started_ingest = service.start(operation_type=OperationRunType.INGEST, context={})
    service.complete(UUID(started_ingest.operation_run_id))
    started_plan = service.start(operation_type=OperationRunType.PLAN, context={})
    service.fail(UUID(started_plan.operation_run_id), error_message="plan-failed")

    all_rows = service.list_history(limit=50)
    assert len(all_rows) >= 2

    ingest_rows = service.list_history(limit=50, operation_type=OperationRunType.INGEST)
    assert len(ingest_rows) >= 1
    assert all(item.operation_type == OperationRunType.INGEST.value for item in ingest_rows)

    failed_rows = service.list_history(limit=50, status=OperationRunStatus.FAILED)
    assert len(failed_rows) >= 1
    assert all(item.status == OperationRunStatus.FAILED.value for item in failed_rows)


def test_operation_run_service_reconciles_only_stale_started_runs_before_today(session_factory) -> None:
    service = OperationRunService(session_factory)

    stale = service.start(operation_type=OperationRunType.INGEST, context={})
    current = service.start(operation_type=OperationRunType.PLAN, context={})
    completed = service.start(operation_type=OperationRunType.APPLY, context={})
    service.complete(UUID(completed.operation_run_id))
    failed = service.start(operation_type=OperationRunType.TAG_ENRICHMENT, context={})
    service.fail(UUID(failed.operation_run_id), error_message="boom")

    now_utc = datetime.now(timezone.utc)
    yesterday = now_utc - timedelta(days=1, hours=1)

    with session_factory.begin() as session:
        stale_row = session.scalar(select(OperationRun).where(OperationRun.id == UUID(stale.operation_run_id)))
        current_row = session.scalar(select(OperationRun).where(OperationRun.id == UUID(current.operation_run_id)))
        assert stale_row is not None
        assert current_row is not None
        stale_row.started_at = yesterday
        stale_row.updated_at = yesterday
        current_row.started_at = now_utc
        current_row.updated_at = now_utc

    result = service.reconcile_stale_started_runs()

    assert result.updated_count == 1
    assert result.include_current_day is False

    with session_factory() as session:
        stale_row = session.scalar(select(OperationRun).where(OperationRun.id == UUID(stale.operation_run_id)))
        current_row = session.scalar(select(OperationRun).where(OperationRun.id == UUID(current.operation_run_id)))
        completed_row = session.scalar(select(OperationRun).where(OperationRun.id == UUID(completed.operation_run_id)))
        failed_row = session.scalar(select(OperationRun).where(OperationRun.id == UUID(failed.operation_run_id)))

    assert stale_row is not None
    assert stale_row.status == OperationRunStatus.FAILED
    assert stale_row.completed_at is not None
    assert stale_row.error_message is not None
    assert "stale-run cleanup" in stale_row.error_message
    assert current_row is not None
    assert current_row.status == OperationRunStatus.STARTED
    assert completed_row is not None
    assert completed_row.status == OperationRunStatus.COMPLETED
    assert failed_row is not None
    assert failed_row.status == OperationRunStatus.FAILED


def test_operation_run_service_reconcile_can_include_current_day_and_is_idempotent(session_factory) -> None:
    service = OperationRunService(session_factory)

    current = service.start(operation_type=OperationRunType.INTEGRITY_SCAN, context={})

    first = service.reconcile_stale_started_runs(include_current_day=True)
    second = service.reconcile_stale_started_runs(include_current_day=True)

    assert first.updated_count == 1
    assert first.include_current_day is True
    assert second.updated_count == 0

    with session_factory() as session:
        current_row = session.scalar(select(OperationRun).where(OperationRun.id == UUID(current.operation_run_id)))

    assert current_row is not None
    assert current_row.status == OperationRunStatus.FAILED
    assert current_row.completed_at is not None
