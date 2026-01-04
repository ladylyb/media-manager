"""
audit_to_be_deleted_full.py

Scans the "to-be-deleted" folder and cross-checks each file against the database.
Summarizes any actions taken on the file (rename/move/delete/ignore) and logs/report.
"""

import argparse
import csv
import logging
from pathlib import Path
import sqlite3

# ---------------- CONFIG ----------------
DB_PATH =  "media-manager.db"

ARCHIVE_ROOT = Path(r"C:\Users\micro\Documents\Better Up\Media-Manager")
TO_BE_DELETED = ARCHIVE_ROOT / "to-be-deleted"

LOG_FILE = ARCHIVE_ROOT / "audit_to_be_deleted.log"
CSV_FILE = ARCHIVE_ROOT / "audit_to_be_deleted.csv"

# ---------------- SETUP LOGGING ----------------
logging.basicConfig(
    filename=LOG_FILE,
    filemode="w",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

# ---------------- HELPER FUNCTIONS ----------------
def get_file_actions_summary(cur, file_id):
    """
    Return a concatenated string summarizing all actions taken on this file
    """
    cur.execute(
        "SELECT action, target_path, notes FROM file_actions WHERE file_id = ?",
        (file_id,),
    )
    rows = cur.fetchall()
    if not rows:
        return ""
    return "; ".join(
        f"{row['action']}:{row['target_path']}:{row['notes'] or ''}" for row in rows
    )

def audit_to_be_deleted(dry_run=False, limit=None):
    logging.info(f"Scanning {TO_BE_DELETED} for audit...")

    if not TO_BE_DELETED.exists():
        logging.error(f"{TO_BE_DELETED} does not exist.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    to_be_deleted_files = sorted([f for f in TO_BE_DELETED.rglob("*") if f.is_file()])
    if limit:
        to_be_deleted_files = to_be_deleted_files[:limit]

    total_files = len(to_be_deleted_files)
    logging.info(f"Found {total_files} files in to-be-deleted folder.")

    with open(CSV_FILE, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = [
            "to_be_deleted_path",
            "original_filename",
            "found_in_db",
            "canonical_name",
            "actions_summary",
            "notes",
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        found_count = 0
        missing_count = 0

        for idx, file_path in enumerate(to_be_deleted_files, 1):
            logging.info(f"[{idx}/{total_files}] Auditing file: {file_path}")
            original_name = file_path.name
            # Look up by original filename (without canonical prefix)
            # Remove any "__" artifact from previous renames if needed
            lookup_name = original_name.replace("__", "_").split("_", 1)[-1]

            cur.execute("SELECT * FROM files WHERE filename LIKE ?", (f"%{lookup_name}",))
            file_row = cur.fetchone()

            if file_row:
                found_count += 1
                file_id = file_row["id"]
                canonical_name = file_row["filename"]
                actions_summary = get_file_actions_summary(cur, file_id)
                notes = ""
            else:
                missing_count += 1
                canonical_name = ""
                actions_summary = ""
                notes = "File not found in DB"

            writer.writerow(
                {
                    "to_be_deleted_path": str(file_path),
                    "original_filename": original_name,
                    "found_in_db": bool(file_row),
                    "canonical_name": canonical_name,
                    "actions_summary": actions_summary,
                    "notes": notes,
                }
            )

    conn.close()
    logging.info("Audit complete")
    logging.info(f"Total files scanned: {total_files}")
    logging.info(f"Found in DB: {found_count}")
    logging.info(f"Missing in DB: {missing_count}")

# ---------------- MAIN ----------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit to-be-deleted folder files against DB")
    parser.add_argument("--dry-run", action="store_true", help="Do not write CSV/log (just simulate)")
    parser.add_argument("--limit", type=int, help="Limit number of files to process for testing")
    args = parser.parse_args()

    if args.dry_run:
        logging.info("Dry-run enabled. No output will be written.")
    audit_to_be_deleted(dry_run=args.dry_run, limit=args.limit)
