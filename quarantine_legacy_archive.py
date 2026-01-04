from pathlib import Path
import shutil
import logging
from datetime import datetime

# -------------------- CONFIG --------------------
SOURCE_ROOT = Path(r"C:\Users\micro\Documents\Better Up\Archive\OWN")
ARCHIVE_ROOT = Path(r"C:\Users\micro\Documents\Better Up\Media-Manager")
QUARANTINE_ROOT = ARCHIVE_ROOT / "to-be-deleted"

DRY_RUN = True  # ← SET TO False TO EXECUTE
MAX_FILENAME_LEN = 240  # conservative for Windows safety
DELIMITER = "__"

# -------------------- LOGGING --------------------
log_file = ARCHIVE_ROOT / f"to_be_deleted_cleanup_{datetime.now():%Y%m%d_%H%M%S}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# -------------------- HELPERS --------------------
def sanitize(text: str) -> str:
    illegal = '<>:"/\\|?*'
    for ch in illegal:
        text = text.replace(ch, "_")
    return "_".join(filter(None, text.split()))

def build_flat_filename(src: Path) -> str:
    relative_parts = src.relative_to(SOURCE_ROOT).parts
    parts = [sanitize(p) for p in relative_parts]

    filename = DELIMITER.join(parts)

    stem = Path(filename).stem
    suffix = src.suffix

    # Trim parent folders first if too long
    while len(filename) > MAX_FILENAME_LEN and DELIMITER in stem:
        stem = DELIMITER.join(stem.split(DELIMITER)[1:])
        filename = f"{stem}{suffix}"

    # Last resort: truncate stem
    if len(filename) > MAX_FILENAME_LEN:
        excess = len(filename) - MAX_FILENAME_LEN
        stem = stem[:-excess]
        filename = f"{stem}{suffix}"

    return filename

def resolve_collision(target: Path) -> Path:
    counter = 1
    base = target.stem
    suffix = target.suffix
    while target.exists():
        target = target.with_name(f"{base}_{counter}{suffix}")
        counter += 1
    return target

# -------------------- MAIN --------------------
def quarantine_files():
    logging.info("Starting quarantine cleanup")
    logging.info(f"DRY RUN MODE: {DRY_RUN}")

    QUARANTINE_ROOT.mkdir(parents=True, exist_ok=True)

    files_moved = 0
    folders_deleted = 0
    truncations = 0
    collisions = 0

    # ---- MOVE FILES ----
    for src in SOURCE_ROOT.rglob("*"):
        if not src.is_file():
            continue

        try:
            flat_name = build_flat_filename(src)
            if len(flat_name) < len(src.name):
                truncations += 1

            target = QUARANTINE_ROOT / flat_name
            if target.exists():
                collisions += 1
                target = resolve_collision(target)

            logging.info(f"[FILE] {src} → {target}")

            if not DRY_RUN:
                shutil.move(str(src), str(target))

            files_moved += 1

        except Exception as e:
            logging.error(f"[ERROR] Failed to process {src}: {e}")

    # ---- DELETE EMPTY FOLDERS ----
    for folder in sorted(SOURCE_ROOT.rglob("*"), reverse=True):
        if folder.is_dir():
            try:
                if not any(folder.iterdir()):
                    logging.info(f"[DIR] Removing empty folder: {folder}")
                    if not DRY_RUN:
                        folder.rmdir()
                    folders_deleted += 1
            except Exception as e:
                logging.error(f"[ERROR] Failed to remove folder {folder}: {e}")

    # ---- SUMMARY ----
    logging.info("------ SUMMARY ------")
    logging.info(f"Files moved           : {files_moved}")
    logging.info(f"Folders deleted       : {folders_deleted}")
    logging.info(f"Filename truncations  : {truncations}")
    logging.info(f"Filename collisions   : {collisions}")
    logging.info("Cleanup complete")

# -------------------- ENTRY --------------------
if __name__ == "__main__":
    quarantine_files()
