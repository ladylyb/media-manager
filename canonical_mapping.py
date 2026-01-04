from pathlib import Path
import sqlite3
from typing import Dict, List, Tuple

DB_PATH = Path("media-manager.db")

def pick_canonical(files: List[Dict]) -> Dict:
    """
    Pick the canonical file from a list of duplicates.
    Rules:
        1. Highest resolution (width * height)
        2. Largest size_bytes
        3. Earliest timestamp (exif_datetime > ctime)
    """
    def sort_key(f: Dict):
        resolution = (f.get("width") or 0) * (f.get("height") or 0)
        size = f.get("size_bytes") or 0
        # Prefer EXIF datetime, fallback to ctime, else max value
        ts = f.get("exif_datetime") or f.get("ctime") or 9999999999
        return (-resolution, -size, ts)

    return sorted(files, key=sort_key)[0]

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Step 1: Build duplicate groups
    cur.execute("""
        SELECT file_id_1, file_id_2
        FROM duplicate_candidates
    """)
    rows = cur.fetchall()

    # Build undirected groups
    groups: List[set[int]] = []
    file_to_group: Dict[int, set[int]] = {}

    for r in rows:
        f1, f2 = r["file_id_1"], r["file_id_2"]
        g1 = file_to_group.get(f1)
        g2 = file_to_group.get(f2)

        if g1 and g2 and g1 != g2:
            # Merge groups
            merged = g1.union(g2)
            for f in merged:
                file_to_group[f] = merged
            groups = [g for g in groups if g != g1 and g != g2]
            groups.append(merged)
        elif g1:
            g1.add(f2)
            file_to_group[f2] = g1
        elif g2:
            g2.add(f1)
            file_to_group[f1] = g2
        else:
            new_group = {f1, f2}
            groups.append(new_group)
            file_to_group[f1] = new_group
            file_to_group[f2] = new_group

    print(f"Found {len(groups)} duplicate groups")

    # Step 2: Pick canonical file per group
    canonical_mapping: Dict[int, List[int]] = {}

    for idx, group in enumerate(groups, start=1):
        cur.execute(f"""
            SELECT *
            FROM files
            WHERE id IN ({','.join(['?']*len(group))})
        """, list(group))
        files = [dict(r) for r in cur.fetchall()]
        canonical = pick_canonical(files)
        duplicates = [f["id"] for f in files if f["id"] != canonical["id"]]
        canonical_mapping[canonical["id"]] = duplicates
        print(f"[{idx}/{len(groups)}] canonical: {canonical['filename']} → {len(duplicates)} duplicates")

    # Optional: store mapping in memory or export
    conn.close()
    print("Canonical mapping complete")
    return canonical_mapping

if __name__ == "__main__":
    mapping = main()
