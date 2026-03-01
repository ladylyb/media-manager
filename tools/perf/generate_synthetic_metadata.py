"""Synthetic dataset generator for Phase 6 metadata performance testing."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Iterable


def _synthetic_hash(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def build_synthetic_rows(count: int) -> list[tuple[str, dict[str, str]]]:
    rows: list[tuple[str, dict[str, str]]] = []
    for idx in range(count):
        digest = _synthetic_hash(f"media-{idx:09d}")
        rows.append(
            (
                digest,
                {
                    "OWNER": "LL",
                    "CONTEXT": "General",
                    "TAKEN_DT": f"2024-01-{(idx % 28) + 1:02d}T12:00:00+00:00",
                    "FS_CTIME": "2024-01-01T00:00:00+00:00",
                    "FS_MTIME": "2024-01-01T00:00:00+00:00",
                    "CAMERA_MODEL": f"CAM-{idx % 5}",
                },
            )
        )
    return rows


def write_tsv(rows: Iterable[tuple[str, dict[str, str]]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        handle.write("file_hash\tcode_type\tdecode_value\n")
        for file_hash, metadata in rows:
            for code_type, decode_value in metadata.items():
                handle.write(f"{file_hash}\t{code_type}\t{decode_value}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic metadata rows for perf harnesses.")
    parser.add_argument("--count", type=int, default=10_000, help="Number of synthetic files.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/perf/synthetic_metadata.tsv"),
        help="TSV output path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = build_synthetic_rows(args.count)
    write_tsv(rows, args.output)
    print(f"Generated {len(rows)} synthetic file records at {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

