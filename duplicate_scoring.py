from pathlib import Path
import sqlite3
from itertools import combinations
from typing import Optional, List, Tuple

DB_PATH = Path("media-manager.db")
CONFIDENCE_THRESHOLD = 70

# -------------------- SCORING FUNCTION --------------------
def score_pair(f1: dict, f2: dict) -> int:
    score = 0

    # Same size (already grouped, but explicit)
    if f1["size_bytes"] == f2["size_bytes"]:
        score += 30

    # Duration within 1 second
    if (
        f1["duration"] is not None
        and f2["duration"] is not None
        and abs(f1["duration"] - f2["duration"]) <= 1.0
    ):
        score += 30

    # Same resolution
    if (
        f1["width"] is not None
        and f1["width"] == f2["width"]
        and f1["height"] == f2["height"]
    ):
        score += 20

    # Same codec
    if f1["codec"] and f1["codec"] == f2["codec"]:
        score += 10

    # Same EXIF datetime (images)
    if (
        f1["exif_datetime"]
        and f1["exif_datetime"] == f2["exif_datetime"]
    ):
        score += 10

    return score

# -------------------- MAIN DRIVER --------------------
def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Step 1: get candidate size groups
    cur.execute("""
        SELECT size_bytes, media_type
        FROM files
        WHERE media_type IN ('image','video')
          AND hash_full IS NULL
        GROUP BY size_bytes, media_type
        HAVING COUNT(*) > 1
    """)
    size_groups = cur.fetchall()
    print(f"Found {len(size_groups)} size groups to process")

    for idx, group in enumerate(size_groups, start=1):
        size_bytes = group["size_bytes"]
        media_type = group["media_type"]

        # Step 2: load files in this group
        cur.execute("""
            SELECT
                id, size_bytes, duration,
                width, height, codec, exif_datetime
            FROM files
            WHERE size_bytes = ?
              AND media_type = ?
              AND hash_full IS NULL
        """, (size_bytes, media_type))
        files = [dict(row) for row in cur.fetchall()]

        if len(files) < 2:
            continue

        inserts: List[Tuple[int, int, str, int, str]] = []

        # Step 3: pairwise comparison
        for f1, f2 in combinations(files, 2):
            score = score_pair(f1, f2)
            if score >= CONFIDENCE_THRESHOLD:
                inserts.append((
                    f1["id"],
                    f2["id"],
                    "probable_metadata",
                    score,
                    "Metadata similarity (size/duration/resolution/codec/exif)"
                ))

        # Step 4: persist results
        if inserts:
            cur.executemany("""
                INSERT OR IGNORE INTO duplicate_candidates (
                    file_id_1,
                    file_id_2,
                    match_type,
                    confidence_score,
                    reason
                ) VALUES (?, ?, ?, ?, ?)
            """, inserts)
            conn.commit()

        print(f"[{idx}/{len(size_groups)}] size={size_bytes} → {len(inserts)} matches")

    conn.close()
    print("Probable duplicate scoring complete")

if __name__ == "__main__":
    main()
