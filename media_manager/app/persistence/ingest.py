"""Ingestion service for Phase 7 identity-first architecture."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.core.hashing import sha256_file
from media_manager.app.core.logging_config import get_logger
import media_manager.app.core.metadata_extractor as metadata_extractor
from media_manager.app.persistence.base import transactional_session
from media_manager.app.persistence.models import FileContent, FileInstance, FileInstanceStatus, MediaMetadata

logger = get_logger(__name__)


@dataclass(frozen=True)
class IngestSummary:
    files_scanned: int
    new_contents: int
    new_instances: int
    duplicates_detected: int
    metadata_extracted: int
    duration_s: float


def select_canonical_instance(session: Session, content_id: uuid.UUID) -> uuid.UUID | None:
    content = session.scalar(select(FileContent).where(FileContent.content_id == content_id).with_for_update())
    if content is None:
        return None
    if content.canonical_file_instance_id is not None:
        return content.canonical_file_instance_id

    candidate = session.scalar(
        select(FileInstance)
        .where(FileInstance.content_id == content_id)
        .order_by(FileInstance.first_seen_at.asc(), FileInstance.file_instance_id.asc())
        .limit(1)
    )
    if candidate is None:
        return None
    content.canonical_file_instance_id = candidate.file_instance_id
    session.flush()
    return content.canonical_file_instance_id


def ingest_paths_in_session(session: Session, files: list[Path]) -> IngestSummary:
    t_start = perf_counter()
    scanned = 0
    new_contents = 0
    new_instances = 0
    duplicates = 0
    metadata_extracted = 0

    for candidate in files:
        if not candidate.exists() or not candidate.is_file():
            continue
        scanned += 1
        digest = sha256_file(candidate)
        absolute_path = str(candidate.resolve(strict=False))

        content = session.scalar(select(FileContent).where(FileContent.sha256_hash == digest).with_for_update())
        content_was_new = False
        if content is None:
            content = FileContent(sha256_hash=digest)
            session.add(content)
            session.flush()
            content_was_new = True
            new_contents += 1
        else:
            duplicates += 1

        instance = session.scalar(
            select(FileInstance).where(FileInstance.absolute_path == absolute_path).with_for_update()
        )
        if instance is None:
            instance = FileInstance(
                content_id=content.content_id,
                absolute_path=absolute_path,
                filesystem_id=None,
                status=FileInstanceStatus.ACTIVE.value,
            )
            session.add(instance)
            session.flush()
            new_instances += 1
        else:
            instance.content_id = content.content_id
            instance.last_seen_at = func.now()
            instance.status = FileInstanceStatus.ACTIVE.value

        if content.canonical_file_instance_id is None:
            content.canonical_file_instance_id = instance.file_instance_id

        if content_was_new:
            existing_rows = session.scalar(
                select(func.count())
                .select_from(MediaMetadata)
                .where(MediaMetadata.content_id == content.content_id)
            )
            if int(existing_rows or 0) == 0:
                rows = metadata_extractor.extract_file_metadata(candidate, digest)
                metadata_extractor.upsert_metadata_for_content(session, rows, content.content_id)
                metadata_extracted += len(rows)

        select_canonical_instance(session, content.content_id)

    duration_s = perf_counter() - t_start
    logger.info(
        "Ingest summary",
        extra={
            "phase": "ingest",
            "action": "EXTRACTED",
            "files_count": scanned,
            "duration_s": f"{duration_s:.6f}",
            "codes_extracted": (
                f"new_contents={new_contents},new_instances={new_instances},"
                f"duplicates={duplicates},metadata_rows={metadata_extracted}"
            ),
        },
    )
    return IngestSummary(
        files_scanned=scanned,
        new_contents=new_contents,
        new_instances=new_instances,
        duplicates_detected=duplicates,
        metadata_extracted=metadata_extracted,
        duration_s=duration_s,
    )


class IngestService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def ingest_path(self, root: Path) -> IngestSummary:
        return self.ingest_paths(self.collect_files(root))

    def ingest_paths(self, files: list[Path]) -> IngestSummary:
        with transactional_session(self._session_factory) as session:
            return ingest_paths_in_session(session, files)

    @staticmethod
    def collect_files(root: Path) -> list[Path]:
        if root.is_file():
            return [root]
        return sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.resolve(strict=False).as_posix())
