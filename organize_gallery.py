from pathlib import Path
import sqlite3
import shutil
from datetime import datetime, date

# -------------------- CONFIG --------------------
ARCHIVE_ROOT = Path(r"C:\Users\micro\Documents\Better Up\Media-Manager")
GALLERY_ROOT = ARCHIVE_ROOT / "gallery"
DB_PATH = Path("media-manager.db")

PROTECTED_DIRS = {
    GALLERY_ROOT.resolve(),
    (ARCHIVE_ROOT / "duplicates").resolve(),
}

# -------------------- HELPERS --------------------
def safe_parse_date(timestamp_str: str | None) -> tuple[str, str, str]:
    """
    Returns (YYYY, MM, DD) or ('0000','00','00') if invalid or future
    """
    if not timestamp_str:
        return "0000", "00", "00"

    try:
        dt = datetime.strptime(timestamp_str, "%Y-%m-%d_%H%M%S")
        if dt.date() > date.today():
            return "0000", "00", "00"
        return f"{dt.year:04}", f"{dt.month:02}", f"{dt.day:02}"
    except Exception:
        return "0000", "00", "00"


def cleanup_empty_dirs(start_path: Path):
    """
    Walk upward deleting empty directories until hitting protected root
    """
    current = start_path

    while True:
        if not current.exists() or not current.is_dir():
            break

        if current.resolve() in PROTECTED_DIRS:
            break

        try:
            if any(current.iterdir()):
                break
            current.rmdir()
            current = current.parent
        except Exception:
            break


# -------------------- MAIN --------------------
def organize_gallery():
    print("Starting gallery organization...")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT
            f.id AS file_id,
            fa.target_path AS current_path,
            f.exif_datetime,
            f.mtime
        FROM files f
        JOIN file_actions fa ON f.id = fa.file_id
        WHERE fa.action = 'rename'
    """)

    rows = cur.fetchall()
    print(f"Found {len(rows)} canonical files to organize.")

    for idx, row in enumerate(rows, 1):
        file_id = row["file_id"]
        src_path = Path(row["current_path"])

        if not src_path.exists():
            print(f"[{idx}] Missing file, skipping: {src_path}")
            continue

        # Determine date folder
        timestamp = row["exif_datetime"]
        if not timestamp and row["mtime"]:
            try:
                timestamp = datetime.fromtimestamp(float(row["mtime"])).strftime("%Y-%m-%d_%H%M%S")
            except Exception:
                timestamp = None

        yyyy, mm, dd = safe_parse_date(timestamp)

        target_dir = GALLERY_ROOT / yyyy / mm / dd
        target_dir.mkdir(parents=True, exist_ok=True)

        target_path = target_dir / src_path.name

        # Avoid overwrite
        if target_path.exists():
            suffix = 1
            stem = target_path.stem
            while (target_dir / f"{stem}_{suffix}{target_path.suffix}").exists():
                suffix += 1
            target_path = target_dir / f"{stem}_{suffix}{target_path.suffix}"

        print(f"[{idx}/{len(rows)}] Moving → {target_path}")

        try:
            shutil.move(str(src_path), str(target_path))
        except Exception as e:
            print(f"  ❌ Move failed: {e}")
            continue

        # Log move
        cur.execute("""
            INSERT INTO file_actions (file_id, action, target_path, notes)
            VALUES (?, 'move_gallery', ?, ?)
        """, (file_id, str(target_path), "Moved canonical file into gallery structure"))

        conn.commit()

        # Cleanup old folders
        cleanup_empty_dirs(src_path.parent)

    conn.close()
    print("Gallery organization complete.")


if __name__ == "__main__":
    organize_gallery()
