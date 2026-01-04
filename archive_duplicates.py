# archive_duplicates.py — Step 3 Enhanced Version
from pathlib import Path
import sqlite3
import shutil
from datetime import datetime

# -------------------- CONFIG --------------------
ARCHIVE_ROOT = Path(r"C:\Users\micro\Documents\Better Up\Media-Manager")  # top-level archive folder
ARCHIVE_SUBFOLDER = ARCHIVE_ROOT / "duplicates"

DB_PATH = Path("media-manager.db")

# -------------------- FUNCTIONS --------------------
def get_duplicates(conn):
    """Fetch all duplicates that have not been moved yet."""
    cur = conn.cursor()
    cur.execute("""
        SELECT dc.id AS dc_id, dc.file_id_1, dc.file_id_2, dc.match_type,
               f1.path AS path1, f2.path AS path2, f1.filename AS fname1, f2.filename AS fname2
        FROM duplicate_candidates dc
        JOIN files f1 ON dc.file_id_1 = f1.id
        JOIN files f2 ON dc.file_id_2 = f2.id
        LEFT JOIN file_actions fa1 ON fa1.file_id = f2.id AND fa1.action = 'move'
        WHERE dc.match_type IN ('exact_hash','probable_metadata')
          AND fa1.id IS NULL
    """)
    return cur.fetchall()


def archive_file(conn, file_id, src_path: Path, canonical_name: str):
    """Move a duplicate file to archive and log in file_actions."""
    if not src_path.exists():
        print(f"[SKIP] File not found: {src_path}")
        return False

    # Determine folder by original file's year-month (fallback to 0000-00)
    try:
        mtime = datetime.fromtimestamp(src_path.stat().st_mtime)
        folder_name = mtime.strftime("%Y-%m")
    except Exception:
        folder_name = "0000-00"

    archive_folder = ARCHIVE_SUBFOLDER / folder_name
    archive_folder.mkdir(parents=True, exist_ok=True)

    target_path = archive_folder / src_path.name

    # Avoid overwriting
    if target_path.exists():
        suffix = 1
        stem = target_path.stem
        while True:
            suffix_path = archive_folder / f"{stem}_{suffix}{target_path.suffix}"
            if not suffix_path.exists():
                target_path = suffix_path
                break
            suffix += 1

    # Move file
    shutil.move(str(src_path), str(target_path))

    # Log action
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO file_actions (file_id, action, target_path, notes)
        VALUES (?, 'move', ?, ?)
    """, (file_id, str(target_path), f"Archived as duplicate of {canonical_name}"))
    conn.commit()

    print(f"[ARCHIVE] {src_path} → {target_path}")
    return True


def archive_duplicates():
    print("Starting duplicate archiving process...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    duplicates = get_duplicates(conn)
    print(f"Found {len(duplicates)} duplicates to process")

    moved_count = 0
    skipped_count = 0

    for dup in duplicates:
        # Choose one of the two files to move (file_id_2 is treated as duplicate)
        canonical_name = dup["fname1"]
        src_path = Path(dup["path2"])
        file_id = dup["file_id_2"]

        success = archive_file(conn, file_id, src_path, canonical_name)
        if success:
            moved_count += 1
        else:
            skipped_count += 1

    conn.close()
    print("Duplicate archiving complete")
    print(f"Total duplicates found: {len(duplicates)}")
    print(f"Files moved: {moved_count}")
    print(f"Files skipped: {skipped_count}")


# -------------------- MAIN --------------------
if __name__ == "__main__":
    archive_duplicates()
