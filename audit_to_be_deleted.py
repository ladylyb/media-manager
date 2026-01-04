from pathlib import Path
import sqlite3
import csv
from datetime import datetime

# -------------------- CONFIG --------------------
TO_BE_DELETED_FOLDER = Path(r"C:\Users\micro\Documents\Better Up\Media-Manager\to-be-deleted")
DB_PATH = Path("media-manager.db")
OUTPUT_CSV = Path("audit_to_be_deleted_report.csv")

# -------------------- MAIN --------------------
def audit_to_be_deleted():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Load all files into memory for fast lookup
    print("Loading files from DB into memory...")
    cur.execute("SELECT id, path, filename FROM files")
    files_dict = {row["path"]: row for row in cur.fetchall()}

    # Load all file_actions into memory
    print("Loading file actions from DB into memory...")
    cur.execute("SELECT file_id, action FROM file_actions")
    file_actions_dict = {}
    for row in cur.fetchall():
        file_actions_dict.setdefault(row["file_id"], []).append(row["action"])

    # Prepare CSV output
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=[
            "file_path", "found_in_db", "file_id", "actions", "notes"
        ])
        writer.writeheader()

        total_files = 0
        found_in_db_count = 0

        for file_path in TO_BE_DELETED_FOLDER.rglob("*"):
            if file_path.is_file():
                total_files += 1
                file_path_str = str(file_path)

                row = {
                    "file_path": file_path_str,
                    "found_in_db": False,
                    "file_id": "",
                    "actions": "",
                    "notes": "",
                }

                db_entry = files_dict.get(file_path_str)
                if db_entry:
                    row["found_in_db"] = True
                    row["file_id"] = db_entry["id"]
                    actions = file_actions_dict.get(db_entry["id"], [])
                    row["actions"] = ",".join(actions)
                    found_in_db_count += 1
                else:
                    row["notes"] = "File not found in DB"

                writer.writerow(row)

    conn.close()
    print(f"Audit complete. Total files scanned: {total_files}, Found in DB: {found_in_db_count}")
    print(f"Report saved to {OUTPUT_CSV}")


if __name__ == "__main__":
    audit_to_be_deleted()
