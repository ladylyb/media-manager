"""Persistence helpers for durable duplicate review state."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.persistence.models import (
    CanonicalAssignment,
    DuplicateGroupReview,
    FileContent,
    FileInstance,
    FileInstanceStatus,
)

VALID_DUPLICATE_REVIEW_STATUSES = frozenset({"looks_right", "needs_review", "not_sure"})


def compute_duplicate_group_signature(
    *,
    content_id: UUID,
    canonical_instance_id: UUID | None,
    file_instance_ids: list[UUID],
) -> str:
    ordered_ids = sorted(str(file_instance_id) for file_instance_id in file_instance_ids)
    payload = "\n".join(
        [
            str(content_id),
            str(canonical_instance_id) if canonical_instance_id is not None else "",
            *ordered_ids,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_latest_canonical_instance_id(session: Session, *, content_id: UUID) -> UUID | None:
    assignment = session.scalar(
        select(CanonicalAssignment.canonical_instance_id)
        .where(CanonicalAssignment.content_id == content_id)
        .order_by(CanonicalAssignment.assigned_at.desc(), CanonicalAssignment.assignment_id.desc())
        .limit(1)
    )
    if assignment is not None:
        return assignment
    return session.scalar(
        select(FileContent.canonical_file_instance_id).where(FileContent.content_id == content_id).limit(1)
    )


class DuplicateReviewService:
    """Create and update durable review state for duplicate groups."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def upsert_review(
        self,
        *,
        content_id: UUID,
        review_status: str,
        reviewed_canonical_instance_id: UUID,
        reviewed_by: str | None = None,
    ) -> dict[str, object]:
        normalized_status = review_status.strip().lower()
        if normalized_status not in VALID_DUPLICATE_REVIEW_STATUSES:
            raise ValueError("review_status must be one of: looks_right, needs_review, not_sure.")

        with self._session_factory() as session:
            active_instance_ids = session.scalars(
                select(FileInstance.file_instance_id)
                .where(
                    FileInstance.content_id == content_id,
                    FileInstance.status == FileInstanceStatus.ACTIVE.value,
                )
                .order_by(FileInstance.file_instance_id.asc())
            ).all()
            if len(active_instance_ids) < 2:
                raise ValueError("Duplicate group not found or no longer contains duplicates.")

            if reviewed_canonical_instance_id not in active_instance_ids:
                raise ValueError("reviewed_canonical_instance_id must belong to the current duplicate group.")

            current_canonical_instance_id = get_latest_canonical_instance_id(session, content_id=content_id)
            if current_canonical_instance_id is None:
                raise ValueError("Duplicate group does not currently have a canonical assignment.")
            if current_canonical_instance_id != reviewed_canonical_instance_id:
                raise ValueError("reviewed_canonical_instance_id must match the current canonical assignment.")

            signature = compute_duplicate_group_signature(
                content_id=content_id,
                canonical_instance_id=current_canonical_instance_id,
                file_instance_ids=active_instance_ids,
            )
            now = datetime.now(UTC)
            existing = session.get(DuplicateGroupReview, content_id)
            if existing is None:
                existing = DuplicateGroupReview(
                    content_id=content_id,
                    review_status=normalized_status,
                    reviewed_at=now,
                    reviewed_by=(reviewed_by or "").strip() or None,
                    reviewed_canonical_instance_id=reviewed_canonical_instance_id,
                    group_signature=signature,
                    created_at=now,
                    updated_at=now,
                )
                session.add(existing)
            else:
                existing.review_status = normalized_status
                existing.reviewed_at = now
                existing.reviewed_by = (reviewed_by or "").strip() or None
                existing.reviewed_canonical_instance_id = reviewed_canonical_instance_id
                existing.group_signature = signature
                existing.updated_at = now

            session.commit()
            return {
                "content_id": str(content_id),
                "review_status": existing.review_status,
                "reviewed_at": existing.reviewed_at.isoformat(),
                "reviewed_canonical_instance_id": str(reviewed_canonical_instance_id),
                "group_signature": existing.group_signature,
                "is_stale": False,
                "stale_reason": None,
            }
