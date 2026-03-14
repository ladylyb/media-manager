"""Ingestion service for Phase 13 ledger + legacy identity architecture."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.core.hashing import sha256_file
from media_manager.app.core.logging_config import get_logger
import media_manager.app.core.metadata_extractor as metadata_extractor
from media_manager.app.observability import record_ingest_metrics, record_ingest_structured_metrics
from media_manager.app.persistence.base import transactional_session
from media_manager.app.persistence.models import (
    FileContent,
    FileInstance,
    FileInstanceStatus,
    MediaFile,
    MediaFileStatus,
    MediaMetadata,
)

logger = get_logger(__name__)


_HASH_PREFIX_LEN = 12
_VALIDATION_SAMPLE_LIMIT = 100


@dataclass(frozen=True)
class IngestSummary:
    files_scanned: int
    new_contents: int
    new_instances: int
    duplicates_detected: int
    metadata_extracted: int
    duration_s: float

    def to_dict(self) -> dict[str, int | float]:
        return {
            "files_scanned": self.files_scanned,
            "new_contents": self.new_contents,
            "new_instances": self.new_instances,
            "duplicates_detected": self.duplicates_detected,
            "metadata_extracted": self.metadata_extracted,
            "duration_s": self.duration_s,
        }


@dataclass(frozen=True)
class IngestValidationDelta:
    """Read-only ingest diff counts for validate/dry-run mode."""

    would_insert: int
    would_update: int
    would_mark_deleted: int
    hash_mismatch_observed: int
    would_reappear_after_delete: int

    def to_dict(self) -> dict[str, int]:
        return {
            "would_insert": self.would_insert,
            "would_update": self.would_update,
            "would_mark_deleted": self.would_mark_deleted,
            "hash_mismatch_observed": self.hash_mismatch_observed,
            "would_reappear_after_delete": self.would_reappear_after_delete,
        }


@dataclass(frozen=True)
class IngestValidationSample:
    """Sample row for dry-run/validation delta details."""

    current_path: str
    status: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "current_path": self.current_path,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class IngestValidationReport:
    """Deterministic ingest validation payload with no persistent writes."""

    mode: str
    root_path: str
    generated_at: str
    files_scanned: int
    files_missing_during_scan: int
    delta: IngestValidationDelta
    would_insert_samples: tuple[IngestValidationSample, ...]
    would_update_samples: tuple[IngestValidationSample, ...]
    would_mark_deleted_samples: tuple[IngestValidationSample, ...]
    hash_mismatch_samples: tuple[IngestValidationSample, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "root_path": self.root_path,
            "generated_at": self.generated_at,
            "scan": {
                "files_scanned": self.files_scanned,
                "files_missing_during_scan": self.files_missing_during_scan,
            },
            "delta": self.delta.to_dict(),
            "samples": {
                "would_insert": [sample.to_dict() for sample in self.would_insert_samples],
                "would_update": [sample.to_dict() for sample in self.would_update_samples],
                "would_mark_deleted": [sample.to_dict() for sample in self.would_mark_deleted_samples],
                "hash_mismatch_observed": [sample.to_dict() for sample in self.hash_mismatch_samples],
            },
            "warnings": list(self.warnings),
        }


@dataclass
class _IngestLatencySamples:
    hash_latencies_ms: list[float]
    db_write_latencies_ms: list[float]


@dataclass
class _ValidationWorkingSet:
    files_scanned: int = 0
    files_missing_during_scan: int = 0
    would_insert: int = 0
    would_update: int = 0
    would_mark_deleted: int = 0
    hash_mismatch_observed: int = 0
    would_reappear_after_delete: int = 0
    warnings: list[str] | None = None
    would_insert_samples: list[IngestValidationSample] | None = None
    would_update_samples: list[IngestValidationSample] | None = None
    would_mark_deleted_samples: list[IngestValidationSample] | None = None
    hash_mismatch_samples: list[IngestValidationSample] | None = None

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []
        if self.would_insert_samples is None:
            self.would_insert_samples = []
        if self.would_update_samples is None:
            self.would_update_samples = []
        if self.would_mark_deleted_samples is None:
            self.would_mark_deleted_samples = []
        if self.hash_mismatch_samples is None:
            self.hash_mismatch_samples = []

    def to_report(self, *, root_path: str) -> IngestValidationReport:
        return IngestValidationReport(
            mode="VALIDATION_ONLY",
            root_path=root_path,
            generated_at=datetime.now(UTC).isoformat(),
            files_scanned=self.files_scanned,
            files_missing_during_scan=self.files_missing_during_scan,
            delta=IngestValidationDelta(
                would_insert=self.would_insert,
                would_update=self.would_update,
                would_mark_deleted=self.would_mark_deleted,
                hash_mismatch_observed=self.hash_mismatch_observed,
                would_reappear_after_delete=self.would_reappear_after_delete,
            ),
            would_insert_samples=tuple(self.would_insert_samples or []),
            would_update_samples=tuple(self.would_update_samples or []),
            would_mark_deleted_samples=tuple(self.would_mark_deleted_samples or []),
            hash_mismatch_samples=tuple(self.hash_mismatch_samples or []),
            warnings=tuple(self.warnings or []),
        )


def _append_validation_sample(
    bucket: list[IngestValidationSample],
    *,
    current_path: str,
    status: str | None = None,
    detail: str | None = None,
) -> None:
    if len(bucket) >= _VALIDATION_SAMPLE_LIMIT:
        return
    bucket.append(IngestValidationSample(current_path=current_path, status=status, detail=detail))


def _upsert_media_file_ledger(
    session: Session,
    *,
    absolute_path: str,
    digest: str,
    size_bytes: int,
) -> None:
    """
    media_file is an ingestion tracking ledger only.
    Canonical authority remains in legacy tables.
    No canonical decisions are mirrored here in Phase 13.
    """

    row = session.scalar(
        select(MediaFile)
        .where(
            MediaFile.current_path == absolute_path,
            # Deleted rows are immutable historical facts. Reappearance creates a new
            # live ledger row rather than mutating the deleted row in place.
            MediaFile.status != MediaFileStatus.DELETED.value,
        )
        .with_for_update()
    )
    if row is None:
        prior_deleted_count = int(
            session.scalar(
                select(func.count())
                .select_from(MediaFile)
                .where(
                    MediaFile.current_path == absolute_path,
                    MediaFile.status == MediaFileStatus.DELETED.value,
                )
            )
            or 0
        )
        if prior_deleted_count > 0:
            logger.info(
                "Path reappeared after delete",
                extra={
                    "phase": "ingest",
                    "action": "REAPPEARED_AFTER_DELETE",
                    "filename": absolute_path,
                    "files_count": 1,
                    "codes_extracted": f"prior_deleted_rows={prior_deleted_count}",
                },
            )
        session.add(
            MediaFile(
                discovered_path=absolute_path,
                current_path=absolute_path,
                size_bytes=size_bytes,
                hash_sha256=digest,
                discovered_at=func.now(),
                status=MediaFileStatus.INGESTED.value,
                quarantined_at=None,
                deleted_at=None,
                ingested_at=func.now(),
            )
        )
        return

    # Preserve existing lifecycle state for live rows. Ingest refreshes ledger
    # observation time, but it must not roll PROCESSED rows back to INGESTED.
    row.current_path = absolute_path
    row.size_bytes = size_bytes
    # Keep lifecycle constraint safe even if application and DB clocks drift:
    # ingested_at must never precede discovered_at.
    row.ingested_at = func.greatest(func.now(), row.discovered_at)
    # Preserve discovered_at as first-seen fact for this ledger row.

    if row.hash_sha256 is None:
        row.hash_sha256 = digest
        return

    # Never overwrite a durable stored hash in Phase 13 ingest. Mismatches are
    # observable facts for later reconciliation phases, not auto-repair here.
    if row.hash_sha256 != digest:
        logger.warning(
            "Ingest hash mismatch observed for existing ledger row",
            extra={
                "phase": "ingest",
                "action": "HASH_MISMATCH",
                "filename": absolute_path,
                "files_count": 1,
                "file_hash": digest[:_HASH_PREFIX_LEN],
                "codes_extracted": (
                    f"stored_hash_prefix={row.hash_sha256[:_HASH_PREFIX_LEN]},"
                    f"computed_hash_prefix={digest[:_HASH_PREFIX_LEN]},file_size={size_bytes}"
                ),
            },
        )


def _mark_missing_paths_deleted_for_root(
    session: Session,
    *,
    root: Path,
    observed_paths: set[str],
) -> None:
    root_path = root.resolve(strict=False)
    live_rows = session.scalars(
        select(MediaFile)
        .where(
            MediaFile.current_path.is_not(None),
            MediaFile.status.in_([MediaFileStatus.INGESTED.value, MediaFileStatus.PROCESSED.value]),
        )
        .with_for_update()
    ).all()
    for row in live_rows:
        path = row.current_path
        if path is None:
            continue
        path_obj = Path(path)
        # DELETED is strictly a filesystem observation for authoritative root scans.
        try:
            within_root = path_obj.resolve(strict=False).is_relative_to(root_path)
        except Exception:
            within_root = False
        if not within_root:
            continue
        if path in observed_paths:
            continue
        row.status = MediaFileStatus.DELETED.value
        row.deleted_at = func.now()


def validate_paths_in_session(
    session: Session,
    files: list[Path],
    *,
    authoritative_root: Path | None = None,
) -> IngestValidationReport:
    """
    Compute ingest deltas without mutating durable state.

    This intentionally reuses ingest comparison rules so dry-run and ingest stay
    in sync while preserving a strict zero-write guarantee.
    """

    observed_paths: set[str] = set()
    working = _ValidationWorkingSet()

    for candidate in files:
        if not candidate.exists() or not candidate.is_file():
            continue

        absolute_path = str(candidate.resolve(strict=False))
        try:
            size_bytes = int(candidate.stat().st_size)
            digest = sha256_file(candidate)
            working.files_scanned += 1
        except OSError:
            working.files_missing_during_scan += 1
            assert working.warnings is not None
            working.warnings.append(f"File disappeared during scan: {absolute_path}")
            continue

        observed_paths.add(absolute_path)
        row = session.scalar(
            select(MediaFile).where(
                MediaFile.current_path == absolute_path,
                MediaFile.status != MediaFileStatus.DELETED.value,
            )
        )
        if row is None:
            working.would_insert += 1
            assert working.would_insert_samples is not None
            _append_validation_sample(working.would_insert_samples, current_path=absolute_path, status="INGESTED")
            prior_deleted_count = int(
                session.scalar(
                    select(func.count())
                    .select_from(MediaFile)
                    .where(
                        MediaFile.current_path == absolute_path,
                        MediaFile.status == MediaFileStatus.DELETED.value,
                    )
                )
                or 0
            )
            if prior_deleted_count > 0:
                working.would_reappear_after_delete += 1
            continue

        # For existing live rows ingest would refresh size/current_path/ingested_at
        # and potentially backfill missing hash. We record this as a prospective update.
        working.would_update += 1
        assert working.would_update_samples is not None
        _append_validation_sample(working.would_update_samples, current_path=absolute_path, status=row.status)

        if row.hash_sha256 is not None and row.hash_sha256 != digest:
            working.hash_mismatch_observed += 1
            assert working.hash_mismatch_samples is not None
            _append_validation_sample(
                working.hash_mismatch_samples,
                current_path=absolute_path,
                status=row.status,
                detail=(
                    f"stored_hash_prefix={row.hash_sha256[:_HASH_PREFIX_LEN]},"
                    f"computed_hash_prefix={digest[:_HASH_PREFIX_LEN]},file_size={size_bytes}"
                ),
            )

    if authoritative_root is not None:
        root_path = authoritative_root.resolve(strict=False)
        live_rows = session.scalars(
            select(MediaFile).where(
                MediaFile.current_path.is_not(None),
                MediaFile.status.in_([MediaFileStatus.INGESTED.value, MediaFileStatus.PROCESSED.value]),
            )
        ).all()
        for row in live_rows:
            path = row.current_path
            if path is None:
                continue
            path_obj = Path(path)
            try:
                within_root = path_obj.resolve(strict=False).is_relative_to(root_path)
            except Exception:
                within_root = False
            if not within_root or path in observed_paths:
                continue
            working.would_mark_deleted += 1
            assert working.would_mark_deleted_samples is not None
            _append_validation_sample(
                working.would_mark_deleted_samples,
                current_path=path,
                status=MediaFileStatus.DELETED.value,
            )

    root_display = (
        str(authoritative_root.resolve(strict=False))
        if authoritative_root is not None
        else ",".join(sorted(p.resolve(strict=False).as_posix() for p in files))
    )
    return working.to_report(root_path=root_display)


def ingest_paths_in_session(
    session: Session,
    files: list[Path],
    *,
    authoritative_root: Path | None = None,
    latency_samples: _IngestLatencySamples | None = None,
) -> IngestSummary:
    t_start = perf_counter()
    scanned = 0
    new_contents = 0
    new_instances = 0
    duplicates = 0
    metadata_extracted = 0
    observed_paths: set[str] = set()

    for candidate in files:
        if not candidate.exists() or not candidate.is_file():
            continue
        absolute_path = str(candidate.resolve(strict=False))
        try:
            size_bytes = int(candidate.stat().st_size)
            scanned += 1
            t_hash_start = perf_counter()
            # TODO(phase14): if ingest throughput demands it, move to a batched
            # hash/db pipeline. Phase 13 keeps per-file hashing for correctness.
            digest = sha256_file(candidate)
            hash_latency_ms = (perf_counter() - t_hash_start) * 1000.0
            if latency_samples is not None:
                latency_samples.hash_latencies_ms.append(hash_latency_ms)
        except OSError:
            logger.warning(
                "File disappeared during ingest; skipping candidate",
                extra={
                    "phase": "ingest",
                    "action": "FILE_MISSING_DURING_INGEST",
                    "filename": absolute_path,
                    "files_count": 1,
                },
            )
            continue

        observed_paths.add(absolute_path)

        t_db_start = perf_counter()
        # media_file remains a pure ingest ledger. Canonical winner/duplicate
        # decisions, including same-hash cross-path reasoning, live elsewhere.
        # Hash mismatch reconciliation is intentionally deferred past Phase 13.
        _upsert_media_file_ledger(session, absolute_path=absolute_path, digest=digest, size_bytes=size_bytes)

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
        db_write_latency_ms = (perf_counter() - t_db_start) * 1000.0
        if latency_samples is not None:
            latency_samples.db_write_latencies_ms.append(db_write_latency_ms)

    if authoritative_root is not None:
        _mark_missing_paths_deleted_for_root(session, root=authoritative_root, observed_paths=observed_paths)

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
        files = self.collect_files(root)
        authoritative_root = root if root.is_dir() else None
        return self.ingest_paths(files, authoritative_root=authoritative_root)

    def validate_path(self, root: Path) -> IngestValidationReport:
        files = self.collect_files(root)
        authoritative_root = root if root.is_dir() else None
        return self.validate_paths(files, authoritative_root=authoritative_root)

    def ingest_paths(self, files: list[Path], *, authoritative_root: Path | None = None) -> IngestSummary:
        latency_samples = _IngestLatencySamples(hash_latencies_ms=[], db_write_latencies_ms=[])
        with transactional_session(self._session_factory) as session:
            summary = ingest_paths_in_session(
                session,
                files,
                authoritative_root=authoritative_root,
                latency_samples=latency_samples,
            )
        # Ingest is not currently run-bound, so run_id is explicitly stable as "none".
        try:
            record_ingest_metrics(run_id="none", files_scanned=summary.files_scanned, new_contents=summary.new_contents)
            record_ingest_structured_metrics(
                run_id="none",
                dataset_id="unknown",
                policy_name="default",
                files_scanned=summary.files_scanned,
                new_contents=summary.new_contents,
                new_instances=summary.new_instances,
                duplicates_detected=summary.duplicates_detected,
                hash_latencies_ms=latency_samples.hash_latencies_ms,
                db_write_latencies_ms=latency_samples.db_write_latencies_ms,
            )
        except Exception:
            logger.exception("Observability metric emission failed", extra={"phase": "ingest", "action": "METRICS"})
        return summary

    def validate_paths(self, files: list[Path], *, authoritative_root: Path | None = None) -> IngestValidationReport:
        with self._session_factory() as session:
            return validate_paths_in_session(session, files, authoritative_root=authoritative_root)

    @staticmethod
    def collect_files(root: Path) -> list[Path]:
        if root.is_file():
            return [root]
        return sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.resolve(strict=False).as_posix())
