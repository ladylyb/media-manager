"""
audit_to_be_deleted_full.py

Scans the "to-be-deleted" folder and cross-checks each file against the database.
Summarizes any actions taken on the file (rename/move/delete/ignore) and logs/report.
"""

from pathlib import Path
from datetime import datetime
import sqlite3
import logging
import csv
import argparse

# -------------------- CONFIG --------------------
# DB_PATH = "media-manager.db"

# ARCHIVE_ROOT = Path(r"C:\Users\micro\Documents\Better Up\Media-Manager")
# TO_BE_DELETED = ARCHIVE_ROOT / "to-be-deleted"

# LOG_FILE = ARCHIVE_ROOT / f"cleanup_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
# LOG_FILE = ARCHIVE_ROOT / f"logs/audit_to_be_deleted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
# CSV_FILE = ARCHIVE_ROOT / f"data/audit_to_be_deleted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

# -------------------- LOGGING --------------------
def log_reconstruction(file_path: Path, reconstructed_name: str):
    logging.debug(
        "RECONSTRUCT | disk='%s' | reconstructed='%s'",
        file_path.name,
        reconstructed_name
    )

def setup_logging(log_file: Path):
    """
    Ensure log directory exists and configure logging safely.
    """
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )


# -------------------- HELPERS --------------------
def ensure_parent_dir(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)

def reconstruct_original_filename(file_path: Path) -> str:
    """
    Reverse flattening and suffixing applied during archival.
    """
    original = file_path.name

    # Remove flattened folder prefixes (Folder__File.ext)
    if "__" in original:
        original = original.split("__", 1)[-1]

    # Remove duplicate suffix (_1, _2, etc.)
    stem = Path(original).stem
    suffix = Path(original).suffix
    if "_" in stem:
        base, tail = stem.rsplit("_", 1)
        if tail.isdigit():
            original = base + suffix

    return original

# -------------------- MAIN --------------------
def audit_to_be_deleted(limit: int | None = None):
    logging.info(f"Scanning {TO_BE_DELETED} for audit...")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    files_only = [p for p in TO_BE_DELETED.rglob("*") if p.is_file()]
    if limit:
        files_only = files_only[:limit]

    total = len(files_only)
    found = 0
    missing = 0
    with_actions = 0
    without_actions = 0
    
    ensure_parent_dir(CSV_FILE)
    
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = [
            "to_be_deleted_path",
            "reconstructed_filename",
            "found_in_db",
            "file_id",
            "actions",
            "notes"
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for file_path in files_only:
            notes = []
            reconstructed = reconstruct_original_filename(file_path)
            
            log_reconstruction(file_path, reconstructed)

            cur.execute(
                "SELECT id FROM files WHERE filename = ?",
                (reconstructed,)
            )
            file_row = cur.fetchone()

            if not file_row:
                missing += 1
                notes.append("Not found in files table")
                # logging.warning(f"No DB record for: {file_path}")
                logging.warning(
                    "DB MISS | reconstructed='%s' | disk='%s'",
                    reconstructed,
                    file_path.name
                )
                
                writer.writerow({
                    "to_be_deleted_path": str(file_path),
                    "reconstructed_filename": reconstructed,
                    "found_in_db": False,
                    "file_id": "",
                    "actions": "",
                    "notes": "; ".join(notes)
                })
                continue

            found += 1
            file_id = file_row["id"]

            cur.execute(
                """
                SELECT action, target_path, decided_at
                FROM file_actions
                WHERE file_id = ?
                ORDER BY decided_at
                """,
                (file_id,)
            )
            actions = cur.fetchall()

            if actions:
                with_actions += 1
                action_summary = " | ".join(
                    f"{a['action']} → {a['target_path'] or ''}".strip()
                    for a in actions
                )
            else:
                without_actions += 1
                action_summary = ""
                notes.append("No recorded action")

            logging.info(
                f"[AUDIT] {file_path.name} | found | actions={bool(actions)}"
            )

            writer.writerow({
                "to_be_deleted_path": str(file_path),
                "reconstructed_filename": reconstructed,
                "found_in_db": True,
                "file_id": file_id,
                "actions": action_summary,
                "notes": "; ".join(notes)
            })

    conn.close()

    # -------------------- SUMMARY --------------------
    logging.info("Audit complete")
    logging.info(f"Total files scanned: {total}")
    logging.info(f"Found in DB: {found}")
    logging.info(f"Missing in DB: {missing}")
    logging.info(f"With actions: {with_actions}")
    logging.info(f"No actions recorded: {without_actions}")

# -------------------- ENTRY --------------------
# -------------------------
# Entry point
# -------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Audit files in to-be-deleted folder against media-manager database."
    )

    parser.add_argument(
        "--db",
        type=Path,
        default=Path("media-manager.db"),
        help="Path to SQLite database (default: media-manager.db)",
    )

    parser.add_argument(
        "--archive-root",
        type=Path,
        required=True,
        help="ARCHIVE_ROOT path (e.g. Media-Manager folder)",
    )

    parser.add_argument(
        "--to-be-deleted",
        type=Path,
        help="Override to-be-deleted folder (default: ARCHIVE_ROOT/to-be-deleted)",
    )

    parser.add_argument(
        "--log",
        type=Path,
        help="Optional log file path (default: ARCHIVE_ROOT/logs/...)",
    )

    parser.add_argument(
        "--csv",
        type=Path,
        help="Optional CSV output path (default: ARCHIVE_ROOT/data/...)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run audit in dry-run mode (no behavior change, explicit safety flag)",
    )

    parser.add_argument(
        "--limit",
        type=int,
        help="Only audit first N files (for testing)",
    )

    args = parser.parse_args()

    # -------------------------
    # Resolve paths
    # -------------------------
    global DB_PATH, ARCHIVE_ROOT, TO_BE_DELETED, LOG_FILE, CSV_FILE

    DB_PATH = args.db
    ARCHIVE_ROOT = args.archive_root
    TO_BE_DELETED = args.to_be_deleted or (ARCHIVE_ROOT / "to-be-deleted")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    LOG_FILE = args.log or (
        ARCHIVE_ROOT / f"logs/audit_to_be_deleted_{timestamp}.log"
    )
    CSV_FILE = args.csv or (
        ARCHIVE_ROOT / f"data/audit_to_be_deleted_{timestamp}.csv"
    )

    setup_logging(LOG_FILE)

    # -------------------------
    # Validation
    # -------------------------
    if not DB_PATH.exists():
        logging.error("Database not found: %s", DB_PATH)
        return

    if not TO_BE_DELETED.exists():
        logging.error("to-be-deleted folder not found: %s", TO_BE_DELETED)
        return

    logging.info("=" * 70)
    logging.info("Starting to-be-deleted audit")
    logging.info("DB: %s", DB_PATH.resolve())
    logging.info("Archive root: %s", ARCHIVE_ROOT.resolve())
    logging.info("To-be-deleted: %s", TO_BE_DELETED.resolve())
    logging.info("Mode: %s", "DRY-RUN" if args.dry_run else "AUDIT")
    if args.limit:
        logging.info("Limit: first %d files", args.limit)
    logging.info("=" * 70)

    audit_to_be_deleted(limit=args.limit)

if __name__ == "__main__":
    main()
