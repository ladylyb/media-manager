import sqlite3
import hashlib
import os

DB_PATH = r"media-manager.db"
PARTIAL_CHUNK_SIZE = 1024 * 1024  # 1MB

def get_partial_hash(file_path):
    """Compute hash of first + last 1MB of the file"""
    try:
        size = os.path.getsize(file_path)
        if size < PARTIAL_CHUNK_SIZE * 2:
            # Small file → full hash is same as partial
            with open(file_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        with open(file_path, "rb") as f:
            first = f.read(PARTIAL_CHUNK_SIZE)
            f.seek(max(size - PARTIAL_CHUNK_SIZE, 0))
            last = f.read(PARTIAL_CHUNK_SIZE)
        return hashlib.sha256(first + last).hexdigest()
    except Exception as e:
        print(f"Error hashing partial {file_path}: {e}")
        return None

def get_full_hash(file_path):
    """Compute full SHA256 hash"""
    try:
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
                sha.update(chunk)
        return sha.hexdigest()
    except Exception as e:
        print(f"Error hashing full {file_path}: {e}")
        return None

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    cur = conn.cursor()

    # Step 1: Identify files needing hashing (size_groups > 1)
    cur.execute("""
        SELECT f.id, f.path
        FROM files f
        JOIN (
            SELECT size_bytes
            FROM files
            GROUP BY size_bytes
            HAVING COUNT(*) > 1
        ) s ON f.size_bytes = s.size_bytes
        WHERE f.hash_partial IS NULL
    """)

    rows = cur.fetchall()
    print(f"{len(rows)} files need hashing")

    for idx, (file_id, file_path) in enumerate(rows, 1):
        file_path = os.path.normpath(file_path)
        partial_hash = get_partial_hash(file_path)
        if not partial_hash:
            continue

        # Update partial hash
        cur.execute(
            "UPDATE files SET hash_partial = ? WHERE id = ?",
            (partial_hash, file_id)
        )
        conn.commit()

        # Check if other files share the same partial hash
        cur.execute("""
            SELECT COUNT(*) FROM files
            WHERE hash_partial = ? AND hash_full IS NULL
        """, (partial_hash,))
        count = cur.fetchone()[0]

        full_hash = None
        if count > 1:
            full_hash = get_full_hash(file_path)
            if full_hash:
                cur.execute(
                    "UPDATE files SET hash_full = ?, hash_algo = 'sha256' WHERE id = ?",
                    (full_hash, file_id)
                )
                conn.commit()

        if idx % 50 == 0:
            print(f"Processed {idx}/{len(rows)} files")

    conn.close()
    print("Hashing complete")

if __name__ == "__main__":
    main()
