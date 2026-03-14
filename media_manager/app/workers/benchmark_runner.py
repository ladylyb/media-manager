"""DB-polled worker for admin benchmark execution."""

from __future__ import annotations

import logging
import os
import time
from uuid import UUID

from media_manager.app.core.config import load_environment
from media_manager.app.persistence.admin_benchmarks import run_discovery_benchmark, run_metadata_benchmark
from media_manager.app.persistence.base import create_db_engine, create_session_factory
from media_manager.app.persistence.benchmark_runs import BenchmarkRunStore
from media_manager.app.persistence.operation_runs import OperationRunService

LOGGER = logging.getLogger(__name__)


def _flag_enabled(name: str) -> bool:
    return (os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def run_once() -> bool:
    load_environment()
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    benchmark_runs = BenchmarkRunStore(session_factory)
    operation_runs = OperationRunService(session_factory)
    operation_run_id: UUID | None = None
    try:
        claimed = benchmark_runs.claim_next()
        if claimed is None:
            return False
        operation_run_id = UUID(claimed.operation_run_id)

        if claimed.status == "CANCELLED":
            operation_runs.fail(operation_run_id, error_message="Benchmark cancelled before execution.")
            return True

        if claimed.benchmark_type == "METADATA":
            result = run_metadata_benchmark(
                session_factory,
                items=int(claimed.parameters.get("items", 1000)),
                batch_size=int(claimed.parameters.get("batch_size", 250)),
                operation_run_id=claimed.operation_run_id,
            )
        elif claimed.benchmark_type == "DISCOVERY":
            result = run_discovery_benchmark(
                session_factory,
                items=int(claimed.parameters.get("items", 1000)),
                operation_run_id=claimed.operation_run_id,
            )
        else:
            raise RuntimeError(f"Unsupported benchmark type: {claimed.benchmark_type}")

        if benchmark_runs.is_cancel_requested(operation_run_id):
            benchmark_runs.cancel_running(
                operation_run_id,
                cleanup_status=result.cleanup_status,
                cleanup_error=result.cleanup_error,
            )
            operation_runs.fail(operation_run_id, error_message="Benchmark cancelled during execution.")
            return True

        benchmark_runs.complete(
            operation_run_id,
            summary_payload=result.summary,
            report_payload=result.report,
            cleanup_status=result.cleanup_status,
            cleanup_error=result.cleanup_error,
        )
        operation_runs.complete(operation_run_id)
        return True
    except Exception as exc:
        LOGGER.exception("Benchmark worker execution failed")
        try:
            if operation_run_id is not None:
                benchmark_runs.fail(
                    operation_run_id,
                    error_message=str(exc),
                    cleanup_status="FAILED",
                    cleanup_error=str(exc),
                )
        except Exception:
            LOGGER.exception("Failed to persist benchmark failure state")
        try:
            if operation_run_id is not None:
                operation_runs.fail(operation_run_id, error_message=str(exc))
        except Exception:
            LOGGER.exception("Failed to persist operation run failure state")
        return True
    finally:
        engine.dispose()


def run_forever() -> None:
    poll_interval_s = float(os.getenv("MEDIA_MANAGER_BENCHMARK_POLL_INTERVAL_SECONDS", "2.0"))
    while True:
        did_work = run_once()
        if not did_work:
            time.sleep(max(0.1, poll_interval_s))


def main() -> None:
    if not _flag_enabled("MEDIA_MANAGER_BENCHMARKS_ENABLED"):
        raise SystemExit("Benchmarks are disabled. Set MEDIA_MANAGER_BENCHMARKS_ENABLED=true to run the worker.")
    mode = (os.getenv("MEDIA_MANAGER_BENCHMARK_WORKER_MODE", "forever") or "").strip().lower()
    if mode == "once":
        run_once()
        return
    run_forever()


if __name__ == "__main__":
    main()
