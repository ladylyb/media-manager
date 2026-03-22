"""Metadata extraction and content-keyed persistence helpers."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from media_manager.app.core.date_extraction import filename_has_date
from media_manager.app.core.naming import DEFAULT_CONTEXT, DEFAULT_OWNER
from media_manager.app.core.hashing import sha256_file
from media_manager.app.core.logging_config import get_logger
from media_manager.app.persistence.models import FileContent, MediaMetadata, MetadataCode

logger = get_logger(__name__)
_FILENAME_DT_RE = re.compile(
    r"(?P<y>19\d{2}|20\d{2})[-_]?"
    r"(?P<m>0[1-9]|1[0-2])[-_]?"
    r"(?P<d>0[1-9]|[12]\d|3[01])"
    r"(?:[T _-]?(?P<h>[01]\d|2[0-3])(?P<min>[0-5]\d)(?P<s>[0-5]\d))?"
)
_TAKEN_DT_SOURCE_RANK = {"metadata": 0, "filename": 1, "filesystem": 2, "unknown": 3}


@dataclass(frozen=True)
class MetadataItem:
    code_type: str
    decode_value: str


@dataclass(frozen=True)
class ExtractResult:
    file_hash: str
    content_id: uuid.UUID
    codes_extracted: list[str]
    defaults_used: list[str]


@dataclass(frozen=True)
class PreExtractMetrics:
    files_total: int
    files_processed: int
    rows_upserted: int
    duration_total_s: float
    hash_time_s: float
    extract_time_s: float
    code_upsert_time_s: float
    metadata_upsert_time_s: float
    metadata_lookup_time_s: float
    code_upsert_batches: int
    metadata_upsert_batches: int
    rows_per_batch: tuple[int, ...]

    @property
    def throughput_files_per_s(self) -> float:
        if self.duration_total_s <= 0:
            return 0.0
        return self.files_processed / self.duration_total_s


def _parse_exif_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC)


def _extract_optional_exif(path: Path) -> dict[str, str]:
    try:
        from PIL import Image, UnidentifiedImageError
    except Exception:
        return {}

    try:
        with Image.open(path) as image:
            exif = image.getexif()
    except (FileNotFoundError, OSError, UnidentifiedImageError):
        return {}

    if not exif:
        return {}

    result: dict[str, str] = {}
    for tag_code in (36867, 36868, 306):  # DateTimeOriginal, DateTimeDigitized, DateTime
        parsed = _parse_exif_datetime(exif.get(tag_code))
        if parsed is not None:
            result["TAKEN_DT"] = parsed.astimezone(UTC).isoformat()
            break

    camera_model = exif.get(272)
    if camera_model:
        result["CAMERA_MODEL"] = str(camera_model)

    gps_info = exif.get(34853)
    if gps_info:
        result["GPS"] = str(gps_info)

    tags_value = exif.get(40094) or exif.get(37510)  # XPKeywords / UserComment fallback
    if tags_value:
        result["TAGS"] = str(tags_value)

    return result


def _parse_taken_dt_value(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parsed = _parse_exif_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _extract_filename_datetime(path: Path) -> datetime | None:
    match = _FILENAME_DT_RE.search(path.name)
    if match is None:
        return None
    year = int(match.group("y"))
    month = int(match.group("m"))
    day = int(match.group("d"))
    hour = int(match.group("h") or "0")
    minute = int(match.group("min") or "0")
    second = int(match.group("s") or "0")
    try:
        return datetime(year, month, day, hour, minute, second, tzinfo=UTC)
    except ValueError:
        return None


def _resolve_taken_datetime(path: Path, exif_values: dict[str, str], stat: object) -> tuple[datetime, str]:
    taken_dt_raw = exif_values.get("TAKEN_DT")
    if taken_dt_raw:
        parsed = _parse_taken_dt_value(taken_dt_raw)
        if parsed is not None:
            return parsed, "metadata"

    if filename_has_date(path.name):
        filename_dt = _extract_filename_datetime(path)
        if filename_dt is not None:
            return filename_dt, "filename"

    ctime = datetime.fromtimestamp(float(stat.st_ctime), tz=UTC)
    return ctime, "filesystem"


def taken_dt_source_rank(source: str | None) -> int:
    return _TAKEN_DT_SOURCE_RANK.get((source or "unknown").strip().lower(), _TAKEN_DT_SOURCE_RANK["unknown"])


def extract_file_metadata(
    path: Path,
    file_hash: str,
    *,
    owner: str = DEFAULT_OWNER,
    context: str = DEFAULT_CONTEXT,
) -> list[MetadataItem]:
    _ = file_hash  # hash is part of extraction context and logging identity.
    stat = path.stat()
    ctime = datetime.fromtimestamp(float(stat.st_ctime), tz=UTC).isoformat()
    mtime = datetime.fromtimestamp(float(stat.st_mtime), tz=UTC).isoformat()

    rows: dict[str, str] = {
        "OWNER": owner,
        "CONTEXT": context,
        "FS_CTIME": ctime,
        "FS_MTIME": mtime,
    }
    exif_values = _extract_optional_exif(path)
    rows.update(exif_values)
    taken_dt, taken_dt_source = _resolve_taken_datetime(path, exif_values, stat)
    rows["TAKEN_DT"] = taken_dt.isoformat()
    rows["TAKEN_DT_SOURCE"] = taken_dt_source

    return [MetadataItem(code_type=code_type, decode_value=decode_value) for code_type, decode_value in rows.items()]


def _upsert_metadata_codes(
    session: Session,
    code_types: list[str],
    *,
    batch_size: int,
) -> dict[str, uuid.UUID]:
    unique_types = sorted(set(code_types))
    if not unique_types:
        return {}

    for offset in range(0, len(unique_types), batch_size):
        chunk = unique_types[offset : offset + batch_size]
        code_rows = [{"id": uuid.uuid4(), "code_type": code_type, "description": None} for code_type in chunk]
        stmt = (
            insert(MetadataCode)
            .values(code_rows)
            .on_conflict_do_update(
                index_elements=[MetadataCode.code_type],
                set_={"code_type": insert(MetadataCode).excluded.code_type},
            )
        )
        session.execute(stmt)

    rows = session.execute(
        select(MetadataCode.code_type, MetadataCode.id).where(MetadataCode.code_type.in_(unique_types))
    ).all()
    return {code_type: code_id for code_type, code_id in rows}


def upsert_metadata_bulk(
    session: Session,
    metadata_by_content: dict[uuid.UUID, list[MetadataItem]],
    *,
    batch_size: int = 1000,
    collect_batch_metrics: bool = True,
) -> tuple[dict[uuid.UUID, ExtractResult], PreExtractMetrics]:
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")

    t_start = perf_counter()
    all_rows = [item for rows in metadata_by_content.values() for item in rows]
    code_types = [item.code_type for item in all_rows]

    t_code_start = perf_counter()
    code_ids = _upsert_metadata_codes(session, code_types, batch_size=batch_size)
    code_upsert_time = perf_counter() - t_code_start
    code_batches = (len(sorted(set(code_types))) + batch_size - 1) // batch_size if code_types else 0

    flattened: list[dict[str, object]] = []
    for content_id, rows in metadata_by_content.items():
        for item in rows:
            flattened.append(
                {
                    "id": uuid.uuid4(),
                    "content_id": content_id,
                    "code_id": code_ids[item.code_type],
                    "decode_value": item.decode_value,
                }
            )

    t_metadata_start = perf_counter()
    rows_per_batch: list[int] = []
    metadata_batches = 0
    for offset in range(0, len(flattened), batch_size):
        chunk = flattened[offset : offset + batch_size]
        if not chunk:
            continue
        metadata_batches += 1
        if collect_batch_metrics:
            rows_per_batch.append(len(chunk))
        stmt = (
            insert(MediaMetadata)
            .values(chunk)
            .on_conflict_do_update(
                index_elements=[MediaMetadata.content_id, MediaMetadata.code_id],
                set_={
                    "decode_value": insert(MediaMetadata).excluded.decode_value,
                    "extracted_at": func.now(),
                },
            )
        )
        session.execute(stmt)
    metadata_upsert_time = perf_counter() - t_metadata_start

    results: dict[uuid.UUID, ExtractResult] = {}
    content_hash_map = {
        content_id: sha_hash
        for content_id, sha_hash in session.execute(
            select(FileContent.content_id, FileContent.sha256_hash).where(FileContent.content_id.in_(metadata_by_content.keys()))
        ).all()
    }
    for content_id, rows in metadata_by_content.items():
        defaults_used = [
            code
            for code in ("OWNER", "CONTEXT")
            if any(item.code_type == code and item.decode_value in {"LL", "General"} for item in rows)
        ]
        results[content_id] = ExtractResult(
            file_hash=content_hash_map.get(content_id, "-"),
            content_id=content_id,
            codes_extracted=sorted(item.code_type for item in rows),
            defaults_used=defaults_used,
        )

    total_duration = perf_counter() - t_start
    metrics = PreExtractMetrics(
        files_total=len(metadata_by_content),
        files_processed=len(metadata_by_content),
        rows_upserted=len(flattened),
        duration_total_s=total_duration,
        hash_time_s=0.0,
        extract_time_s=0.0,
        code_upsert_time_s=code_upsert_time,
        metadata_upsert_time_s=metadata_upsert_time,
        metadata_lookup_time_s=0.0,
        code_upsert_batches=code_batches,
        metadata_upsert_batches=metadata_batches,
        rows_per_batch=tuple(rows_per_batch) if collect_batch_metrics else (),
    )
    return results, metrics


def upsert_metadata_for_content(
    session: Session,
    rows: list[MetadataItem],
    content_id: uuid.UUID,
    *,
    batch_size: int = 1000,
) -> ExtractResult:
    results, _ = upsert_metadata_bulk(
        session,
        {content_id: rows},
        batch_size=max(min(batch_size, max(len(rows), 1)), 1),
        collect_batch_metrics=False,
    )
    return results[content_id]


def pre_extract_for_paths_with_metrics(
    session: Session,
    paths: list[Path],
    *,
    run_id: str | None = None,
    batch_size: int = 1000,
    collect_batch_metrics: bool = True,
) -> tuple[dict[str, ExtractResult], PreExtractMetrics]:
    """Compatibility helper used by perf tests.

    Phase 7 ingestion owns extraction. This helper still supports batch profiling
    by mapping paths to file_contents and upserting metadata by content_id.
    """

    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")

    t_total_start = perf_counter()
    hash_time = 0.0
    extract_time = 0.0
    sorted_paths = sorted(paths, key=lambda p: p.resolve(strict=False).as_posix())
    metadata_by_content: dict[uuid.UUID, list[MetadataItem]] = {}
    by_path: dict[str, tuple[uuid.UUID, str]] = {}
    for path in sorted_paths:
        if not path.exists() or not path.is_file():
            logger.info(
                "Metadata skipped",
                extra={
                    "run_id": run_id or "-",
                    "phase": "plan",
                    "file_hash": "-",
                    "action": "SKIPPED",
                    "codes_extracted": "",
                },
            )
            continue

        t_hash_start = perf_counter()
        file_hash = sha256_file(path)
        hash_time += perf_counter() - t_hash_start

        content = session.scalar(select(FileContent).where(FileContent.sha256_hash == file_hash))
        if content is None:
            content = FileContent(sha256_hash=file_hash)
            session.add(content)
            session.flush()

        t_extract_start = perf_counter()
        rows = extract_file_metadata(path, file_hash)
        extract_time += perf_counter() - t_extract_start
        metadata_by_content[content.content_id] = rows
        by_path[str(path.resolve(strict=False))] = (content.content_id, file_hash)

    t_bulk_start = perf_counter()
    content_results, bulk_metrics = upsert_metadata_bulk(
        session,
        metadata_by_content,
        batch_size=batch_size,
        collect_batch_metrics=collect_batch_metrics,
    )
    bulk_duration = perf_counter() - t_bulk_start

    path_results: dict[str, ExtractResult] = {}
    for path_key, (content_id, file_hash) in by_path.items():
        result = content_results[content_id]
        path_results[path_key] = ExtractResult(
            file_hash=file_hash,
            content_id=result.content_id,
            codes_extracted=result.codes_extracted,
            defaults_used=result.defaults_used,
        )
        action = "DEFAULT_USED" if result.defaults_used else "EXTRACTED"
        message = "Metadata defaults used" if action == "DEFAULT_USED" else "Metadata extracted"
        logger.info(
            message,
            extra={
                "run_id": run_id or "-",
                "phase": "plan",
                "file_hash": file_hash,
                "action": action,
                "codes_extracted": ",".join(result.codes_extracted),
            },
        )

    total_duration = perf_counter() - t_total_start
    metrics = PreExtractMetrics(
        files_total=len(sorted_paths),
        files_processed=len(path_results),
        rows_upserted=bulk_metrics.rows_upserted,
        duration_total_s=total_duration,
        hash_time_s=hash_time,
        extract_time_s=extract_time,
        code_upsert_time_s=bulk_metrics.code_upsert_time_s,
        metadata_upsert_time_s=bulk_metrics.metadata_upsert_time_s,
        metadata_lookup_time_s=bulk_duration - bulk_metrics.metadata_upsert_time_s - bulk_metrics.code_upsert_time_s,
        code_upsert_batches=bulk_metrics.code_upsert_batches,
        metadata_upsert_batches=bulk_metrics.metadata_upsert_batches,
        rows_per_batch=bulk_metrics.rows_per_batch,
    )
    return path_results, metrics


def pre_extract_for_paths(
    session: Session,
    paths: list[Path],
    *,
    run_id: str | None = None,
    batch_size: int = 1000,
) -> dict[str, ExtractResult]:
    results, _ = pre_extract_for_paths_with_metrics(
        session,
        paths,
        run_id=run_id,
        batch_size=batch_size,
        collect_batch_metrics=True,
    )
    return results
