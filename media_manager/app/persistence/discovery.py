"""Legacy canonical discovery flow with Phase 13 media_file processing state updates."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from media_manager.app.canonical.factory import build_canonical_policy, resolve_default_policy_name
from media_manager.app.persistence.canonicalization import append_assignment, build_selection_context, get_active_assignment
from media_manager.app.persistence.models import FileInstance, MediaFile, MediaFileStatus


def ensure_canonical_assignment(session: Session, content_id: uuid.UUID) -> uuid.UUID | None:
    active = get_active_assignment(session, content_id)
    if active is not None:
        return active.canonical_instance_id

    instances = session.scalars(
        select(FileInstance)
        .where(FileInstance.content_id == content_id)
        .order_by(FileInstance.first_seen_at.asc(), FileInstance.absolute_path.asc(), FileInstance.file_instance_id.asc())
    ).all()
    if not instances:
        return None

    policy = build_canonical_policy(resolve_default_policy_name())
    selected = policy.select(
        str(content_id),
        instances,
        build_selection_context(session, content_id=content_id, instances=instances),
    )
    row = append_assignment(
        session,
        content_id=content_id,
        canonical_instance_id=selected.file_instance_id,
        policy_name=policy.name,
        policy_version=policy.version,
    )
    return row.canonical_instance_id


def process_discovery_paths_in_session(session: Session, files: list[Path]) -> list[str]:
    """
    media_file is an ingestion tracking ledger only.
    Canonical authority remains in legacy tables.
    No canonical decisions are mirrored here in Phase 13.
    """

    processed_paths: list[str] = []
    for candidate in files:
        if not candidate.exists() or not candidate.is_file():
            continue
        absolute_path = str(candidate.resolve(strict=False))
        instance = session.scalar(select(FileInstance).where(FileInstance.absolute_path == absolute_path).with_for_update())
        if instance is None:
            continue
        ensure_canonical_assignment(session, instance.content_id)
        processed_paths.append(absolute_path)

    unique_processed_paths = sorted(set(processed_paths))
    if unique_processed_paths:
        # Keep canonical assignment writes and INGESTED->PROCESSED transition in the
        # same DB transaction boundary to prevent partial ledger/canonical mismatch.
        # PROCESSED only means canonical evaluation completed successfully.
        # It does not indicate canonical winner/duplicate outcome.
        session.execute(
            update(MediaFile)
            .where(
                MediaFile.current_path.in_(unique_processed_paths),
                MediaFile.status == MediaFileStatus.INGESTED.value,
            )
            .values(status=MediaFileStatus.PROCESSED.value)
        )

    return unique_processed_paths


def process_all_discovery_in_session(session: Session) -> list[str]:
    rows = session.scalars(select(FileInstance.absolute_path).order_by(FileInstance.absolute_path.asc())).all()
    return process_discovery_paths_in_session(session, [Path(path) for path in rows])
