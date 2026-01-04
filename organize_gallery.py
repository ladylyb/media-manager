# -------------------- organize_gallery.py --------------------
from pathlib import Path
import sqlite3
import shutil
from datetime import datetime

# -------------------- CONFIG --------------------
ARCHIVE_ROOT = Path(r"C:\Users\micro\Documents\Better Up\Media-Manager")
GALLERY_ROOT = ARCHIVE_ROOT / "gallery"
DUPLICATES_ROOT = ARCHIVE_ROOT / "duplicates"

DB_PATH = Path("media-manager.db")
CANONICAL_PREFIX = "ladylyb - Personal Chapters —"

# -------------------- HELPERS --------------------
def parse_timestamp_from_filename(filename: str) -> str:
    """
    Extract YYYY-MM-DD_HHMMSS from canonical filename.
    Returns "0000-00-00_000000" if invalid or in future.
    """
    try:
        base = Path(filename).stem
        ts_part = base.replace(CANONICAL_PREFIX, "")
        ts = datetime.strptime(ts_part, "%Y-%m-%d_%H%M%S")
        if ts > datetime.now():
            return "0000-00-00_000000"
        return ts.strftime("%Y-%m-%d_%H%M%S")
    except Exception:
        return "0000-00-00_000000"


def move_file(src_path: Path, target_root: Path, timestamp_str: str) -> Path:
    """
    Move file to YYYY/MM/DD (gallery) or YYYY-MM-DD (duplicates) folder.
    Avoid overwrite by adding numeric suffix if needed.
    """
    # Determine folder
    if target_root.name == "gallery":
        year, month, day = timestamp_str[:4], timestamp_str[5:7], timestamp_str[8:10]
        folder = target_root / year / month / day
    else:  # duplicates
        folder = target_root / timestamp_str[:10]

    folder.mkdir(parents=True, exist_ok=True)
    target_path = folder / src_path.name

    # Avoid overwriting
    if target_path.exists():
        suffix = 1
        stem = target_path.stem
        while (folder / f"{stem}_{suffix}{target_path.suffix}").exists():
            suffix += 1
        target_path = folder / f"{stem}_{suffix}{target_path.suffix}"

    shutil.move(str(src_path), str(target_path))
    return target_path


def cleanup_empty_folders(path: Path):
    """Recursively remove empty folders up to ARCHIVE_ROOT"""
    current = path
    while current != ARCHIVE_ROOT and current.exists() and current.is_dir():
        if any(current.iterdir()):
            break
        current.rmdir()
        current = current.parent


# -------------------- MAIN --------------------
def organize_gallery():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("Organizing canonical files into gallery...")

    # Canonical files (already renamed)
    cur.execute("""
        SELECT f.id, f.path, f.filename
        FROM files f
        JOIN file_actions fa ON f.id = fa.file_id
        WHERE fa.action = 'rename'
    """)
    canonical_files = cur.fetchall()

    for row in canonical_files:
        file_id = row["id"]
        src_path = Path(row["path"])
        timestamp_str = parse_timestamp_from_filename(row["filename"])

        if not src_path.exists():
            print(f"⚠ Source missing: {src_path}")
            continue

        target_path = move_file(src_path, GALLERY_ROOT, timestamp_str)

        cur.execute("""
            INSERT INTO file_actions (file_id, action, target_path, notes)
            VALUES (?, 'move_gallery', ?, ?)
        """, (file_id, str(target_path), f"Moved to gallery/{timestamp_str}"))

        cleanup_empty_folders(src_path.parent)
        conn.commit()
        print(f"{src_path.name} → {target_path}")

    # Duplicates
    print("Organizing duplicates into dated folders...")
    for dup_file in DUPLICATES_ROOT.iterdir():
        if dup_file.is_file():
            timestamp_str = parse_timestamp_from_filename(dup_file.name)
            target_path = move_file(dup_file, DUPLICATES_ROOT, timestamp_str)
            print(f"Duplicate {dup_file.name} → {target_path}")

    conn.close()
    print("Gallery organization complete.")


if __name__ == "__main__":
    organize_gallery()
