from pathlib import Path
import sqlite3
import shutil
from canonical_mapping import main as get_canonical_mapping
from typing import Dict, List

# -------------------- CONFIG --------------------
ARCHIVE_ROOT = Path(r"C:\Users\micro\Documents\Better Up\Media-Manager")  # Top-level archive folder

# -------------------- FUNCTIONS --------------------
def archive_duplicates(mapping: Dict[int, List[int]]):
    conn = sqlite3.connect("media-manager.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    for canonical_id, duplicate_ids in mapping.items():
        # Fetch canonical file info
        cur.execute("SELECT filename FROM files WHERE id = ?", (canonical_id,))
        canonical = cur.fetchone()
        canonical_name = canonical["filename"] if canonical else str(canonical_id)

        for dup_id in duplicate_ids:
            # Skip if already archived
            cur.execute("""
                SELECT 1 FROM file_actions
                WHERE file_id = ? AND action = 'move'
            """, (dup_id,))
            if cur.fetchone():
                continue

            # Fetch duplicate file info
            cur.execute("SELECT path, filename FROM files WHERE id = ?", (dup_id,))
            dup = cur.fetchone()
            if not dup:
                continue

            src_path = Path(dup["path"])
            if not src_path.exists():
                continue

            # Determine archive folder
            archive_folder = ARCHIVE_ROOT / "duplicates"
            archive_folder.mkdir(parents=True, exist_ok=True)
            target_path = archive_folder / dup["filename"]

            # Avoid overwriting by adding numeric suffix
            if target_path.exists():
                suffix = 1
                stem = target_path.stem
                suffix_path = archive_folder / f"{stem}_{suffix}{target_path.suffix}"
                while suffix_path.exists():
                    suffix += 1
                    suffix_path = archive_folder / f"{stem}_{suffix}{target_path.suffix}"
                target_path = suffix_path

            # Move file
            shutil.move(str(src_path), str(target_path))

            # Log action in file_actions
            cur.execute("""
                INSERT INTO file_actions (file_id, action, target_path, notes)
                VALUES (?, 'move', ?, ?)
            """, (dup_id, str(target_path), f"Archived as duplicate of {canonical_name}"))

        conn.commit()
        print(f"Canonical {canonical_name} → archived {len(duplicate_ids)} duplicates")

    conn.close()
    print("Archiving complete")

# -------------------- MAIN --------------------
if __name__ == "__main__":
    mapping = get_canonical_mapping()
    archive_duplicates(mapping)
