from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from media_manager.app.core.errors import MediaManagerError

_HASH64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class LegacyImportError(MediaManagerError):
    """Raised when legacy import fails validation or persistence."""


@dataclass(frozen=True)
class LegacyImportSummary:
    import_run_id: uuid.UUID
    state: str
    raw_counts: dict[str, int]
    verification_failures: list[str]


_RAW_TABLES_WITH_ID: tuple[str, ...] = (
    "scans",
    "files",
    "file_actions",
    "_file_actions_old",
    "duplicate_candidates",
    "deletion_audit_runs",
    "deletion_audit_candidates",
    "deletion_audit_candidate_files",
)

_RAW_TABLES_WITH_ROW_NO: tuple[str, ...] = ("_tmp_deletion_audit_import",)

_REQUIRED_TABLE_COLUMNS: dict[str, set[str]] = {
    "scans": {"id", "root_path"},
    "files": {"id", "scan_id", "path", "filename", "size_bytes"},
    "file_actions": {"id", "file_id", "action"},
    "_file_actions_old": {"id", "file_id", "action"},
    "duplicate_candidates": {"id", "file_id_1", "file_id_2", "match_type", "confidence_score"},
    "deletion_audit_runs": {"id", "audit_name"},
    "deletion_audit_candidates": {"id", "audit_run_id", "observed_path"},
    "deletion_audit_candidate_files": {"id", "audit_candidate_id", "related_file_id"},
    "_tmp_deletion_audit_import": {"to_be_deleted_path"},
}


def _chunked(items: list[dict[str, Any]], chunk_size: int = 1000) -> list[list[dict[str, Any]]]:
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _normalize_path_for_surrogate(path: str) -> str:
    return path.replace("\\", "/").lower().strip()


def _stable_mtime_token(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _parse_optional_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    text_value = value.strip()
    if not text_value:
        return None

    normalized = text_value.replace("Z", "+00:00")
    for parser in (
        lambda v: datetime.fromisoformat(v),
        lambda v: datetime.strptime(v, "%Y:%m:%d %H:%M:%S"),
        lambda v: datetime.strptime(v, "%Y-%m-%d %H:%M:%S"),
    ):
        try:
            parsed = parser(normalized)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            continue
    return None


class LegacyImportService:
    def __init__(self, engine: Engine, *, raw_schema: str = "legacy_raw", normalized_schema: str = "legacy_3nf") -> None:
        if not _IDENTIFIER_RE.match(raw_schema):
            raise LegacyImportError(f"Invalid raw schema identifier: {raw_schema}")
        if not _IDENTIFIER_RE.match(normalized_schema):
            raise LegacyImportError(f"Invalid normalized schema identifier: {normalized_schema}")
        self._engine = engine
        self._raw_schema = raw_schema
        self._normalized_schema = normalized_schema

    def import_sqlite(
        self,
        sqlite_path: Path,
        *,
        import_run_id: uuid.UUID | None = None,
        source_db_name: str | None = None,
    ) -> LegacyImportSummary:
        resolved = sqlite_path.resolve(strict=False)
        if not resolved.exists():
            raise LegacyImportError(f"SQLite path does not exist: {resolved}")

        fingerprint = self._fingerprint_sqlite_file(resolved)
        run_id = import_run_id or uuid.uuid4()
        source_name = source_db_name or resolved.name

        with closing(self._open_sqlite_readonly(resolved)) as sqlite_conn:
            self._validate_sqlite_shape(sqlite_conn)
            self._ensure_import_run(run_id, resolved, source_name, fingerprint)
            row = self._load_import_run(run_id)
            self._assert_source_consistency(row, resolved, fingerprint)

            if row["state"] == "VERIFIED":
                report = self._load_json(row["verification_report_json"])
                return LegacyImportSummary(
                    import_run_id=run_id,
                    state="VERIFIED",
                    raw_counts=self._load_json(row["raw_counts_json"]),
                    verification_failures=report.get("failures", []),
                )

            try:
                if row["raw_loaded_at"] is None:
                    raw_counts, raw_checksums = self._load_raw_phase(run_id, sqlite_conn, source_name)
                    self._mark_state(
                        run_id,
                        state="RAW_LOADED",
                        raw_counts_json=json.dumps(raw_counts, sort_keys=True),
                        raw_checksums_json=json.dumps(raw_checksums, sort_keys=True),
                        raw_loaded_at=_now_utc(),
                    )

                row = self._load_import_run(run_id)
                if row["normalized_at"] is None:
                    self._normalize_phase(run_id)
                    self._mark_state(run_id, state="NORMALIZED", normalized_at=_now_utc())

                report = self._verify_phase(run_id, sqlite_conn)
                if report["failures"]:
                    for failure in report["failures"]:
                        self._append_failure(
                            run_id,
                            stage="verification",
                            error_code="VERIFICATION_FAILED",
                            error_message=failure,
                            context={"report": report},
                        )
                    self._mark_state(
                        run_id,
                        state="FAILED",
                        verification_report_json=json.dumps(report, sort_keys=True),
                    )
                    raise LegacyImportError("Legacy import verification failed")

                self._mark_state(
                    run_id,
                    state="VERIFIED",
                    verification_report_json=json.dumps(report, sort_keys=True),
                    verified_at=_now_utc(),
                )
                raw_counts = self._load_json(self._load_import_run(run_id)["raw_counts_json"])
                return LegacyImportSummary(
                    import_run_id=run_id,
                    state="VERIFIED",
                    raw_counts=raw_counts,
                    verification_failures=[],
                )
            except Exception as exc:
                self._append_failure(
                    run_id,
                    stage="pipeline",
                    error_code=exc.__class__.__name__,
                    error_message=str(exc),
                    context={"sqlite_path": str(resolved)},
                )
                self._mark_state(run_id, state="FAILED")
                raise

    def _fingerprint_sqlite_file(self, sqlite_path: Path) -> dict[str, Any]:
        stat = sqlite_path.stat()
        sha = hashlib.sha256()
        with sqlite_path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                sha.update(chunk)
        return {
            "size": int(stat.st_size),
            "mtime": datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            "sha256": sha.hexdigest(),
        }

    def _open_sqlite_readonly(self, sqlite_path: Path) -> sqlite3.Connection:
        uri = f"file:{sqlite_path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA temp_store=MEMORY")
        return conn

    def _validate_sqlite_shape(self, sqlite_conn: sqlite3.Connection) -> None:
        table_names = {
            row["name"]
            for row in sqlite_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }

        missing_tables = sorted(set(_REQUIRED_TABLE_COLUMNS) - table_names)
        if missing_tables:
            raise LegacyImportError(f"SQLite database missing required tables: {', '.join(missing_tables)}")

        for table_name, required_columns in _REQUIRED_TABLE_COLUMNS.items():
            columns = {
                row["name"]
                for row in sqlite_conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
            }
            missing_columns = sorted(required_columns - columns)
            if missing_columns:
                raise LegacyImportError(
                    f"SQLite table {table_name} missing columns: {', '.join(missing_columns)}"
                )

    def _ensure_import_run(
        self,
        run_id: uuid.UUID,
        sqlite_path: Path,
        source_db_name: str,
        fingerprint: dict[str, Any],
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    f"""
                    INSERT INTO {self._normalized_schema}.import_runs (
                        import_run_id,
                        state,
                        sqlite_path,
                        source_db_name,
                        source_db_size_bytes,
                        source_db_mtime,
                        source_db_sha256
                    )
                    VALUES (
                        :import_run_id,
                        'CREATED',
                        :sqlite_path,
                        :source_db_name,
                        :source_db_size_bytes,
                        :source_db_mtime,
                        :source_db_sha256
                    )
                    ON CONFLICT (import_run_id) DO UPDATE
                    SET
                        sqlite_path = EXCLUDED.sqlite_path,
                        source_db_name = EXCLUDED.source_db_name,
                        updated_at = now()
                    """
                ),
                {
                    "import_run_id": run_id,
                    "sqlite_path": str(sqlite_path),
                    "source_db_name": source_db_name,
                    "source_db_size_bytes": fingerprint["size"],
                    "source_db_mtime": fingerprint["mtime"],
                    "source_db_sha256": fingerprint["sha256"],
                },
            )

    def _load_import_run(self, run_id: uuid.UUID) -> dict[str, Any]:
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    f"SELECT * FROM {self._normalized_schema}.import_runs WHERE import_run_id = :import_run_id"
                ),
                {"import_run_id": run_id},
            ).mappings().one()
            return dict(row)

    def _assert_source_consistency(self, row: dict[str, Any], sqlite_path: Path, fingerprint: dict[str, Any]) -> None:
        if Path(row["sqlite_path"]).resolve(strict=False) != sqlite_path.resolve(strict=False):
            raise LegacyImportError("Provided import_run_id points to a different sqlite_path")
        if row["source_db_sha256"] != fingerprint["sha256"]:
            raise LegacyImportError("Provided import_run_id points to different SQLite source content")

    def _load_raw_phase(
        self,
        run_id: uuid.UUID,
        sqlite_conn: sqlite3.Connection,
        source_db_name: str,
    ) -> tuple[dict[str, int], dict[str, str]]:
        counts: dict[str, int] = {}
        checksums: dict[str, str] = {}

        for table_name in (*_RAW_TABLES_WITH_ID, *_RAW_TABLES_WITH_ROW_NO):
            if table_name in _RAW_TABLES_WITH_ID:
                rows = sqlite_conn.execute(f'SELECT * FROM "{table_name}" ORDER BY id').fetchall()
            else:
                rows = sqlite_conn.execute(f'SELECT rowid AS legacy_row_no, * FROM "{table_name}" ORDER BY rowid').fetchall()

            counts[table_name] = len(rows)
            checksums[table_name] = self._checksum_rows(rows)
            self._insert_raw_rows(run_id, table_name, rows, source_db_name)

        return counts, checksums

    def _checksum_rows(self, rows: list[sqlite3.Row]) -> str:
        digest = hashlib.sha256()
        for row in rows:
            payload = json.dumps({key: row[key] for key in row.keys()}, sort_keys=True, default=str)
            digest.update(payload.encode("utf-8"))
            digest.update(b"\n")
        return digest.hexdigest()

    def _insert_raw_rows(
        self,
        run_id: uuid.UUID,
        table_name: str,
        rows: list[sqlite3.Row],
        source_db_name: str,
    ) -> None:
        if not rows:
            return

        sqlite_columns = list(rows[0].keys())
        if table_name in _RAW_TABLES_WITH_ROW_NO and "legacy_row_no" not in sqlite_columns:
            raise LegacyImportError(f"Table {table_name} expected synthetic legacy_row_no")

        table_columns = [*sqlite_columns, "import_run_id", "source_db_name"]
        params_template = ", ".join(f":{column}" for column in table_columns)
        insert_columns = ", ".join(table_columns)

        if table_name in _RAW_TABLES_WITH_ID:
            conflict = "import_run_id, id"
        else:
            conflict = "import_run_id, legacy_row_no"

        sql = text(
            f"""
            INSERT INTO {self._raw_schema}.{table_name} ({insert_columns})
            VALUES ({params_template})
            ON CONFLICT ({conflict}) DO NOTHING
            """
        )

        payload: list[dict[str, Any]] = []
        for row in rows:
            data = {column: row[column] for column in sqlite_columns}
            data["import_run_id"] = run_id
            data["source_db_name"] = source_db_name
            payload.append(data)

        with self._engine.begin() as conn:
            for chunk in _chunked(payload):
                conn.execute(sql, chunk)

    def _normalize_phase(self, run_id: uuid.UUID) -> None:
        self._load_scan_batch(run_id)
        self._load_content_identity(run_id)
        self._load_file_instance_and_media(run_id)
        self._load_action_events(run_id)
        self._load_duplicate_evidence(run_id)
        self._load_deletion_audit(run_id)
        self._load_canonical_candidates(run_id)

    def _load_scan_batch(self, run_id: uuid.UUID) -> None:
        namespace = uuid.uuid5(uuid.NAMESPACE_URL, str(run_id))
        with self._engine.begin() as conn:
            rows = conn.execute(
                text(
                    f"SELECT id, root_path, started_at, finished_at, notes FROM {self._raw_schema}.scans "
                    "WHERE import_run_id = :import_run_id"
                ),
                {"import_run_id": run_id},
            ).mappings().all()

            payload = []
            for row in rows:
                payload.append(
                    {
                        "scan_batch_id": uuid.uuid5(namespace, f"scan:{row['id']}"),
                        "import_run_id": run_id,
                        "legacy_scan_id": row["id"],
                        "root_path": row["root_path"],
                        "started_at": row["started_at"],
                        "finished_at": row["finished_at"],
                        "notes": row["notes"],
                    }
                )

            if not payload:
                return

            stmt = text(
                f"""
                INSERT INTO {self._normalized_schema}.scan_batch (
                    scan_batch_id, import_run_id, legacy_scan_id, root_path, started_at, finished_at, notes
                )
                VALUES (
                    :scan_batch_id, :import_run_id, :legacy_scan_id, :root_path, :started_at, :finished_at, :notes
                )
                ON CONFLICT (import_run_id, legacy_scan_id) DO UPDATE
                SET
                    root_path = EXCLUDED.root_path,
                    started_at = EXCLUDED.started_at,
                    finished_at = EXCLUDED.finished_at,
                    notes = EXCLUDED.notes
                """
            )
            for chunk in _chunked(payload):
                conn.execute(stmt, chunk)

    def _identity_for_file(self, row: dict[str, Any]) -> tuple[str, str, str | None, str | None, int | None]:
        hash_full = row.get("hash_full")
        hash_algo = row.get("hash_algo")
        size_bytes = row.get("size_bytes")
        if isinstance(hash_full, str) and _HASH64_RE.match(hash_full.strip()):
            normalized_hash = hash_full.lower()
            return "HASH_FULL", normalized_hash, normalized_hash, hash_algo, size_bytes

        normalized_path = _normalize_path_for_surrogate(str(row["path"]))
        mtime_token = _stable_mtime_token(row.get("mtime"))
        raw = f"{normalized_path}|{size_bytes}|{mtime_token}"
        surrogate = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return "SURROGATE", surrogate, None, hash_algo, size_bytes

    def _load_content_identity(self, run_id: uuid.UUID) -> None:
        namespace = uuid.uuid5(uuid.NAMESPACE_URL, str(run_id))
        with self._engine.begin() as conn:
            rows = conn.execute(
                text(
                    f"SELECT id, path, size_bytes, mtime, hash_full, hash_algo FROM {self._raw_schema}.files "
                    "WHERE import_run_id = :import_run_id"
                ),
                {"import_run_id": run_id},
            ).mappings().all()

            seen: dict[tuple[str, str], dict[str, Any]] = {}
            for row in rows:
                tier, value, hash_full, hash_algo, size_bytes = self._identity_for_file(dict(row))
                key = (tier, value)
                if key not in seen:
                    seen[key] = {
                        "content_identity_id": uuid.uuid5(namespace, f"content:{tier}:{value}"),
                        "import_run_id": run_id,
                        "identity_tier": tier,
                        "identity_value": value,
                        "hash_full": hash_full,
                        "hash_algo": hash_algo,
                        "size_bytes": size_bytes,
                    }

            payload = list(seen.values())
            if not payload:
                return

            stmt = text(
                f"""
                INSERT INTO {self._normalized_schema}.content_identity (
                    content_identity_id,
                    import_run_id,
                    identity_tier,
                    identity_value,
                    hash_full,
                    hash_algo,
                    size_bytes
                )
                VALUES (
                    :content_identity_id,
                    :import_run_id,
                    :identity_tier,
                    :identity_value,
                    :hash_full,
                    :hash_algo,
                    :size_bytes
                )
                ON CONFLICT (import_run_id, identity_tier, identity_value) DO UPDATE
                SET
                    hash_full = COALESCE(EXCLUDED.hash_full, {self._normalized_schema}.content_identity.hash_full),
                    hash_algo = COALESCE(EXCLUDED.hash_algo, {self._normalized_schema}.content_identity.hash_algo),
                    size_bytes = COALESCE(EXCLUDED.size_bytes, {self._normalized_schema}.content_identity.size_bytes)
                """
            )
            for chunk in _chunked(payload):
                conn.execute(stmt, chunk)

    def _load_file_instance_and_media(self, run_id: uuid.UUID) -> None:
        namespace = uuid.uuid5(uuid.NAMESPACE_URL, str(run_id))
        with self._engine.begin() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT
                        f.id,
                        f.scan_id,
                        f.path,
                        f.filename,
                        f.extension,
                        f.size_bytes,
                        f.mtime,
                        f.ctime,
                        f.hash_full,
                        f.hash_algo,
                        f.is_hashed,
                        f.is_metadata_extracted,
                        f.media_type,
                        f.duration,
                        f.width,
                        f.height,
                        f.codec,
                        f.bitrate,
                        f.exif_datetime,
                        f.camera_model,
                        f.orientation
                    FROM {self._raw_schema}.files f
                    WHERE f.import_run_id = :import_run_id
                    """
                ),
                {"import_run_id": run_id},
            ).mappings().all()

            files_payload: list[dict[str, Any]] = []
            media_payload: list[dict[str, Any]] = []

            for row in rows:
                row_dict = dict(row)
                tier, value, _, _, _ = self._identity_for_file(row_dict)
                files_payload.append(
                    {
                        "file_instance_id": uuid.uuid5(namespace, f"file:{row_dict['id']}"),
                        "import_run_id": run_id,
                        "legacy_file_id": row_dict["id"],
                        "scan_batch_id": uuid.uuid5(namespace, f"scan:{row_dict['scan_id']}"),
                        "content_identity_id": uuid.uuid5(namespace, f"content:{tier}:{value}"),
                        "absolute_path": row_dict["path"],
                        "filename": row_dict["filename"],
                        "extension": row_dict["extension"],
                        "size_bytes": row_dict["size_bytes"],
                        "mtime": row_dict["mtime"],
                        "ctime": row_dict["ctime"],
                        "is_hashed": bool(row_dict["is_hashed"] or 0),
                        "is_metadata_extracted": bool(row_dict["is_metadata_extracted"] or 0),
                    }
                )
                media_payload.append(
                    {
                        "file_instance_id": uuid.uuid5(namespace, f"file:{row_dict['id']}"),
                        "media_type": row_dict["media_type"],
                        "duration": row_dict["duration"],
                        "width": row_dict["width"],
                        "height": row_dict["height"],
                        "codec": row_dict["codec"],
                        "bitrate": row_dict["bitrate"],
                        "exif_datetime": row_dict["exif_datetime"],
                        "camera_model": row_dict["camera_model"],
                        "orientation": row_dict["orientation"],
                    }
                )

            if files_payload:
                files_stmt = text(
                    f"""
                    INSERT INTO {self._normalized_schema}.file_instance (
                        file_instance_id,
                        import_run_id,
                        legacy_file_id,
                        scan_batch_id,
                        content_identity_id,
                        absolute_path,
                        filename,
                        extension,
                        size_bytes,
                        mtime,
                        ctime,
                        is_hashed,
                        is_metadata_extracted
                    )
                    VALUES (
                        :file_instance_id,
                        :import_run_id,
                        :legacy_file_id,
                        :scan_batch_id,
                        :content_identity_id,
                        :absolute_path,
                        :filename,
                        :extension,
                        :size_bytes,
                        :mtime,
                        :ctime,
                        :is_hashed,
                        :is_metadata_extracted
                    )
                    ON CONFLICT (import_run_id, legacy_file_id) DO UPDATE
                    SET
                        scan_batch_id = EXCLUDED.scan_batch_id,
                        content_identity_id = EXCLUDED.content_identity_id,
                        absolute_path = EXCLUDED.absolute_path,
                        filename = EXCLUDED.filename,
                        extension = EXCLUDED.extension,
                        size_bytes = EXCLUDED.size_bytes,
                        mtime = EXCLUDED.mtime,
                        ctime = EXCLUDED.ctime,
                        is_hashed = EXCLUDED.is_hashed,
                        is_metadata_extracted = EXCLUDED.is_metadata_extracted
                    """
                )
                for chunk in _chunked(files_payload):
                    conn.execute(files_stmt, chunk)

            if media_payload:
                media_stmt = text(
                    f"""
                    INSERT INTO {self._normalized_schema}.media_attributes (
                        file_instance_id,
                        media_type,
                        duration,
                        width,
                        height,
                        codec,
                        bitrate,
                        exif_datetime,
                        camera_model,
                        orientation
                    )
                    VALUES (
                        :file_instance_id,
                        :media_type,
                        :duration,
                        :width,
                        :height,
                        :codec,
                        :bitrate,
                        :exif_datetime,
                        :camera_model,
                        :orientation
                    )
                    ON CONFLICT (file_instance_id) DO UPDATE
                    SET
                        media_type = EXCLUDED.media_type,
                        duration = EXCLUDED.duration,
                        width = EXCLUDED.width,
                        height = EXCLUDED.height,
                        codec = EXCLUDED.codec,
                        bitrate = EXCLUDED.bitrate,
                        exif_datetime = EXCLUDED.exif_datetime,
                        camera_model = EXCLUDED.camera_model,
                        orientation = EXCLUDED.orientation
                    """
                )
                for chunk in _chunked(media_payload):
                    conn.execute(media_stmt, chunk)

    def _load_action_events(self, run_id: uuid.UUID) -> None:
        namespace = uuid.uuid5(uuid.NAMESPACE_URL, str(run_id))
        payload: list[dict[str, Any]] = []
        with self._engine.begin() as conn:
            for table_name, source_name in (("file_actions", "CURRENT"), ("_file_actions_old", "LEGACY_OLD")):
                rows = conn.execute(
                    text(
                        f"SELECT id, file_id, action, target_path, decided_at, notes FROM {self._raw_schema}.{table_name} "
                        "WHERE import_run_id = :import_run_id"
                    ),
                    {"import_run_id": run_id},
                ).mappings().all()
                for row in rows:
                    payload.append(
                        {
                            "action_event_id": uuid.uuid5(namespace, f"action:{source_name}:{row['id']}"),
                            "import_run_id": run_id,
                            "legacy_action_id": row["id"],
                            "action_source": source_name,
                            "file_instance_id": uuid.uuid5(namespace, f"file:{row['file_id']}"),
                            "action": row["action"],
                            "target_path": row["target_path"],
                            "decided_at": row["decided_at"],
                            "notes": row["notes"],
                        }
                    )

            if not payload:
                return

            stmt = text(
                f"""
                INSERT INTO {self._normalized_schema}.action_event (
                    action_event_id,
                    import_run_id,
                    legacy_action_id,
                    action_source,
                    file_instance_id,
                    action,
                    target_path,
                    decided_at,
                    notes
                )
                VALUES (
                    :action_event_id,
                    :import_run_id,
                    :legacy_action_id,
                    :action_source,
                    :file_instance_id,
                    :action,
                    :target_path,
                    :decided_at,
                    :notes
                )
                ON CONFLICT (import_run_id, action_source, legacy_action_id) DO UPDATE
                SET
                    file_instance_id = EXCLUDED.file_instance_id,
                    action = EXCLUDED.action,
                    target_path = EXCLUDED.target_path,
                    decided_at = EXCLUDED.decided_at,
                    notes = EXCLUDED.notes
                """
            )
            for chunk in _chunked(payload):
                conn.execute(stmt, chunk)

    def _load_duplicate_evidence(self, run_id: uuid.UUID) -> None:
        namespace = uuid.uuid5(uuid.NAMESPACE_URL, str(run_id))
        with self._engine.begin() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT id, file_id_1, file_id_2, match_type, confidence_score, reason, duplicate_group_id, created_at
                    FROM {self._raw_schema}.duplicate_candidates
                    WHERE import_run_id = :import_run_id
                    """
                ),
                {"import_run_id": run_id},
            ).mappings().all()

            payload = []
            for row in rows:
                one = uuid.uuid5(namespace, f"file:{row['file_id_1']}")
                two = uuid.uuid5(namespace, f"file:{row['file_id_2']}")
                low, high = sorted((one, two), key=str)
                payload.append(
                    {
                        "duplicate_evidence_id": uuid.uuid5(namespace, f"dup:{row['id']}"),
                        "import_run_id": run_id,
                        "legacy_duplicate_id": row["id"],
                        "file_instance_1_id": one,
                        "file_instance_2_id": two,
                        "canonical_low_file_id": low,
                        "canonical_high_file_id": high,
                        "match_type": row["match_type"],
                        "confidence_score": row["confidence_score"],
                        "reason": row["reason"],
                        "duplicate_group_id": row["duplicate_group_id"],
                        "created_at": row["created_at"],
                    }
                )

            if not payload:
                return

            stmt = text(
                f"""
                INSERT INTO {self._normalized_schema}.duplicate_evidence (
                    duplicate_evidence_id,
                    import_run_id,
                    legacy_duplicate_id,
                    file_instance_1_id,
                    file_instance_2_id,
                    canonical_low_file_id,
                    canonical_high_file_id,
                    match_type,
                    confidence_score,
                    reason,
                    duplicate_group_id,
                    created_at
                )
                VALUES (
                    :duplicate_evidence_id,
                    :import_run_id,
                    :legacy_duplicate_id,
                    :file_instance_1_id,
                    :file_instance_2_id,
                    :canonical_low_file_id,
                    :canonical_high_file_id,
                    :match_type,
                    :confidence_score,
                    :reason,
                    :duplicate_group_id,
                    :created_at
                )
                ON CONFLICT (import_run_id, legacy_duplicate_id) DO UPDATE
                SET
                    file_instance_1_id = EXCLUDED.file_instance_1_id,
                    file_instance_2_id = EXCLUDED.file_instance_2_id,
                    canonical_low_file_id = EXCLUDED.canonical_low_file_id,
                    canonical_high_file_id = EXCLUDED.canonical_high_file_id,
                    match_type = EXCLUDED.match_type,
                    confidence_score = EXCLUDED.confidence_score,
                    reason = EXCLUDED.reason,
                    duplicate_group_id = EXCLUDED.duplicate_group_id,
                    created_at = EXCLUDED.created_at
                """
            )
            for chunk in _chunked(payload):
                conn.execute(stmt, chunk)

    def _load_deletion_audit(self, run_id: uuid.UUID) -> None:
        namespace = uuid.uuid5(uuid.NAMESPACE_URL, str(run_id))
        with self._engine.begin() as conn:
            run_rows = conn.execute(
                text(
                    f"SELECT id, audit_name, created_at, notes FROM {self._raw_schema}.deletion_audit_runs "
                    "WHERE import_run_id = :import_run_id"
                ),
                {"import_run_id": run_id},
            ).mappings().all()
            run_payload = [
                {
                    "deletion_audit_run_id": uuid.uuid5(namespace, f"audit-run:{row['id']}"),
                    "import_run_id": run_id,
                    "legacy_audit_run_id": row["id"],
                    "audit_name": row["audit_name"],
                    "created_at": row["created_at"],
                    "notes": row["notes"],
                }
                for row in run_rows
            ]

            if run_payload:
                run_stmt = text(
                    f"""
                    INSERT INTO {self._normalized_schema}.deletion_audit_run (
                        deletion_audit_run_id,
                        import_run_id,
                        legacy_audit_run_id,
                        audit_name,
                        created_at,
                        notes
                    )
                    VALUES (
                        :deletion_audit_run_id,
                        :import_run_id,
                        :legacy_audit_run_id,
                        :audit_name,
                        :created_at,
                        :notes
                    )
                    ON CONFLICT (import_run_id, legacy_audit_run_id) DO UPDATE
                    SET
                        audit_name = EXCLUDED.audit_name,
                        created_at = EXCLUDED.created_at,
                        notes = EXCLUDED.notes
                    """
                )
                for chunk in _chunked(run_payload):
                    conn.execute(run_stmt, chunk)

            candidate_rows = conn.execute(
                text(
                    f"""
                    SELECT id, audit_run_id, reconstructed_name, observed_path, audit_notes, raw_actions_snapshot, created_at
                    FROM {self._raw_schema}.deletion_audit_candidates
                    WHERE import_run_id = :import_run_id
                    """
                ),
                {"import_run_id": run_id},
            ).mappings().all()
            candidate_payload = [
                {
                    "deletion_audit_candidate_id": uuid.uuid5(namespace, f"audit-candidate:{row['id']}"),
                    "import_run_id": run_id,
                    "legacy_candidate_id": row["id"],
                    "deletion_audit_run_id": uuid.uuid5(namespace, f"audit-run:{row['audit_run_id']}"),
                    "reconstructed_name": row["reconstructed_name"],
                    "observed_path": row["observed_path"],
                    "audit_notes": row["audit_notes"],
                    "raw_actions_snapshot": row["raw_actions_snapshot"],
                    "created_at": row["created_at"],
                }
                for row in candidate_rows
            ]

            if candidate_payload:
                candidate_stmt = text(
                    f"""
                    INSERT INTO {self._normalized_schema}.deletion_audit_candidate (
                        deletion_audit_candidate_id,
                        import_run_id,
                        legacy_candidate_id,
                        deletion_audit_run_id,
                        reconstructed_name,
                        observed_path,
                        audit_notes,
                        raw_actions_snapshot,
                        created_at
                    )
                    VALUES (
                        :deletion_audit_candidate_id,
                        :import_run_id,
                        :legacy_candidate_id,
                        :deletion_audit_run_id,
                        :reconstructed_name,
                        :observed_path,
                        :audit_notes,
                        :raw_actions_snapshot,
                        :created_at
                    )
                    ON CONFLICT (import_run_id, legacy_candidate_id) DO UPDATE
                    SET
                        deletion_audit_run_id = EXCLUDED.deletion_audit_run_id,
                        reconstructed_name = EXCLUDED.reconstructed_name,
                        observed_path = EXCLUDED.observed_path,
                        audit_notes = EXCLUDED.audit_notes,
                        raw_actions_snapshot = EXCLUDED.raw_actions_snapshot,
                        created_at = EXCLUDED.created_at
                    """
                )
                for chunk in _chunked(candidate_payload):
                    conn.execute(candidate_stmt, chunk)

            link_rows = conn.execute(
                text(
                    f"SELECT id, audit_candidate_id, related_file_id FROM {self._raw_schema}.deletion_audit_candidate_files "
                    "WHERE import_run_id = :import_run_id"
                ),
                {"import_run_id": run_id},
            ).mappings().all()
            link_payload = [
                {
                    "deletion_audit_candidate_instance_id": uuid.uuid5(namespace, f"audit-link:{row['id']}"),
                    "import_run_id": run_id,
                    "legacy_candidate_file_id": row["id"],
                    "deletion_audit_candidate_id": uuid.uuid5(namespace, f"audit-candidate:{row['audit_candidate_id']}"),
                    "file_instance_id": uuid.uuid5(namespace, f"file:{row['related_file_id']}"),
                }
                for row in link_rows
            ]

            if link_payload:
                link_stmt = text(
                    f"""
                    INSERT INTO {self._normalized_schema}.deletion_audit_candidate_instance (
                        deletion_audit_candidate_instance_id,
                        import_run_id,
                        legacy_candidate_file_id,
                        deletion_audit_candidate_id,
                        file_instance_id
                    )
                    VALUES (
                        :deletion_audit_candidate_instance_id,
                        :import_run_id,
                        :legacy_candidate_file_id,
                        :deletion_audit_candidate_id,
                        :file_instance_id
                    )
                    ON CONFLICT (import_run_id, legacy_candidate_file_id) DO UPDATE
                    SET
                        deletion_audit_candidate_id = EXCLUDED.deletion_audit_candidate_id,
                        file_instance_id = EXCLUDED.file_instance_id
                    """
                )
                for chunk in _chunked(link_payload):
                    conn.execute(link_stmt, chunk)

    def _load_canonical_candidates(self, run_id: uuid.UUID) -> None:
        with self._engine.begin() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT
                        fi.content_identity_id,
                        fi.file_instance_id,
                        fi.absolute_path,
                        fi.mtime,
                        ma.exif_datetime
                    FROM {self._normalized_schema}.file_instance fi
                    LEFT JOIN {self._normalized_schema}.media_attributes ma
                      ON ma.file_instance_id = fi.file_instance_id
                    WHERE fi.import_run_id = :import_run_id
                    ORDER BY fi.content_identity_id, fi.absolute_path
                    """
                ),
                {"import_run_id": run_id},
            ).mappings().all()

            grouped: dict[uuid.UUID, list[dict[str, Any]]] = {}
            for row in rows:
                grouped.setdefault(row["content_identity_id"], []).append(dict(row))

            payload: list[dict[str, Any]] = []
            for content_id, candidates in grouped.items():
                ranked = sorted(
                    candidates,
                    key=lambda candidate: (
                        _parse_optional_datetime(candidate["exif_datetime"]) is None,
                        _parse_optional_datetime(candidate["exif_datetime"]) or datetime.max.replace(tzinfo=UTC),
                        candidate["mtime"] is None,
                        candidate["mtime"] if candidate["mtime"] is not None else float("inf"),
                        str(candidate["absolute_path"]).lower(),
                    ),
                )
                canonical = ranked[0]
                payload.append(
                    {
                        "import_run_id": run_id,
                        "content_identity_id": content_id,
                        "canonical_file_instance_id": canonical["file_instance_id"],
                        "selection_reason": "earliest_exif_then_mtime_then_path",
                    }
                )

            if not payload:
                return

            stmt = text(
                f"""
                INSERT INTO {self._normalized_schema}.canonical_candidate (
                    import_run_id,
                    content_identity_id,
                    canonical_file_instance_id,
                    selection_reason
                )
                VALUES (
                    :import_run_id,
                    :content_identity_id,
                    :canonical_file_instance_id,
                    :selection_reason
                )
                ON CONFLICT (import_run_id, content_identity_id) DO UPDATE
                SET
                    canonical_file_instance_id = EXCLUDED.canonical_file_instance_id,
                    selection_reason = EXCLUDED.selection_reason,
                    generated_at = now()
                """
            )
            for chunk in _chunked(payload):
                conn.execute(stmt, chunk)

    def _verify_phase(self, run_id: uuid.UUID, sqlite_conn: sqlite3.Connection) -> dict[str, Any]:
        failures: list[str] = []

        source_counts = {
            table: sqlite_conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in (*_RAW_TABLES_WITH_ID, *_RAW_TABLES_WITH_ROW_NO)
        }

        with self._engine.begin() as conn:
            raw_counts = {
                table: conn.execute(
                    text(
                        f"SELECT COUNT(*) FROM {self._raw_schema}.{table} WHERE import_run_id = :import_run_id"
                    ),
                    {"import_run_id": run_id},
                ).scalar_one()
                for table in (*_RAW_TABLES_WITH_ID, *_RAW_TABLES_WITH_ROW_NO)
            }

            for table, source_count in source_counts.items():
                if raw_counts[table] != source_count:
                    failures.append(
                        f"raw_count_mismatch:{table}:source={source_count}:loaded={raw_counts[table]}"
                    )

            files_count = conn.execute(
                text(
                    f"SELECT COUNT(*) FROM {self._normalized_schema}.file_instance WHERE import_run_id = :import_run_id"
                ),
                {"import_run_id": run_id},
            ).scalar_one()
            if files_count != raw_counts["files"]:
                failures.append(f"normalized_file_instance_mismatch:expected={raw_counts['files']}:actual={files_count}")

            action_count = conn.execute(
                text(
                    f"SELECT COUNT(*) FROM {self._normalized_schema}.action_event WHERE import_run_id = :import_run_id"
                ),
                {"import_run_id": run_id},
            ).scalar_one()
            expected_actions = raw_counts["file_actions"] + raw_counts["_file_actions_old"]
            if action_count != expected_actions:
                failures.append(f"normalized_action_event_mismatch:expected={expected_actions}:actual={action_count}")

            duplicate_count = conn.execute(
                text(
                    f"SELECT COUNT(*) FROM {self._normalized_schema}.duplicate_evidence WHERE import_run_id = :import_run_id"
                ),
                {"import_run_id": run_id},
            ).scalar_one()
            if duplicate_count != raw_counts["duplicate_candidates"]:
                failures.append(
                    f"normalized_duplicate_evidence_mismatch:expected={raw_counts['duplicate_candidates']}:actual={duplicate_count}"
                )

            orphan_action_rows = conn.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM {self._normalized_schema}.action_event ae
                    LEFT JOIN {self._normalized_schema}.file_instance fi
                      ON fi.file_instance_id = ae.file_instance_id
                    WHERE ae.import_run_id = :import_run_id
                      AND fi.file_instance_id IS NULL
                    """
                ),
                {"import_run_id": run_id},
            ).scalar_one()
            if orphan_action_rows:
                failures.append(f"orphan_action_events:{orphan_action_rows}")

            orphan_duplicate_rows = conn.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM {self._normalized_schema}.duplicate_evidence de
                    LEFT JOIN {self._normalized_schema}.file_instance fi1
                      ON fi1.file_instance_id = de.file_instance_1_id
                    LEFT JOIN {self._normalized_schema}.file_instance fi2
                      ON fi2.file_instance_id = de.file_instance_2_id
                    WHERE de.import_run_id = :import_run_id
                      AND (fi1.file_instance_id IS NULL OR fi2.file_instance_id IS NULL)
                    """
                ),
                {"import_run_id": run_id},
            ).scalar_one()
            if orphan_duplicate_rows:
                failures.append(f"orphan_duplicate_evidence:{orphan_duplicate_rows}")

            orphan_deletion_links = conn.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM {self._normalized_schema}.deletion_audit_candidate_instance daci
                    LEFT JOIN {self._normalized_schema}.deletion_audit_candidate dac
                      ON dac.deletion_audit_candidate_id = daci.deletion_audit_candidate_id
                    LEFT JOIN {self._normalized_schema}.file_instance fi
                      ON fi.file_instance_id = daci.file_instance_id
                    WHERE daci.import_run_id = :import_run_id
                      AND (dac.deletion_audit_candidate_id IS NULL OR fi.file_instance_id IS NULL)
                    """
                ),
                {"import_run_id": run_id},
            ).scalar_one()
            if orphan_deletion_links:
                failures.append(f"orphan_deletion_audit_links:{orphan_deletion_links}")

            collision_count = conn.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM (
                        SELECT fi.filename
                        FROM {self._normalized_schema}.file_instance fi
                        WHERE fi.import_run_id = :import_run_id
                        GROUP BY fi.filename
                        HAVING COUNT(DISTINCT fi.content_identity_id) > 1
                    ) collisions
                    """
                ),
                {"import_run_id": run_id},
            ).scalar_one()

            surrogate_rows = conn.execute(
                text(
                    f"""
                    SELECT fi.absolute_path, fi.size_bytes, fi.mtime, ci.identity_value
                    FROM {self._normalized_schema}.file_instance fi
                    JOIN {self._normalized_schema}.content_identity ci
                      ON ci.content_identity_id = fi.content_identity_id
                    WHERE fi.import_run_id = :import_run_id
                      AND ci.identity_tier = 'SURROGATE'
                    """
                ),
                {"import_run_id": run_id},
            ).mappings().all()

            deterministic_surrogate_mismatches = 0
            for row in surrogate_rows:
                normalized_path = _normalize_path_for_surrogate(str(row["absolute_path"]))
                token = _stable_mtime_token(row["mtime"])
                expected = hashlib.sha256(
                    f"{normalized_path}|{row['size_bytes']}|{token}".encode("utf-8")
                ).hexdigest()
                if expected != row["identity_value"]:
                    deterministic_surrogate_mismatches += 1

            if deterministic_surrogate_mismatches:
                failures.append(f"surrogate_determinism_mismatch:{deterministic_surrogate_mismatches}")

        return {
            "source_counts": source_counts,
            "raw_counts": raw_counts,
            "collision_count": collision_count,
            "failures": failures,
        }

    def _append_failure(
        self,
        run_id: uuid.UUID,
        *,
        stage: str,
        error_code: str,
        error_message: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    f"""
                    INSERT INTO {self._normalized_schema}.import_failure_events (
                        id,
                        import_run_id,
                        stage,
                        error_code,
                        error_message,
                        context_json
                    )
                    VALUES (
                        :id,
                        :import_run_id,
                        :stage,
                        :error_code,
                        :error_message,
                        :context_json
                    )
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "import_run_id": run_id,
                    "stage": stage,
                    "error_code": error_code,
                    "error_message": error_message,
                    "context_json": json.dumps(context, sort_keys=True) if context is not None else None,
                },
            )

    def _mark_state(self, run_id: uuid.UUID, *, state: str, **extra_columns: Any) -> None:
        allowed_states = {"CREATED", "RAW_LOADED", "NORMALIZED", "VERIFIED", "FAILED"}
        if state not in allowed_states:
            raise LegacyImportError(f"Invalid import state: {state}")

        set_parts = ["state = :state", "updated_at = now()"]
        params: dict[str, Any] = {"import_run_id": run_id, "state": state}

        for key, value in extra_columns.items():
            set_parts.append(f"{key} = :{key}")
            params[key] = value

        with self._engine.begin() as conn:
            conn.execute(
                text(
                    f"UPDATE {self._normalized_schema}.import_runs "
                    f"SET {', '.join(set_parts)} "
                    "WHERE import_run_id = :import_run_id"
                ),
                params,
            )

    def _load_json(self, value: str | None) -> dict[str, Any]:
        if not value:
            return {}
        loaded = json.loads(value)
        if isinstance(loaded, dict):
            return loaded
        raise LegacyImportError("Expected JSON object payload")
