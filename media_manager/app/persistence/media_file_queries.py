from __future__ import annotations

import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from media_manager.app.persistence.models import MediaFile, MediaFileStatus

# Phase 13 ledger note:
# media_file is ingestion ledger state only. It is not a canonical/duplicate authority.
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def _path_match(path: str):
    """Return a shared path predicate against both current and discovered paths."""
    return or_(MediaFile.current_path == path, MediaFile.discovered_path == path)


def _ordered_media_file_query(stmt):
    """Apply deterministic ordering for idempotent-safe batch reads."""
    return stmt.order_by(MediaFile.discovered_at.asc(), MediaFile.id.asc())


def _escape_like_prefix(value: str) -> str:
    """Escape LIKE wildcards so prefix lookups remain literal-prefix matching."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def get_rows_by_hash(session: Session, hash_prefix: str) -> list[MediaFile]:
    """Return ledger rows by SHA-256 value using exact or prefix semantics.

    Phase 13 hash policy for reads:
    - A full 64-char lowercase hex hash is treated as an exact match.
    - Otherwise, the normalized input is treated as a literal prefix.

    This is a read-only ledger helper and performs no canonical/duplicate inference.
    """
    normalized = hash_prefix.strip().lower()
    if not normalized:
        return []

    stmt = select(MediaFile).where(MediaFile.hash_sha256.is_not(None))
    if _HEX64_RE.fullmatch(normalized):
        stmt = stmt.where(MediaFile.hash_sha256 == normalized)
    else:
        escaped = _escape_like_prefix(normalized)
        stmt = stmt.where(MediaFile.hash_sha256.like(f"{escaped}%", escape="\\"))

    return session.scalars(_ordered_media_file_query(stmt)).all()


def get_history_by_path(session: Session, path: str) -> list[MediaFile]:
    """Return a ledger timeline for a path across all statuses.

    History includes rows whose `current_path` or `discovered_path` matches `path`.
    Rows are returned in durable timeline order by discovered_at ascending.
    """
    stmt = select(MediaFile).where(_path_match(path))
    return session.scalars(_ordered_media_file_query(stmt)).all()


def get_rows_by_status(session: Session, status: MediaFileStatus) -> list[MediaFile]:
    """Return ledger rows for a single Phase 13 status.

    Status meaning in this ledger-only model:
    - INGESTED: file observation recorded by ingest.
    - PROCESSED: downstream canonical evaluation completed.
    - DELETED: authoritative root scan observed missing file and recorded tombstone.

    Function is strictly read-only and does not mutate transition state.
    """
    stmt = select(MediaFile).where(MediaFile.status == status.value)
    return session.scalars(_ordered_media_file_query(stmt)).all()


def get_reappearances_after_deleted(session: Session, path: str) -> list[MediaFile]:
    """Return non-DELETED rows discovered after the latest DELETED tombstone for a path.

    This helper uses the latest `deleted_at` boundary for `path` across both
    current/discovered path columns. If no deleted baseline exists, result is empty.

    This is ledger-only history slicing; no canonical or duplicate logic is applied.
    """
    latest_deleted_at = session.scalar(
        select(func.max(MediaFile.deleted_at)).where(
            _path_match(path),
            MediaFile.status == MediaFileStatus.DELETED.value,
            MediaFile.deleted_at.is_not(None),
        )
    )
    if latest_deleted_at is None:
        return []

    stmt = (
        select(MediaFile)
        .where(
            _path_match(path),
            MediaFile.status != MediaFileStatus.DELETED.value,
            MediaFile.discovered_at > latest_deleted_at,
        )
    )
    return session.scalars(_ordered_media_file_query(stmt)).all()
