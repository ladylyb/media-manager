"""Persistence helpers for duplicate reclaim review state."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.core.logging_config import get_logger
from media_manager.app.persistence.base import transactional_session
from media_manager.app.persistence.models import DuplicateReclaimRecord, DuplicateReclaimStatus

LOGGER = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class DuplicateReclaimService:
    """Store reclaim readiness without mutating files."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def set_reclaim_status(
        self,
        *,
        content_id: UUID,
        reclaim_status: str,
        reviewed_by: str | None = None,
    ) -> dict[str, object]:
        normalized = DuplicateReclaimStatus(reclaim_status.strip().upper())
        with transactional_session(self._session_factory) as session:
            row = session.get(DuplicateReclaimRecord, content_id)
            now = _utcnow()
            prior_status = row.reclaim_status if row is not None else None
            if row is None:
                row = DuplicateReclaimRecord(
                    content_id=content_id,
                    reclaim_status=normalized.value,
                    reviewed_at=now,
                    reviewed_by=(reviewed_by or "").strip() or None,
                    archive_path=None,
                    reclaimed_at=None,
                    expires_at=None,
                    restored_at=None,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.reclaim_status = normalized.value
                row.reviewed_at = now
                row.reviewed_by = (reviewed_by or "").strip() or None
                row.updated_at = now

            LOGGER.debug(
                "duplicate_reclaim_debug: persisted reclaim review state",
                extra={
                    "stage": "duplicate_reclaim_review_persisted",
                    "content_id": str(content_id),
                    "prior_reclaim_status": prior_status or "",
                    "next_reclaim_status": row.reclaim_status,
                    "reviewed_by": row.reviewed_by or "",
                },
            )

            return {
                "content_id": str(content_id),
                "reclaim_status": row.reclaim_status,
                "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at is not None else None,
                "reviewed_by": row.reviewed_by,
            }
