from pathlib import Path
import sqlite3
import logging
import csv
import argparse
import sys

# -------------------- CONFIG --------------------
ARCHIVE_ROOT = Path(r"C:\Users\micro\Documents\Better Up\Media-Manager")
TO_BE_DELETED = ARCHIVE_ROOT / "to-be-deleted"
DB_PATH = ARCHIVE_ROOT / "media-manager.db"

LOG_FILE = TO_BE_DELETED / "audit_to_be_deleted.log"
CSV_FILE = TO_BE_DELETED / "audit_to_be_deleted.csv"

# -------------------- ARGPARSE --------------------
parser = argparse.ArgumentParser(description="Audit files in to-be-deleted folder")
parser.add_argument("--dry-run", action="store_true", help="Do not modify anything, just log")
parser.add_argument("--limit", type=int, default=None, help="Limit to first N files for testing")
args = parser.parse_args()

# -------------------- LOGGING --------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8")
    ]
)

# -------------------- MAIN --------------------
def audit_to_be_deleted():
    logging.info(f"Scanning {TO_BE_DELETED} for audit...")
    if not TO_BE_DELETED.exists():
        logging.error(f"{TO_BE_DELETED} does not exist.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    all_files = list(TO_BE_DELETED.rglob("*"))
    files_only = [f for f in all_files if f.is_file()]
    if args.limit:
        files_only = files_only[:args.limit]

    logging.info(f"Found {len(files_only)} files to audit.")

    with CSV_FILE.open("w", newline="", encoding="utf-8") as csvfile:
        fieldnames = [
            "to_be_deleted_path", "original_filename", "found_in_db",
            "canonical_name", "notes"
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        count_found = 0
        count_missing = 0

        for file_path in files_only:
            notes = []
            to_be_deleted_path = str(file_path)
            # Reconstruct original filename by removing canonicalization transforms
            original_filename = file_path.name
            # Remove any prepended folders/underscores if present
            if "__" in original_filename:
                original_filename = original_filename.split("__")[-1]

            # Remove suffix added by duplicates handling (_1, _2, etc.)
            stem = Path(original_filename).stem
            if "_" in stem:
                parts = stem.rsplit("_", 1)
                if parts[1].isdigit():
                    original_filename = parts[0] + file_path.suffix

            # Lookup in DB
            cur.execute("SELECT filename FROM files WHERE filename = ?", (original_filename,))
            row = cur.fetchone()

            if row:
                found_in_db = True
                canonical_name = row["filename"]
                count_found += 1
            else:
                found_in_db = False
                canonical_name = ""
                count_missing += 1
                notes.append("Not found in DB")

            logging.info(f"[{file_path}] Found in DB: {found_in_db}")
            writer.writerow({
                "to_be_deleted_path": to_be_deleted_path,
                "original_filename": original_filename,
                "found_in_db": found_in_db,
                "canonical_name": canonical_name,
                "notes": "; ".join(notes)
            })

    logging.info("Audit complete")
    logging.info(f"Total files scanned: {len(files_only)}")
    logging.info(f"Found in DB: {count_found}")
    logging.info(f"Missing in DB: {count_missing}")

    conn.close()

# -------------------- ENTRY POINT --------------------
if __name__ == "__main__":
    if args.dry_run:
        logging.info("Running in dry-run mode (no changes will be made).")
    audit_to_be_deleted()
