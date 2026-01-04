from pathlib import Path
import sqlite3
from itertools import combinations
from typing import List, Tuple, Dict, Optional

DB_PATH = Path("media-manager.db")
CONFIDENCE_THRESHOLD = 50

# -------------------- TYPE ALIAS --------------------
FileDict = Dict[str, Optional[int | float | str]]  # generic file dict from DB

# -------------------- HELPERS --------------------
def to_float(x: Optional[int | float | str]) -> Optional[float]:
    """Convert a value to float if possible, else return None"""
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None

def to_int(x: Optional[int | float | str]) -> int:
    """Convert a value to int, raise error if None or invalid"""
    if x is None:
        raise ValueError("Expected numeric ID, got None")
    return int(x)

# -------------------- SCORING FUNCTION --------------------
def score_pair(f1: FileDict, f2: FileDict) -> int:
    score = 0

    # Same size (already grouped, but explicit)
    if f1.get("size_bytes") == f2.get("size_bytes"):
        score += 30

    # Duration within 1 second
    d1 = to_float(f1.get("duration"))
    d2 = to_float(f2.get("duration"))
    if d1 is not None and d2 is not None and abs(d1 - d2) <= 1.0:
        score += 30

    # Same resolution
    w1 = to_int(f1.get("width")) if f1.get("width") is not None else None
    h1 = to_int(f1.get("height")) if f1.get("height") is not None else None
    w2 = to_int(f2.get("width")) if f2.get("width") is not None else None
    h2 = to_int(f2.get("height")) if f2.get("height") is not None else None

    if w1 is not None and h1 is not None and w2 is not None and h2 is not None:
        if w1 == w2 and h1 == h2:
            score += 20

    # Same codec
    if f1.get("codec") and f1["codec"] == f2.get("codec"):
        score += 10

    # Same EXIF datetime (images)
    if f1.get("exif_datetime") and f1["exif_datetime"] == f2.get("exif_datetime"):
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

    # Step 2: iterate over size groups
    for idx, group in enumerate(size_groups, start=1):
        size_bytes = group["size_bytes"]
        media_type = group["media_type"]

        cur.execute("""
            SELECT
                id, size_bytes, duration,
                width, height, codec, exif_datetime
            FROM files
            WHERE size_bytes = ?
              AND media_type = ?
              AND hash_full IS NULL
        """, (size_bytes, media_type))
        files: List[FileDict] = [dict(row) for row in cur.fetchall()]

        if len(files) < 2:
            continue

        inserts: List[Tuple[int, int, str, int, str]] = []

        # Step 3: pairwise comparison
        for f1, f2 in combinations(files, 2):
            score = score_pair(f1, f2)
            if score >= CONFIDENCE_THRESHOLD:
                try:
                    id1 = to_int(f1.get("id"))
                    id2 = to_int(f2.get("id"))
                except ValueError as e:
                    print(f"Skipping pair due to invalid ID: {e}")
                    continue

                inserts.append((
                    id1,
                    id2,
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
