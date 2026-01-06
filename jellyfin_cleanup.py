#!/usr/bin/env python3

import argparse
import csv
import logging
import os
import shutil
import stat
from pathlib import Path

# -------------------------
# Configuration
# -------------------------

TRICKPLAY_SUFFIX = ".trickplay"

ARTWORK_TOKENS = {
    "poster",
    "folder",
    "thumb",
    "landscape",
    "backdrop",
    "banner",
}

ARTWORK_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp",
}

# Never delete files containing these tokens
WHITELIST_TOKENS = {
    "fanart",
}

# -------------------------
# Helpers
# -------------------------

def make_writable(path: str):
    try:
        os.chmod(path, stat.S_IWRITE)
    except Exception:
        pass


def tokenize_stem(stem: str) -> list[str]:
    return stem.lower().replace("_", "-").split("-")


def setup_logging(log_file: str | None):
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(
            logging.FileHandler(
                log_file,
                mode="a",
                encoding="utf-8",
            )
        )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=handlers,
    )


def write_csv_row(csv_path: Path, row: list[str]):
    write_header = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(
                ["full_path", "filename", "trigger_token", "mode"]
            )
        writer.writerow(row)

# -------------------------
# Core logic
# -------------------------

def cleanup_media(
    root: Path,
    dry_run: bool,
    artwork_only: bool,
    csv_path: Path | None,
):
    trickplay_dirs = 0
    artwork_files = 0
    failures = 0

    for current_root, dirs, files in os.walk(root, topdown=True):

        # ---- TRICKPLAY DIRECTORIES ----
        if not artwork_only:
            for d in list(dirs):
                if d.lower().endswith(TRICKPLAY_SUFFIX):
                    full_path = Path(current_root) / d
                    trickplay_dirs += 1

                    logging.info(
                        "%s trickplay directory: %s",
                        "DRY-RUN would delete" if dry_run else "Deleting",
                        full_path,
                    )

                    if not dry_run:
                        shutil.rmtree(
                            full_path,
                            onerror=lambda func, p, exc: (
                                make_writable(p),
                                func(p),
                            ),
                        )

                    # Prevent descent
                    dirs.remove(d)

        # ---- ARTWORK FILES ----
        for f in files:
            path = Path(current_root) / f
            try:
                if path.suffix.lower() not in ARTWORK_EXTENSIONS:
                    continue

                tokens = tokenize_stem(path.stem)

                # Skip whitelisted tokens
                if any(t in WHITELIST_TOKENS for t in tokens):
                    continue

                trigger = next(
                    (t for t in tokens if t in ARTWORK_TOKENS),
                    None,
                )

                if not trigger:
                    continue

                artwork_files += 1

                logging.info(
                    "%s artwork file: %s (token: %s)",
                    "DRY-RUN would delete" if dry_run else "Deleting",
                    path,
                    trigger,
                )

                if csv_path:
                    write_csv_row(
                        csv_path,
                        [
                            str(path),
                            path.name,
                            trigger,
                            "dry-run" if dry_run else "apply",
                        ],
                    )

                if not dry_run:
                    make_writable(path)
                    path.unlink()

            except Exception as e:
                failures += 1
                logging.error("Failed processing %s: %s", path, e)

    logging.info("=" * 70)
    logging.info("Cleanup complete")
    logging.info("Trickplay directories removed: %d", trickplay_dirs)
    logging.info("Artwork files removed: %d", artwork_files)
    logging.info("Failures: %d", failures)

# -------------------------
# Entry point
# -------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Windows-safe Jellyfin cleanup with audit logging."
    )
    parser.add_argument("media_root", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--artwork-only",
        action="store_true",
        help="Only delete artwork files, skip trickplay folders",
    )
    parser.add_argument("--log", type=str)
    parser.add_argument(
        "--csv",
        type=Path,
        help="Optional CSV audit file for deleted artwork",
    )

    args = parser.parse_args()
    setup_logging(args.log)

    if not args.media_root.exists():
        logging.error("Path does not exist: %s", args.media_root)
        return

    logging.info("=" * 70)
    logging.info("Starting Jellyfin cleanup")
    logging.info("Root: %s", args.media_root.resolve())
    logging.info("Mode: %s", "APPLY" if args.apply else "DRY-RUN")
    logging.info(
        "Scope: %s",
        "ARTWORK ONLY" if args.artwork_only else "TRICKPLAY + ARTWORK",
    )

    cleanup_media(
        root=args.media_root,
        dry_run=not args.apply,
        artwork_only=args.artwork_only,
        csv_path=args.csv,
    )

if __name__ == "__main__":
    main()
