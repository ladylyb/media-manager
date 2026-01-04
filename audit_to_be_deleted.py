# audit_to_be_deleted_final.py

import sqlite3
from pathlib import Path
import logging

# -------------------- CONFIG --------------------
ARCHIVE_ROOT = Path(r"C:\Users\micro\Documents\Better Up\Media-Manager")
TO_BE_DELETED = ARCHIVE_ROOT / "to-be-deleted"
DB_PATH = ARCHIVE_ROOT / "media-manager.db"
LOG_FILE = ARCHIVE_ROOT / "audit_to_be_deleted.log"

# -------------------- LOGGING --------------------
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# -------------------- HELPERS --------------------
def extract_original_filename(moved_path: Path) -> str:
    """
    Attempt to recover the original filename from the moved file.
    Strategy: remove any added prefixes (e.g., "File_Path_") and keep the basename.
    """
    name = moved_path.name
    # Adjust this pattern if other prefixes were used
    if name.startswith("File_Path_"):
        name = name[len("File_Path_") :]
    return name

# -------------------- MAIN --------------------
def audit_to_be_deleted():
    print(f"Scanning {TO_BE_DELETED} for audit...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    total_files = 0
    matched_files = 0
    unmatched_files = 0

    report = []

    for file_path in TO_BE_DELETED.rglob("*"):
        if not file_path.is_file():
            continue
        total_files += 1
        orig_filename = extract_original_filename(file_path)

        # Query files table by original filename
        cur.execute("SELECT * FROM files WHERE filename = ?", (orig_filename,))
        rows = cur.fetchall()

        if not rows:
            unmatched_files += 1
            logging.warning(f"No DB record found for: {file_path}")
            report.append((file_path, None, "No DB record"))
            continue

        # Handle multiple rows (e.g., duplicates)
        for row in rows:
            file_id = row["id"]
            cur.execute(
                "SELECT * FROM file_actions WHERE file_id = ?", (file_id,)
            )
            actions = cur.fetchall()
            action_summary = [a["action"] for a in actions] if actions else []

            matched_files += 1
            logging.info(
                f"[MATCHED] {file_path} → original filename: {orig_filename}, "
                f"DB id: {file_id}, actions: {action_summary}"
            )
            report.append((file_path, file_id, action_summary))

    # Summary
    print("\n--- Audit Summary ---")
    print(f"Total files scanned: {total_files}")
    print(f"Matched files: {matched_files}")
    print(f"Unmatched files: {unmatched_files}")
    logging.info(f"Audit complete. Total: {total_files}, Matched: {matched_files}, Unmatched: {unmatched_files}")

    conn.close()
    print(f"Detailed log written to {LOG_FILE}")
    return report

# -------------------- EXECUTE --------------------
if __name__ == "__main__":
    audit_to_be_deleted()
