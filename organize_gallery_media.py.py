#!/usr/bin/env python3

import argparse
import csv
import logging
import os
import sqlite3
from pathlib import Path

# -------------------------
# Configuration
# -------------------------

IMAGE_EXTENSIONS = {
    "jpg", "jpeg", "png", "webp", "heic", "heif", "tiff", "bmp"
}

VIDEO_EXTENSIONS = {
    "mp4", "mov", "mkv", "avi", "wmv", "flv", "webm", "mpeg", "mpg"
}

# -------------------------
# Helpers
# -------------------------

def setup_logging(log_file: str | None):
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=handlers,
    )


def write_csv_row(csv_path: Path, header: list[str], row: list[str]):
    write_header = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(header)
        writer.writerow(row)


def infer_media_type_from_extension(ext: str) -> str:
    ext = ext.lower()
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


# -------------------------
# Core logic
# -------------------------

def sanity_check_and_move_gallery(
    db_path: Path,
    gallery_root: Path,
    dry_run: bool,
    csv_path: Path | None,
):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT
            f.id AS file_id,
            f.filename,
            f.extension,
            f.media_type AS db_media_type,
            fa.target_path
        FROM file_actions fa
        JOIN files f ON f.id = fa.file_id
        WHERE fa.action = 'move'
          AND fa.target_path LIKE ?
        ORDER BY fa.decided_at ASC
    """, (str(gallery_root) + "%",))

    rows = cur.fetchall()

    logging.info("Gallery candidates found: %d", len(rows))

    for row in rows:
        file_id = row["file_id"]
        filename = row["filename"]
        extension = row["extension"] or Path(filename).suffix
        db_media_type = row["db_media_type"]
        source_path = Path(row["target_path"])

        inferred_type = infer_media_type_from_extension(extension)

        status = "OK" if db_media_type == inferred_type else "MISMATCH"

        if not source_path.exists():
            status = "MISSING"
            logging.warning(
                "MISSING | id=%s | %s",
                file_id,
                source_path,
            )
        else:
            logging.info(
                "%s | id=%s | db=%s | inferred=%s | %s",
                status,
                file_id,
                db_media_type,
                inferred_type,
                source_path.name,
            )

        if csv_path:
            write_csv_row(
                csv_path,
                header=[
                    "file_id",
                    "filename",
                    "db_media_type",
                    "inferred_media_type",
                    "status",
                    "source_path",
                    "target_path",
                    "mode",
                ],
                row=[
                    file_id,
                    filename,
                    db_media_type,
                    inferred_type,
                    status,
                    str(source_path),
                    "",
                    "dry-run" if dry_run else "apply",
                ],
            )

        # ---- Move logic (only if file exists) ----
        if not source_path.exists():
            continue

        if inferred_type == "image":
            target_root = gallery_root / "Images"
        elif inferred_type == "video":
            target_root = gallery_root / "Movies"
        else:
            logging.warning(
                "SKIP unknown media type | id=%s | %s",
                file_id,
                source_path.name,
            )
            continue

        target_root.mkdir(parents=True, exist_ok=True)
        target_path = ensure_unique_path(target_root / source_path.name)

        if dry_run:
            logging.info(
                "DRY-RUN move | %s → %s",
                source_path,
                target_path,
            )
        else:
            try:
                source_path.rename(target_path)
                logging.info(
                    "MOVED | %s → %s",
                    source_path,
                    target_path,
                )
            except Exception as e:
                logging.error(
                    "FAILED MOVE | id=%s | %s",
                    file_id,
                    e,
                )

        if csv_path:
            write_csv_row(
                csv_path,
                header=[
                    "file_id",
                    "filename",
                    "db_media_type",
                    "inferred_media_type",
                    "status",
                    "source_path",
                    "target_path",
                    "mode",
                ],
                row=[
                    file_id,
                    filename,
                    db_media_type,
                    inferred_type,
                    status,
                    str(source_path),
                    str(target_path),
                    "dry-run" if dry_run else "apply",
                ],
            )

    conn.close()

    logging.info("=" * 70)
    logging.info("Gallery sanity check complete")


# -------------------------
# Entry point
# -------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Gallery sanity check and canonical move (Images / Movies)"
    )
    parser.add_argument("db_path", type=Path, help="SQLite database path")
    parser.add_argument("gallery_root", type=Path, help="Gallery root folder")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--log", type=str)
    parser.add_argument("--csv", type=Path)

    args = parser.parse_args()
    setup_logging(args.log)

    if not args.db_path.exists():
        logging.error("Database not found: %s", args.db_path)
        return

    if not args.gallery_root.exists():
        logging.error("Gallery root not found: %s", args.gallery_root)
        return

    logging.info("=" * 70)
    logging.info("Starting gallery sanity check")
    logging.info("DB: %s", args.db_path)
    logging.info("Gallery: %s", args.gallery_root)
    logging.info("Mode: %s", "APPLY" if args.apply else "DRY-RUN")

    sanity_check_and_move_gallery(
        db_path=args.db_path,
        gallery_root=args.gallery_root,
        dry_run=not args.apply,
        csv_path=args.csv,
    )


if __name__ == "__main__":
    main()
