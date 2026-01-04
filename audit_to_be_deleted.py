from pathlib import Path
import sqlite3
import csv
import argparse
import logging

# -------------------- CONFIG --------------------
TO_BE_DELETED = Path(r"C:\Users\micro\Documents\Better Up\Media-Manager\to-be-deleted")
DB_PATH = Path("media-manager.db")
LOG_FILE = Path("audit_to_be_deleted.log")
REPORT_FILE = Path("audit_to_be_deleted_report.csv")

# -------------------- ARGPARSE --------------------
parser = argparse.ArgumentParser(description="Audit files in to-be-deleted folder against media-manager database")
parser.add_argument("--dry-run", action="store_true", help="Run audit without any changes")
args = parser.parse_args()

# -------------------- LOGGING --------------------
logging.basicConfig(
    filename=LOG_FILE,
    filemode="w",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logging.info("Starting audit of to-be-deleted folder: %s", TO_BE_DELETED)

# -------------------- DB CONNECTION --------------------
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# -------------------- AUDIT --------------------
rows = []

for file_path in TO_BE_DELETED.rglob("*.*"):
    file_path_str = str(file_path)
    status = ""
    file_id = None
    file_action = None

    # Check if file is in files table
    cur.execute("SELECT * FROM files WHERE path = ?", (file_path_str,))
    row = cur.fetchone()
    if row:
        file_id = row["id"]
        # Check if an action exists
        cur.execute("SELECT * FROM file_actions WHERE file_id = ?", (file_id,))
        action_row = cur.fetchone()
        file_action = action_row["action"] if action_row else None
        if file_action:
            status = f"Processed ({file_action})"
        else:
            status = "In files table, no action"
    else:
        status = "Not in files table"

    logging.info("[AUDIT] %s → %s", file_path, status)

    rows.append({
        "file_path": file_path_str,
        "file_id": file_id,
        "file_action": file_action,
        "status": status
    })

# -------------------- EXPORT REPORT --------------------
with open(REPORT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["file_path", "file_id", "file_action", "status"])
    writer.writeheader()
    writer.writerows(rows)

logging.info("Audit complete. Report saved to: %s", REPORT_FILE)
print(f"Audit complete. Report saved to: {REPORT_FILE}")
print(f"Log file: {LOG_FILE}")

# -------------------- SUMMARY --------------------
total_files = len(rows)
missing_in_db = sum(1 for r in rows if r["status"] == "Not in files table")
no_action = sum(1 for r in rows if r["status"] == "In files table, no action")

print(f"Total files audited: {total_files}")
print(f"Files missing in DB: {missing_in_db}")
print(f"Files in DB with no action: {no_action}")

logging.info("Summary: total=%d, missing_in_db=%d, no_action=%d",
             total_files, missing_in_db, no_action)

conn.close()
