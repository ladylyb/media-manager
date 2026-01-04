import os
import sqlite3
import time
from pathlib import Path

# -----------------------------
# CONFIG
# -----------------------------
# DB_PATH = r"media-manager.db"     # path to your sqlite db
DB_PATH = os.path.join(os.path.dirname(__file__), "media-manager.db")

ROOT_PATH = r"C:\Users\micro\Documents\Better Up\Archive\OWN" # root folder to scan
BATCH_SIZE = 1000

# -----------------------------
# HELPERS
# -----------------------------
def get_extension(filename: str) -> str | None:
    ext = os.path.splitext(filename)[1].lower()
    return ext[1:] if ext else None

def unix_time(ts):
    return float(ts) if ts else None

# -----------------------------
# MAIN SCAN
# -----------------------------
def run_scan(db_path: str, root_path: str):
    root_path = os.path.abspath(root_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    cur = conn.cursor()

    # Create scan entry
    cur.execute(
        "INSERT INTO scans (root_path) VALUES (?)",
        (root_path,)
    )
    scan_id = cur.lastrowid
    conn.commit()

    print(f"Started scan {scan_id} on {root_path}")

    batch = []
    file_count = 0
    start_time = time.time()

    for dirpath, _, filenames in os.walk(root_path):
        for name in filenames:
            try:
                full_path = os.path.join(dirpath, name)

                stat = os.stat(full_path)

                batch.append((
                    scan_id,
                    full_path,
                    name,
                    get_extension(name),
                    stat.st_size,
                    unix_time(stat.st_mtime),
                    unix_time(stat.st_ctime)
                ))

                if len(batch) >= BATCH_SIZE:
                    cur.executemany(
                        """
                        INSERT INTO files (
                            scan_id, path, filename, extension,
                            size_bytes, mtime, ctime
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        batch
                    )
                    conn.commit()
                    file_count += len(batch)
                    batch.clear()

            except (PermissionError, FileNotFoundError):
                # Common on Windows (locked/system files)
                continue
            except Exception as e:
                print(f"Error reading file: {full_path}")
                print(e)

    # Final flush
    if batch:
        cur.executemany(
            """
            INSERT INTO files (
                scan_id, path, filename, extension,
                size_bytes, mtime, ctime
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            batch
        )
        conn.commit()
        file_count += len(batch)

    # Mark scan complete
    cur.execute(
        "UPDATE scans SET finished_at = CURRENT_TIMESTAMP WHERE id = ?",
        (scan_id,)
    )
    conn.commit()

    elapsed = time.time() - start_time
    print(f"Scan {scan_id} complete")
    print(f"Files indexed: {file_count}")
    print(f"Elapsed time: {elapsed:.2f} seconds")

    conn.close()

# -----------------------------
# ENTRY POINT
# -----------------------------
if __name__ == "__main__":
    run_scan(DB_PATH, ROOT_PATH)

