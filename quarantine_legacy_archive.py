import argparse
import shutil
from pathlib import Path
from datetime import datetime
import logging

# -------------------- CONFIG --------------------
ARCHIVE_ROOT = Path(r"C:\Users\micro\Documents\Better Up\Media-Manager")
QUARANTINE_FOLDER = ARCHIVE_ROOT / "to-be-deleted"
LOG_FILE = ARCHIVE_ROOT / f"cleanup_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

MAX_FILENAME_LENGTH = 200  # truncate long names

# -------------------- SETUP LOGGING --------------------
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# -------------------- HELPERS --------------------
def safe_flat_name(file_path: Path):
    """Generate a flat filename including the original path."""
    parts = file_path.parts[-5:]  # keep last 5 parts to avoid too long names
    flat_name = "_".join(parts)
    flat_name = flat_name.replace(":", "-").replace(" ", "_")
    if len(flat_name) > MAX_FILENAME_LENGTH:
        flat_name = flat_name[:MAX_FILENAME_LENGTH]
    return flat_name

def confirm(prompt="Proceed? [y/N]: "):
    resp = input(prompt).strip().lower()
    return resp == "y"

# -------------------- MAIN --------------------
def archive_and_cleanup(source_root: Path, dry_run=True, limit=None):
    source_root = source_root.resolve()
    QUARANTINE_FOLDER.mkdir(parents=True, exist_ok=True)

    files_moved = 0
    folders_deleted = 0
    all_files = list(source_root.rglob("*.*"))

    if limit:
        all_files = all_files[:limit]

    logging.info(f"Starting archive cleanup from {source_root}, dry_run={dry_run}, limit={limit}")
    print(f"Found {len(all_files)} files to process.")

    for idx, file_path in enumerate(all_files, 1):
        if not file_path.is_file():
            continue
        flat_name = safe_flat_name(file_path)
        target_path = QUARANTINE_FOLDER / flat_name
        print(f"[{idx}/{len(all_files)}] {file_path} → {target_path}")
        logging.info(f"Processing {file_path} → {target_path}")

        if not dry_run:
            # Avoid overwriting
            suffix = 1
            base_target = target_path
            while target_path.exists():
                target_path = base_target.with_name(f"{base_target.stem}_{suffix}{base_target.suffix}")
                suffix += 1
            shutil.move(str(file_path), str(target_path))
        files_moved += 1

    # Delete empty folders
    for folder in sorted([f for f in source_root.rglob("*") if f.is_dir()], key=lambda p: -len(p.parts)):
        if not any(folder.iterdir()):
            print(f"Deleting empty folder: {folder}")
            logging.info(f"Deleting empty folder: {folder}")
            if not dry_run:
                folder.rmdir()
            folders_deleted += 1

    # Summary footer
    print(f"\n=== Summary ===")
    print(f"Files moved: {files_moved}")
    print(f"Folders deleted: {folders_deleted}")
    logging.info(f"Cleanup complete: files_moved={files_moved}, folders_deleted={folders_deleted}")

# -------------------- ENTRY POINT --------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Archive legacy files and clean empty folders safely.")
    parser.add_argument("--source", type=Path, required=True, help="Root folder to clean")
    parser.add_argument("--dry-run", action="store_true", help="Do not move or delete, just log actions")
    parser.add_argument("--limit", type=int, help="Process only first N files")
    args = parser.parse_args()

    print(f"Dry run: {args.dry_run}")
    if not args.dry_run and not confirm("Proceed with moving files and deleting folders? [y/N]: "):
        print("Aborted by user.")
        exit(0)

    archive_and_cleanup(args.source, dry_run=args.dry_run, limit=args.limit)
