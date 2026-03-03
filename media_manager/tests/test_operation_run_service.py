from __future__ import annotations

from uuid import UUID

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
