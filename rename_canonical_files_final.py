# rename_canonical_files_final.py
from pathlib import Path
import sqlite3
from datetime import datetime
import re
import os

# -------------------- CONFIG --------------------
ARCHIVE_ROOT = Path(r"C:\Users\micro\Documents\Better Up\Media-Manager")  # top-level folder
DB_PATH = Path("media-manager.db")
FILENAME_PREFIX = "ladylyb - Personal Chapters — "

# -------------------- FUNCTIONS --------------------
def parse_timestamp_from_filename(filename: str):
    """Try to extract a timestamp from the filename (YYYYMMDD or YYYY-MM-DD)"""
    patterns = [
        r"(\d{4})[-]?(\d{2})[-]?(\d{2})[_-]?(\d{2})(\d{2})(\d{2})",  # YYYYMMDD_HHMMSS
        r"(\d{4})[-]?(\d{2})[-]?(\d{2})"  # YYYYMMDD
    ]
    for pat in patterns:
        m = re.search(pat, filename)
        if m:
            groups = m.groups()
            try:
                if len(groups) == 6:
                    return datetime(int(groups[0]), int(groups[1]), int(groups[2]),
                                    int(groups[3]), int(groups[4]), int(groups[5]))
                elif len(groups) == 3:
                    return datetime(int(groups[0]), int(groups[1]), int(groups[2]), 0, 0, 0)
            except Exception:
                continue
    return None


def get_canonical_files(conn):
    """Return files not moved/archived (canonical)"""
    cur = conn.cursor()
    cur.execute("""
        SELECT f.id, f.path, f.filename, f.extension, f.exif_datetime, f.mtime
        FROM files f
        LEFT JOIN file_actions fa ON fa.file_id = f.id AND fa.action IN ('move','rename')
        WHERE fa.id IS NULL
          AND f.media_type IN ('image','video')
    """)
    return cur.fetchall()


def determine_best_timestamp(file_row):
    """Return datetime object or fallback"""
    exif = file_row["exif_datetime"]
    if exif:
        try:
            return datetime.strptime(exif, "%Y:%m:%d %H:%M:%S")
        except Exception:
            pass

    parsed = parse_timestamp_from_filename(file_row["filename"])
    if parsed:
        return parsed

    mtime = file_row["mtime"]
    if mtime:
        return datetime.fromtimestamp(mtime)

    # fallback
    return datetime(0, 1, 1, 0, 0, 0)


def canonical_filename(file_row, timestamp: datetime):
    """Generate canonical filename with given timestamp"""
    dt_str = timestamp.strftime("%Y-%m-%d_%H%M%S")
    ext = file_row["extension"] if file_row["extension"] else Path(file_row["filename"]).suffix
    if not ext.startswith(".") and ext:
        ext = f".{ext}"
    return FILENAME_PREFIX + dt_str + ext


def rename_file(conn, file_row, new_name):
    src_path = Path(file_row["path"])
    if not src_path.exists():
        print(f"[SKIP] File not found: {src_path}")
        return False

    target_path = src_path.with_name(new_name)

    # Avoid overwriting
    if target_path.exists():
        suffix = 1
        stem = target_path.stem
        while True:
            suffix_path = target_path.with_name(f"{stem}_{suffix}{target_path.suffix}")
            if not suffix_path.exists():
                target_path = suffix_path
                break
            suffix += 1

    # Rename
    os.rename(src_path, target_path)

    # Log action
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO file_actions (file_id, action, target_path, notes)
        VALUES (?, 'rename', ?, ?)
    """, (file_row["id"], str(target_path), "Renamed to canonical filename"))
    conn.commit()

    print(f"[RENAME] {src_path} → {target_path}")
    return True


def rename_canonical_files():
    print("Starting canonical renaming process...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    files = get_canonical_files(conn)
    print(f"Found {len(files)} canonical files to process.")

    renamed_count = 0
    skipped_count = 0

    for file_row in files:
        ts = determine_best_timestamp(file_row)
        new_name = canonical_filename(file_row, ts)
        success = rename_file(conn, file_row, new_name)
        if success:
            renamed_count += 1
        else:
            skipped_count += 1

    conn.close()
    print("Canonical renaming complete")
    print(f"Files renamed: {renamed_count}")
    print(f"Files skipped: {skipped_count}")


# -------------------- MAIN --------------------
if __name__ == "__main__":
    rename_canonical_files()
