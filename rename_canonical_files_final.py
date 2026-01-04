from pathlib import Path
import sqlite3
import shutil
from datetime import datetime

# -------------------- CONFIG --------------------
ARCHIVE_ROOT = Path(r"C:\Users\micro\Documents\Better Up\Media-Manager")  # Top-level archive folder
CANONICAL_PREFIX = "ladylyb - Personal Chapters — "

DB_PATH = Path("media-manager.db")

# -------------------- HELPERS --------------------
def get_canonical_files(conn):
    """Return files not moved/archived (canonical)"""
    cur = conn.cursor()
    cur.execute("""
        SELECT f.id, f.path, f.filename, f.extension, f.exif_datetime, f.mtime
        FROM files f
        LEFT JOIN file_actions fa 
               ON f.id = fa.file_id 
              AND fa.action IN ('move', 'rename')
        WHERE fa.file_id IS NULL
          AND f.media_type IN ('image','video')
    """)
    return cur.fetchall()


def format_timestamp(exif_datetime, mtime):
    """Generate YYYY-MM-DD_HHMMSS from EXIF or filesystem times"""
    ts = None
    if exif_datetime:
        try:
            ts = datetime.strptime(exif_datetime, "%Y:%m:%d %H:%M:%S")
        except Exception:
            ts = None
    if ts is None and mtime:
        try:
            ts = datetime.fromtimestamp(float(mtime))
        except Exception:
            ts = None
    if ts:
        return ts.strftime("%Y-%m-%d_%H%M%S")
    else:
        return "0000-00-00_000000"

# -------------------- MAIN --------------------
def rename_canonical_files():
    print("Starting canonical renaming process...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    files = get_canonical_files(conn)
    print(f"Found {len(files)} canonical files to process.")

    for idx, row in enumerate(files, 1):
        file_id = row["id"]
        src_path = Path(row["path"])
        extension = row["extension"] or src_path.suffix
        timestamp_str = format_timestamp(row["exif_datetime"], row["mtime"])

        # Generate canonical filename
        new_filename = f"{CANONICAL_PREFIX}{timestamp_str}{extension}"
        target_path = src_path.with_name(new_filename)

        print(f"[{idx}/{len(files)}] File ID {file_id}: {src_path.name} → {new_filename}")

        # Skip if source missing
        if not src_path.exists():
            print(f"  ⚠ Source file missing, skipping.")
            continue

        # Avoid overwriting
        if target_path.exists():
            suffix = 1
            stem = target_path.stem
            while (target_path.parent / f"{stem}_{suffix}{target_path.suffix}").exists():
                suffix += 1
            target_path = target_path.parent / f"{stem}_{suffix}{target_path.suffix}"
            print(f"  ⚠ Target exists, renamed to {target_path.name}")

        # Rename file
        try:
            shutil.move(str(src_path), str(target_path))
        except Exception as e:
            print(f"  ❌ Failed to rename: {e}")
            continue

        # Log action
        cur.execute("""
            INSERT INTO file_actions (file_id, action, target_path, notes)
            VALUES (?, 'rename', ?, ?)
        """, (file_id, str(target_path), f"Renamed canonical file"))

        conn.commit()

    conn.close()
    print("Canonical renaming complete.")


if __name__ == "__main__":
    rename_canonical_files()
