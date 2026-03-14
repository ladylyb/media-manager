"""Persistence helpers for durable admin benchmark runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import uuid
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.persistence.base import transactional_session
from media_manager.app.persistence.models import BenchmarkRun, BenchmarkRunStatus, BenchmarkRunType

_MAX_ERROR_MESSAGE_LEN = 4_096


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class BenchmarkRunSnapshot:
    benchmark_run_id: str
    operation_run_id: str
    benchmark_type: str
    status: str
    parameters: dict[str, object]
    report_payload: dict[str, object] | None
    summary_payload: dict[str, object] | None
    cleanup_status: str | None
    cleanup_error: str | None
    error_message: str | None
    queued_at: str
    started_at: str | None
    completed_at: str | None
    cancel_requested_at: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "benchmark_run_id": self.benchmark_run_id,
            "operation_run_id": self.operation_run_id,
            "benchmark_type": self.benchmark_type,
            "status": self.status,
            "parameters": dict(self.parameters),
            "report_payload": self.report_payload,
            "summary_payload": self.summary_payload,
            "cleanup_status": self.cleanup_status,
            "cleanup_error": self.cleanup_error,
            "error_message": self.error_message,
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "cancel_requested_at": self.cancel_requested_at,
        }


class BenchmarkRunStore:
    """Durable benchmark queue with explicit claim/start/complete/fail boundaries."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create(
        self,
        *,
        operation_run_id: uuid.UUID,
        benchmark_type: BenchmarkRunType,
        parameters: dict[str, object],
    ) -> BenchmarkRunSnapshot:
        with transactional_session(self._session_factory) as session:
            row = BenchmarkRun(
                operation_run_id=operation_run_id,
                benchmark_type=benchmark_type,
                status=BenchmarkRunStatus.QUEUED,
                parameters=dict(parameters),
                queued_at=_now_utc(),
                created_at=_now_utc(),
                updated_at=_now_utc(),
            )
            session.add(row)
            session.flush()
            return self._to_snapshot(row)

    def request_cancel(self, operation_run_id: uuid.UUID) -> BenchmarkRunSnapshot:
        with transactional_session(self._session_factory) as session:
            row = self._get_by_operation_run_id_for_update(session, operation_run_id)
            if row.status in {BenchmarkRunStatus.COMPLETED, BenchmarkRunStatus.FAILED, BenchmarkRunStatus.CANCELLED}:
                return self._to_snapshot(row)
            row.status = BenchmarkRunStatus.CANCEL_REQUESTED
            row.cancel_requested_at = _now_utc()
            row.updated_at = _now_utc()
            session.flush()
            return self._to_snapshot(row)

    def claim_next(self) -> BenchmarkRunSnapshot | None:
        with transactional_session(self._session_factory) as session:
            stmt = (
                select(BenchmarkRun)
                .where(
                    (BenchmarkRun.status == BenchmarkRunStatus.QUEUED)
                    | and_(
                        BenchmarkRun.status == BenchmarkRunStatus.CANCEL_REQUESTED,
                        BenchmarkRun.started_at.is_(None),
                    )
                )
                .order_by(BenchmarkRun.queued_at.asc(), BenchmarkRun.id.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            row = session.scalar(stmt)
            if row is None:
                return None
            if row.status == BenchmarkRunStatus.CANCEL_REQUESTED:
                row.status = BenchmarkRunStatus.CANCELLED
                row.completed_at = _now_utc()
                row.updated_at = _now_utc()
                session.flush()
                return self._to_snapshot(row)
            row.status = BenchmarkRunStatus.RUNNING
            row.started_at = _now_utc()
            row.updated_at = _now_utc()
            session.flush()
            return self._to_snapshot(row)

    def abandon_stale_running(self, *, stale_after: timedelta) -> list[BenchmarkRunSnapshot]:
        cutoff = _now_utc() - stale_after
        with transactional_session(self._session_factory) as session:
            rows = session.scalars(
                select(BenchmarkRun)
                .where(
                    BenchmarkRun.status.in_((BenchmarkRunStatus.RUNNING, BenchmarkRunStatus.CANCEL_REQUESTED)),
                    BenchmarkRun.started_at.is_not(None),
                    BenchmarkRun.completed_at.is_(None),
                    BenchmarkRun.started_at < cutoff,
                )
                .with_for_update(skip_locked=True)
            ).all()
            snapshots: list[BenchmarkRunSnapshot] = []
            for row in rows:
                row.status = BenchmarkRunStatus.FAILED
                row.error_message = "Benchmark worker stopped before completion; marked failed at stale boundary."
                row.cleanup_status = "ABANDONED"
                row.completed_at = _now_utc()
                row.updated_at = _now_utc()
                session.flush()
                snapshots.append(self._to_snapshot(row))
            return snapshots

    def complete(
        self,
        operation_run_id: uuid.UUID,
        *,
        summary_payload: dict[str, object],
        report_payload: dict[str, object],
        cleanup_status: str = "COMPLETED",
        cleanup_error: str | None = None,
    ) -> BenchmarkRunSnapshot:
        with transactional_session(self._session_factory) as session:
            row = self._get_by_operation_run_id_for_update(session, operation_run_id)
            row.status = BenchmarkRunStatus.COMPLETED
            row.summary_payload = dict(summary_payload)
            row.report_payload = dict(report_payload)
            row.cleanup_status = cleanup_status
            row.cleanup_error = cleanup_error
            row.completed_at = _now_utc()
            row.updated_at = _now_utc()
            session.flush()
            return self._to_snapshot(row)

    def cancel_running(
        self,
        operation_run_id: uuid.UUID,
        *,
        cleanup_status: str = "CANCELLED",
        cleanup_error: str | None = None,
    ) -> BenchmarkRunSnapshot:
        with transactional_session(self._session_factory) as session:
            row = self._get_by_operation_run_id_for_update(session, operation_run_id)
            row.status = BenchmarkRunStatus.CANCELLED
            row.cleanup_status = cleanup_status
            row.cleanup_error = cleanup_error
            row.completed_at = _now_utc()
            row.updated_at = _now_utc()
            session.flush()
            return self._to_snapshot(row)

    def fail(
        self,
        operation_run_id: uuid.UUID,
        *,
        error_message: str,
        cleanup_status: str = "FAILED",
        cleanup_error: str | None = None,
        summary_payload: dict[str, object] | None = None,
        report_payload: dict[str, object] | None = None,
    ) -> BenchmarkRunSnapshot:
        with transactional_session(self._session_factory) as session:
            row = self._get_by_operation_run_id_for_update(session, operation_run_id)
            row.status = BenchmarkRunStatus.FAILED
            row.error_message = (error_message or "")[:_MAX_ERROR_MESSAGE_LEN]
            row.cleanup_status = cleanup_status
            row.cleanup_error = cleanup_error
            row.summary_payload = dict(summary_payload or {})
            row.report_payload = dict(report_payload or {})
            row.completed_at = _now_utc()
            row.updated_at = _now_utc()
            session.flush()
            return self._to_snapshot(row)

    def get(self, operation_run_id: uuid.UUID) -> BenchmarkRunSnapshot | None:
        with self._session_factory() as session:
            row = session.scalar(select(BenchmarkRun).where(BenchmarkRun.operation_run_id == operation_run_id))
            return None if row is None else self._to_snapshot(row)

    def list_history(self, *, limit: int = 50) -> list[BenchmarkRunSnapshot]:
        bounded_limit = max(1, min(200, int(limit)))
        with self._session_factory() as session:
            rows = session.scalars(
                select(BenchmarkRun).order_by(BenchmarkRun.queued_at.desc(), BenchmarkRun.id.desc()).limit(bounded_limit)
            ).all()
        return [self._to_snapshot(row) for row in rows]

    def is_cancel_requested(self, operation_run_id: uuid.UUID) -> bool:
        with self._session_factory() as session:
            row = session.scalar(select(BenchmarkRun).where(BenchmarkRun.operation_run_id == operation_run_id))
            if row is None:
                return False
            return row.status == BenchmarkRunStatus.CANCEL_REQUESTED

    def _get_by_operation_run_id_for_update(self, session: Session, operation_run_id: uuid.UUID) -> BenchmarkRun:
        row = session.scalar(
            select(BenchmarkRun).where(BenchmarkRun.operation_run_id == operation_run_id).with_for_update()
        )
        if row is None:
            raise ValueError(f"benchmark operation_run_id not found: {operation_run_id}")
        return row

    def _to_snapshot(self, row: BenchmarkRun) -> BenchmarkRunSnapshot:
        return BenchmarkRunSnapshot(
            benchmark_run_id=str(row.id),
            operation_run_id=str(row.operation_run_id),
            benchmark_type=row.benchmark_type.value,
            status=row.status.value,
            parameters=dict(row.parameters or {}),
            report_payload=dict(row.report_payload or {}) if row.report_payload is not None else None,
            summary_payload=dict(row.summary_payload or {}) if row.summary_payload is not None else None,
            cleanup_status=row.cleanup_status,
            cleanup_error=row.cleanup_error,
            error_message=row.error_message,
            queued_at=row.queued_at.isoformat(),
            started_at=row.started_at.isoformat() if row.started_at is not None else None,
            completed_at=row.completed_at.isoformat() if row.completed_at is not None else None,
            cancel_requested_at=row.cancel_requested_at.isoformat() if row.cancel_requested_at is not None else None,
        )
