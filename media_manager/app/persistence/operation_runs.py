"""Persistence service for unified operation run logging."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.persistence.base import transactional_session
from media_manager.app.persistence.models import OperationRun, OperationRunStatus, OperationRunType

_MAX_CONTEXT_JSON_BYTES = 16_384
_MAX_ERROR_MESSAGE_LEN = 4_096


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class OperationRunSnapshot:
    operation_run_id: str
    operation_type: str
    status: str
    started_at: str
    completed_at: str | None
    linked_run_id: str | None
    context: dict[str, object]
    error_message: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "operation_run_id": self.operation_run_id,
            "operation_type": self.operation_type,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "linked_run_id": self.linked_run_id,
            "context": dict(self.context),
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class OperationRunHistoryItem:
    operation_run_id: str
    operation_type: str
    status: str
    started_at: str
    completed_at: str | None
    duration_ms: float | None
    linked_run_id: str | None
    context: dict[str, object]
    error_message: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "operation_run_id": self.operation_run_id,
            "operation_type": self.operation_type,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "linked_run_id": self.linked_run_id,
            "context": dict(self.context),
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class OperationRunReconciliationResult:
    cutoff: str
    scanned_count: int
    updated_count: int
    include_current_day: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "cutoff": self.cutoff,
            "scanned_count": self.scanned_count,
            "updated_count": self.updated_count,
            "include_current_day": self.include_current_day,
        }


def _normalize_context(context: dict[str, object]) -> dict[str, object]:
    payload = dict(context)
    encoded = json.dumps(payload, default=str, sort_keys=True)
    if len(encoded.encode("utf-8")) <= _MAX_CONTEXT_JSON_BYTES:
        return payload
    return {"truncated": True, "original_size_bytes": len(encoded.encode("utf-8"))}


class OperationRunService:
    """Durable operation-run logger with explicit start/complete/fail boundaries."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def start(
        self,
        *,
        operation_type: OperationRunType,
        context: dict[str, object],
        linked_run_id: uuid.UUID | None = None,
    ) -> OperationRunSnapshot:
        with transactional_session(self._session_factory) as session:
            row = OperationRun(
                operation_type=operation_type,
                status=OperationRunStatus.STARTED,
                started_at=_now_utc(),
                completed_at=None,
                error_message=None,
                context=_normalize_context(context),
                linked_run_id=linked_run_id,
                created_at=_now_utc(),
                updated_at=_now_utc(),
            )
            session.add(row)
            session.flush()
            return self._to_snapshot(row)

    def complete(self, operation_run_id: uuid.UUID) -> OperationRunSnapshot:
        with transactional_session(self._session_factory) as session:
            row = self._get_row_for_update(session, operation_run_id)
            row.status = OperationRunStatus.COMPLETED
            row.completed_at = _now_utc()
            row.updated_at = _now_utc()
            session.flush()
            return self._to_snapshot(row)

    def fail(self, operation_run_id: uuid.UUID, *, error_message: str) -> OperationRunSnapshot:
        with transactional_session(self._session_factory) as session:
            row = self._get_row_for_update(session, operation_run_id)
            row.status = OperationRunStatus.FAILED
            row.completed_at = _now_utc()
            row.error_message = (error_message or "")[:_MAX_ERROR_MESSAGE_LEN]
            row.updated_at = _now_utc()
            session.flush()
            return self._to_snapshot(row)

    def link_run(self, operation_run_id: uuid.UUID, *, linked_run_id: uuid.UUID | None) -> OperationRunSnapshot:
        with transactional_session(self._session_factory) as session:
            row = self._get_row_for_update(session, operation_run_id)
            row.linked_run_id = linked_run_id
            row.updated_at = _now_utc()
            session.flush()
            return self._to_snapshot(row)

    def list_history(
        self,
        *,
        limit: int,
        operation_type: OperationRunType | None = None,
        status: OperationRunStatus | None = None,
    ) -> list[OperationRunHistoryItem]:
        bounded_limit = max(1, min(200, int(limit)))
        with self._session_factory() as session:
            stmt = select(OperationRun).order_by(OperationRun.started_at.desc(), OperationRun.id.desc()).limit(bounded_limit)
            if operation_type is not None:
                stmt = stmt.where(OperationRun.operation_type == operation_type)
            if status is not None:
                stmt = stmt.where(OperationRun.status == status)
            rows = session.scalars(stmt).all()

        items: list[OperationRunHistoryItem] = []
        for row in rows:
            duration_ms: float | None = None
            if row.completed_at is not None and row.started_at is not None:
                duration_ms = (row.completed_at - row.started_at).total_seconds() * 1000.0
            items.append(
                OperationRunHistoryItem(
                    operation_run_id=str(row.id),
                    operation_type=row.operation_type.value,
                    status=row.status.value,
                    started_at=row.started_at.isoformat(),
                    completed_at=row.completed_at.isoformat() if row.completed_at is not None else None,
                    duration_ms=duration_ms,
                    linked_run_id=str(row.linked_run_id) if row.linked_run_id is not None else None,
                    context=dict(row.context or {}),
                    error_message=row.error_message,
                )
            )
        return items

    def count(self) -> int:
        with self._session_factory() as session:
            value = session.scalar(select(func.count()).select_from(OperationRun))
        return int(value or 0)

    def reconcile_stale_started_runs(self, *, include_current_day: bool = False) -> OperationRunReconciliationResult:
        now_utc = _now_utc()
        cutoff = now_utc if include_current_day else now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        stale_message = (
            "Operation run left in STARTED state after interrupted process termination; "
            "marked failed during stale-run cleanup."
        )[:_MAX_ERROR_MESSAGE_LEN]

        with transactional_session(self._session_factory) as session:
            rows = session.scalars(
                select(OperationRun)
                .where(
                    OperationRun.status == OperationRunStatus.STARTED,
                    OperationRun.started_at < cutoff,
                )
                .with_for_update(skip_locked=True)
            ).all()

            for row in rows:
                row.status = OperationRunStatus.FAILED
                row.completed_at = now_utc
                row.error_message = stale_message
                row.updated_at = now_utc

            session.flush()

        return OperationRunReconciliationResult(
            cutoff=cutoff.isoformat(),
            scanned_count=len(rows),
            updated_count=len(rows),
            include_current_day=include_current_day,
        )

    def _get_row_for_update(self, session: Session, operation_run_id: uuid.UUID) -> OperationRun:
        stmt = select(OperationRun).where(OperationRun.id == operation_run_id).with_for_update()
        row = session.scalar(stmt)
        if row is None:
            raise ValueError(f"operation_run_id not found: {operation_run_id}")
        return row

    def _to_snapshot(self, row: OperationRun) -> OperationRunSnapshot:
        return OperationRunSnapshot(
            operation_run_id=str(row.id),
            operation_type=row.operation_type.value,
            status=row.status.value,
            started_at=row.started_at.isoformat(),
            completed_at=row.completed_at.isoformat() if row.completed_at is not None else None,
            linked_run_id=str(row.linked_run_id) if row.linked_run_id is not None else None,
            context=dict(row.context or {}),
            error_message=row.error_message,
        )
