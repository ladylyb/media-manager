"""Metadata pre-extraction and persistence helpers for planning."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from media_manager.app.core.hashing import sha256_file
from media_manager.app.core.logging_config import get_logger
from media_manager.app.persistence.models import ContentObject, MediaMetadata, MetadataCode

logger = get_logger(__name__)


@dataclass(frozen=True)
class MetadataItem:
    code_type: str
    decode_value: str


@dataclass(frozen=True)
class ExtractResult:
    file_hash: str
    codes_extracted: list[str]
    defaults_used: list[str]


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


def extract_file_metadata(path: Path, file_hash: str) -> list[MetadataItem]:
    _ = file_hash  # Hash is part of the external API contract; rows are code/decode only.
    stat = path.stat()
    ctime = datetime.fromtimestamp(float(stat.st_ctime), tz=UTC).isoformat()
    mtime = datetime.fromtimestamp(float(stat.st_mtime), tz=UTC).isoformat()

    rows: dict[str, str] = {
        "OWNER": "LL",
        "CONTEXT": "General",
        "FS_CTIME": ctime,
        "FS_MTIME": mtime,
    }
    exif_values = _extract_optional_exif(path)
    rows.update(exif_values)
    if "TAKEN_DT" not in rows:
        rows["TAKEN_DT"] = ctime

    return [MetadataItem(code_type=code_type, decode_value=decode_value) for code_type, decode_value in rows.items()]


def upsert_metadata_batch(session: Session, rows: list[MetadataItem], file_hash: str) -> ExtractResult:
    defaults_used = [
        code for code in ("OWNER", "CONTEXT") if any(item.code_type == code and item.decode_value in {"LL", "General"} for item in rows)
    ]
    if any(item.code_type == "TAKEN_DT" for item in rows) and not any(item.code_type == "EXIF_DT" for item in rows):
        pass

    code_ids: dict[str, uuid.UUID] = {}
    for item in rows:
        code_stmt = (
            insert(MetadataCode)
            .values(id=uuid.uuid4(), code_type=item.code_type, description=None)
            .on_conflict_do_update(
                index_elements=[MetadataCode.code_type],
                set_={"code_type": item.code_type},
            )
            .returning(MetadataCode.id)
        )
        code_id = session.scalar(code_stmt)
        if code_id is None:
            code_id = session.scalar(select(MetadataCode.id).where(MetadataCode.code_type == item.code_type))
        if code_id is None:
            raise RuntimeError(f"Failed to resolve metadata code id for {item.code_type}")
        code_ids[item.code_type] = code_id

    for item in rows:
        metadata_stmt = (
            insert(MediaMetadata)
            .values(
                id=uuid.uuid4(),
                file_hash=file_hash,
                code_id=code_ids[item.code_type],
                decode_value=item.decode_value,
            )
            .on_conflict_do_update(
                index_elements=[MediaMetadata.file_hash, MediaMetadata.code_id],
                set_={"decode_value": item.decode_value, "extracted_at": func.now()},
            )
        )
        session.execute(metadata_stmt)

    return ExtractResult(
        file_hash=file_hash,
        codes_extracted=sorted(item.code_type for item in rows),
        defaults_used=defaults_used,
    )


def _upsert_content_object(session: Session, file_hash: str, size_bytes: int) -> None:
    stmt = (
        insert(ContentObject)
        .values(hash=file_hash, size_bytes=size_bytes)
        .on_conflict_do_update(
            index_elements=[ContentObject.hash],
            set_={"size_bytes": size_bytes},
        )
    )
    session.execute(stmt)


def pre_extract_for_paths(
    session: Session,
    paths: list[Path],
    *,
    run_id: str | None = None,
) -> dict[str, ExtractResult]:
    results: dict[str, ExtractResult] = {}
    for path in sorted(paths, key=lambda p: p.resolve(strict=False).as_posix()):
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

        file_hash = sha256_file(path)
        size_bytes = int(path.stat().st_size)
        _upsert_content_object(session, file_hash, size_bytes)
        rows = extract_file_metadata(path, file_hash)
        result = upsert_metadata_batch(session, rows, file_hash)
        results[str(path.resolve(strict=False))] = result

        action = "DEFAULT_USED" if result.defaults_used else "EXTRACTED"
        message = "Metadata defaults used" if action == "DEFAULT_USED" else "Metadata extracted"
        logger.info(
            message,
            extra={
                "run_id": run_id or "-",
                "phase": "plan",
                "file_hash": result.file_hash,
                "action": action,
                "codes_extracted": ",".join(result.codes_extracted),
            },
        )
    return results
