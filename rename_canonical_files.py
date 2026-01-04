from pathlib import Path
import sqlite3
from datetime import datetime
import re

DB_PATH = Path("media-manager.db")
PREFIX = "ladylyb - Personal Chapters —"

# -------------------- FUNCTIONS --------------------
def parse_filename_timestamp(filename: str):
    """Extract YYYYMMDD or YYYY-MM-DD patterns from original filename if possible."""
    date_match = re.search(r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})", filename)
    if date_match:
        y, m, d = date_match.groups()
        return f"{y}-{m}-{d}", "000000"
    return None, None

def select_best_timestamp(file_row):
    """Determine best timestamp for canonical filename."""
    # 1. EXIF
    exif = file_row["exif_datetime"]
    if exif:
        try:
            dt = datetime.strptime(exif, "%Y:%m:%d %H:%M:%S")
            return dt.strftime("%Y-%m-%d"), dt.strftime("%H%M%S")
        except ValueError:
            pass

    # 2. Filename
    date_part, time_part = parse_filename_timestamp(file_row["filename"])
    if date_part:
        return date_part, time_part

    # 3. Filesystem timestamps
    for ts_field in ("ctime", "mtime"):
        ts = file_row[ts_field]
        if ts:
            try:
                dt = datetime.fromtimestamp(ts)
                return dt.strftime("%Y-%m-%d"), dt.strftime("%H%M%S")
            except Exception:
                pass

    # Fallback
    return "0000-00-00", "000000"

def rename_canonical_files():
    print("Starting canonical renaming process...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Select canonical files: not archived, not duplicates
    cur.execute("""
        SELECT f.*
        FROM files f
        LEFT JOIN file_actions fa ON f.id = fa.file_id AND fa.action IN ('move', 'rename')
        WHERE fa.id IS NULL
        AND f.media_type IN ('image', 'video')
    """)
    files = cur.fetchall()

    print(f"Found {len(files)} canonical files to process.\n")

    renamed_count = 0
    skipped_count = 0

    for file_row in files:
        orig_path = Path(file_row["path"])
        print(f"Processing file ID {file_row['id']}: {orig_path}")

        if not orig_path.exists():
            print(f"  → File does not exist. Skipping.")
            skipped_count += 1
            continue

        date_str, time_str = select_best_timestamp(file_row)
        ext = orig_path.suffix  # preserve original extension
        canonical_name = f"{PREFIX} {date_str}_{time_str}{ext}"

        target_path = orig_path.parent / canonical_name

        # Avoid overwriting
        if target_path.exists():
            suffix = 1
            while (orig_path.parent / f"{PREFIX} {date_str}_{time_str}_{suffix}{ext}").exists():
                suffix += 1
            target_path = orig_path.parent / f"{PREFIX} {date_str}_{time_str}_{suffix}{ext}"

        # Rename file
        orig_path.rename(target_path)
        renamed_count += 1

        # Log in file_actions
        cur.execute("""
            INSERT INTO file_actions (file_id, action, target_path, notes)
            VALUES (?, 'rename', ?, 'Renamed to canonical format')
        """, (file_row["id"], str(target_path)))

        print(f"  → Renamed to {target_path.name}")

    conn.commit()
    conn.close()

    print("\nCanonical renaming complete.")
    print(f"  Total files processed: {len(files)}")
    print(f"  Files renamed: {renamed_count}")
    print(f"  Files skipped: {skipped_count}")

# -------------------- MAIN --------------------
if __name__ == "__main__":
    rename_canonical_files()
