#!/usr/bin/env python3

import argparse
import logging
import os
import sqlite3
from pathlib import Path

IMAGE_EXTENSIONS = {
    "jpg", "jpeg", "png", "webp", "heic", "heif", "tiff", "bmp"
}

VIDEO_EXTENSIONS = {
    "mp4", "mov", "mkv", "avi", "wmv", "flv", "webm", "mpeg", "mpg"
}

# -------------------------
# Logging
# -------------------------

def setup_logging(log_file: Path | None):
    handlers = [logging.StreamHandler()]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.FileHandler(log_file, encoding="utf-8")
        )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=handlers,
    )


# -------------------------
# Helpers
# -------------------------

def infer_media_type(ext: str) -> str:
    ext = ext.lower().lstrip(".")
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    return "unknown"


def ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    counter = 1
    while True:
        candidate = path.with_stem(f"{path.stem}_{counter}")
        if not candidate.exists():
            return candidate
        counter += 1


def cleanup_empty_parents(start: Path, stop_at: Path):
    current = start
    while current != stop_at and current.exists():
        try:
            if any(current.iterdir()):
                break
            current.rmdir()
            current = current.parent
        except Exception:
            break


# -------------------------
# Core logic
# -------------------------

def organize_gallery(
    db_path: Path,
    gallery_root: Path,
    dry_run: bool,
    limit: int | None,
    cleanup_empty_dirs: bool,
):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT
            fa.id            AS action_id,
            fa.file_id,
            fa.target_path,
            f.filename,
            f.extension,
            f.media_type AS db_media_type
        FROM file_actions fa
        JOIN files f ON f.id = fa.file_id
        WHERE fa.action = 'move'
          AND fa.target_path LIKE ?
        ORDER BY fa.decided_at ASC
    """, (str(gallery_root) + "%",))

    rows = cur.fetchall()
    if limit:
        rows = rows[:limit]
        dry_run = True

    logging.info("Candidates: %d", len(rows))
    logging.info("Mode: %s", "DRY-RUN" if dry_run else "APPLY")

    for row in rows:
        source_path = Path(row["target_path"])
        ext = row["extension"] or source_path.suffix
        inferred = infer_media_type(ext)

        if inferred not in {"image", "video"}:
            logging.warning(
                "SKIP unknown | id=%s | %s",
                row["file_id"],
                source_path.name,
            )
            continue

        if not source_path.exists():
            logging.warning(
                "MISSING | id=%s | %s",
                row["file_id"],
                source_path,
            )
            continue

        rel = source_path.relative_to(gallery_root)
        date_parts = rel.parts[:3]  # YYYY/MM/DD

        target_root = gallery_root / ("Images" if inferred == "image" else "Movies")
        target_path = ensure_unique_path(
            target_root.joinpath(*date_parts, source_path.name)
        )

        logging.info(
            "%s | %s → %s",
            "DRY-RUN" if dry_run else "MOVE",
            source_path,
            target_path,
        )

        if dry_run:
            continue

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.rename(target_path)

            cur.execute("""
                INSERT INTO file_actions (
                    file_id,
                    action,
                    target_path,
                    notes,
                    decided_at
                ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                row["file_id"],
                "organize",
                str(target_path),
                f"Moved to {'Images' if inferred == 'image' else 'Movies'} folder; Move {str(source_path)} → {str(target_path)}"
            ))

            if cleanup_empty_dirs:
                cleanup_empty_parents(source_path.parent, gallery_root)

        except Exception as e:
            logging.error(
                "FAILED | id=%s | %s",
                row["file_id"],
                e,
            )

    if not dry_run:
        conn.commit()

    conn.close()
    logging.info("Gallery organization complete")


# -------------------------
# Entry point
# -------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Organize gallery into Images/ and Movies/ preserving date structure"
    )

    # Required named arguments
    parser.add_argument(
        "--db",
        required=True,
        type=Path,
        help="SQLite database path",
    )
    parser.add_argument(
        "--gallery",
        required=True,
        type=Path,
        help="Gallery root folder",
    )

    # Optional flags
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of files processed (forces DRY-RUN)",
    )
    parser.add_argument(
        "--cleanup-empty-dirs",
        action="store_true",
        help="Remove empty directories after moves",
    )
    parser.add_argument("--log", type=Path)

    args = parser.parse_args()

    # ---- Safety rule ----
    dry_run = not args.apply or args.limit is not None

    setup_logging(args.log)

    if not args.db.exists():
        logging.error("Database not found: %s", args.db)
        return

    if not args.gallery.exists():
        logging.error("Gallery root not found: %s", args.gallery)
        return

    logging.info("=" * 70)
    logging.info("Starting gallery organization")
    logging.info("DB: %s", args.db)
    logging.info("Gallery: %s", args.gallery)
    logging.info("Mode: %s", "APPLY" if not dry_run else "DRY-RUN")
    if args.limit:
        logging.info("Limit: %d (dry-run enforced)", args.limit)

    organize_gallery(
        db_path=args.db,
        gallery_root=args.gallery,
        dry_run=dry_run,
        limit=args.limit,
        cleanup_empty_dirs=args.cleanup_empty_dirs,
    )

if __name__ == "__main__":
    main()
