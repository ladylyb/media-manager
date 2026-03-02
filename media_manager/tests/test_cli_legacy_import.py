from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from media_manager.app.cli import main
from media_manager.app.persistence.legacy_import import LegacyImportService


def _build_legacy_sqlite(path: Path) -> Path:
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            root_path TEXT NOT NULL,
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            finished_at DATETIME,
            notes TEXT
        );

        CREATE TABLE files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            filename TEXT NOT NULL,
            extension TEXT,
            size_bytes INTEGER NOT NULL,
            mtime REAL,
            ctime REAL,
            hash_partial TEXT,
            hash_full TEXT,
            hash_algo TEXT,
            media_type TEXT,
            duration REAL,
            width INTEGER,
            height INTEGER,
            codec TEXT,
            bitrate INTEGER,
            exif_datetime TEXT,
            is_hashed INTEGER DEFAULT 0,
            is_metadata_extracted INTEGER DEFAULT 0,
            camera_model TEXT,
            orientation TEXT
        );

        CREATE TABLE file_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            target_path TEXT,
            decided_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        );

        CREATE TABLE _file_actions_old (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            target_path TEXT,
            decided_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        );

        CREATE TABLE duplicate_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id_1 INTEGER NOT NULL,
            file_id_2 INTEGER NOT NULL,
            match_type TEXT NOT NULL,
            confidence_score INTEGER NOT NULL,
            reason TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            duplicate_group_id INTEGER
        );

        CREATE TABLE deletion_audit_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            audit_name TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        );

        CREATE TABLE deletion_audit_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            audit_run_id INTEGER NOT NULL,
            reconstructed_name TEXT,
            observed_path TEXT NOT NULL,
            audit_notes TEXT,
            raw_actions_snapshot TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE deletion_audit_candidate_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            audit_candidate_id INTEGER NOT NULL,
            related_file_id INTEGER NOT NULL
        );

        CREATE TABLE _tmp_deletion_audit_import (
            to_be_deleted_path TEXT,
            reconstructed_filename TEXT,
            found_in_db TEXT,
            file_id INTEGER,
            actions TEXT,
            notes TEXT
        );
        """
    )

    cur.execute(
        "INSERT INTO scans (id, root_path, notes) VALUES (1, ?, 'seed')",
        (r"C:\\legacy\\root",),
    )

    cur.execute(
        """
        INSERT INTO files (
            id, scan_id, path, filename, extension, size_bytes, mtime, ctime,
            hash_partial, hash_full, hash_algo, media_type, duration, width, height, codec,
            bitrate, exif_datetime, is_hashed, is_metadata_extracted, camera_model, orientation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            1,
            r"C:\\legacy\\root\\IMG_0001.JPG",
            "IMG_0001.JPG",
            "jpg",
            100,
            1700000000.0,
            1700000000.0,
            "abc",
            "a" * 64,
            "sha256",
            "image",
            0.0,
            100,
            100,
            "jpeg",
            1000,
            "2024:01:01 10:00:00",
            1,
            1,
            "cam",
            "1",
        ),
    )

    cur.execute(
        """
        INSERT INTO files (
            id, scan_id, path, filename, extension, size_bytes, mtime, ctime,
            hash_partial, hash_full, hash_algo, media_type, duration, width, height, codec,
            bitrate, exif_datetime, is_hashed, is_metadata_extracted, camera_model, orientation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            2,
            1,
            r"C:\\legacy\\root\\IMG_0001_COPY.JPG",
            "IMG_0001.JPG",
            "jpg",
            100,
            1700001000.0,
            1700001000.0,
            "def",
            None,
            None,
            "image",
            0.0,
            100,
            100,
            "jpeg",
            1000,
            "",
            0,
            1,
            "cam",
            "1",
        ),
    )

    cur.execute(
        "INSERT INTO file_actions (id, file_id, action, target_path, notes) VALUES (1, 1, 'move', ?, 'n1')",
        (r"C:\\target\\IMG_0001.JPG",),
    )
    cur.execute(
        "INSERT INTO _file_actions_old (id, file_id, action, notes) VALUES (1, 2, 'keep', 'n2')"
    )
    cur.execute(
        "INSERT INTO duplicate_candidates (id, file_id_1, file_id_2, match_type, confidence_score, reason) VALUES (1, 1, 2, 'exact_hash', 99, 'same')"
    )
    cur.execute("INSERT INTO deletion_audit_runs (id, audit_name, notes) VALUES (1, 'audit-1', 'ok')")
    cur.execute(
        "INSERT INTO deletion_audit_candidates (id, audit_run_id, reconstructed_name, observed_path, audit_notes, raw_actions_snapshot) VALUES (1, 1, 'IMG_0001.JPG', ?, 'note', '{\"a\":1}')",
        (r"C:\\legacy\\root\\IMG_0001.JPG",),
    )
    cur.execute(
        "INSERT INTO deletion_audit_candidate_files (id, audit_candidate_id, related_file_id) VALUES (1, 1, 1)"
    )
    cur.execute(
        "INSERT INTO _tmp_deletion_audit_import (to_be_deleted_path, reconstructed_filename, found_in_db, file_id, actions, notes) VALUES (?, 'IMG_0001.JPG', 'yes', 1, 'move', 'tmp')",
        (r"C:\\legacy\\root\\IMG_0001.JPG",),
    )

    conn.commit()
    conn.close()
    return path


def test_cli_legacy_import_happy_path(tmp_path: Path, test_database_url: str, monkeypatch, capsys, db_engine) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    sqlite_path = _build_legacy_sqlite(tmp_path / "legacy.db")

    exit_code = main([
        "legacy-import",
        "--sqlite-path",
        str(sqlite_path),
        "--pg-url",
        test_database_url,
    ])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Legacy Import Summary" in output
    assert "State: VERIFIED" in output

    with db_engine.begin() as conn:
        import_runs = conn.execute(text("SELECT COUNT(*) FROM legacy_3nf.import_runs")).scalar_one()
        file_instances = conn.execute(text("SELECT COUNT(*) FROM legacy_3nf.file_instance")).scalar_one()
        canonical_candidates = conn.execute(text("SELECT COUNT(*) FROM legacy_3nf.canonical_candidate")).scalar_one()
        runtime_runs = conn.execute(text("SELECT COUNT(*) FROM runs")).scalar_one()

    assert import_runs == 1
    assert file_instances == 2
    assert canonical_candidates == 2
    assert runtime_runs == 0


def test_cli_legacy_import_idempotent_same_run_id(tmp_path: Path, test_database_url: str, monkeypatch, db_engine) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    sqlite_path = _build_legacy_sqlite(tmp_path / "legacy-idempotent.db")
    run_id = str(uuid.uuid4())

    args = [
        "legacy-import",
        "--sqlite-path",
        str(sqlite_path),
        "--pg-url",
        test_database_url,
        "--import-run-id",
        run_id,
    ]

    assert main(args) == 0
    assert main(args) == 0

    with db_engine.begin() as conn:
        run_count = conn.execute(
            text("SELECT COUNT(*) FROM legacy_3nf.import_runs WHERE import_run_id = :id"),
            {"id": run_id},
        ).scalar_one()
        action_count = conn.execute(
            text("SELECT COUNT(*) FROM legacy_3nf.action_event WHERE import_run_id = :id"),
            {"id": run_id},
        ).scalar_one()

    assert run_count == 1
    assert action_count == 2


def test_legacy_import_resume_after_failure(tmp_path: Path, db_engine) -> None:
    sqlite_path = _build_legacy_sqlite(tmp_path / "legacy-resume.db")
    service = LegacyImportService(db_engine)
    run_id = uuid.uuid4()

    original = service._normalize_phase
    state = {"failed_once": False}

    def _fail_once(import_run_id: uuid.UUID) -> None:
        if not state["failed_once"]:
            state["failed_once"] = True
            raise RuntimeError("forced-normalize-failure")
        original(import_run_id)

    service._normalize_phase = _fail_once  # type: ignore[assignment]

    try:
        with pytest.raises(RuntimeError, match="forced-normalize-failure"):
            service.import_sqlite(sqlite_path, import_run_id=run_id)
    finally:
        service._normalize_phase = original  # type: ignore[assignment]

    summary = service.import_sqlite(sqlite_path, import_run_id=run_id)
    assert summary.state == "VERIFIED"

    with db_engine.begin() as conn:
        run_state = conn.execute(
            text("SELECT state FROM legacy_3nf.import_runs WHERE import_run_id = :id"),
            {"id": run_id},
        ).scalar_one()
        failure_events = conn.execute(
            text("SELECT COUNT(*) FROM legacy_3nf.import_failure_events WHERE import_run_id = :id"),
            {"id": run_id},
        ).scalar_one()

    assert run_state == "VERIFIED"
    assert failure_events >= 1
