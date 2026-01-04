from pathlib import Path
import sqlite3

DB_PATH = Path("media-manager.db")

def diagnostic_report():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("=== MEDIA FILES DIAGNOSTIC REPORT ===\n")

    # Total media files
    cur.execute("SELECT COUNT(*) AS cnt FROM files WHERE media_type IN ('image','video')")
    total_files = cur.fetchone()["cnt"]
    print(f"Total media files (image/video): {total_files}")

    # Files already renamed or moved
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM files f
        JOIN file_actions fa ON f.id = fa.file_id
        WHERE fa.action IN ('move','rename') AND f.media_type IN ('image','video')
    """)
    moved_files = cur.fetchone()["cnt"]
    print(f"Files already moved or renamed: {moved_files}")

    # Remaining files to rename/move
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM files f
        WHERE f.media_type IN ('image','video')
        AND f.id NOT IN (
            SELECT file_id
            FROM file_actions
            WHERE action IN ('move','rename')
        )
    """)
    remaining_files = cur.fetchone()["cnt"]
    print(f"Remaining files to process: {remaining_files}")

    # Check media_type inconsistencies
    cur.execute("""
        SELECT media_type, COUNT(*) AS cnt
        FROM files
        GROUP BY media_type
    """)
    print("\nMedia type distribution:")
    for row in cur.fetchall():
        print(f"  {row['media_type']}: {row['cnt']}")

    # Files with missing or invalid paths
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM files
        WHERE (path IS NULL OR path = '' OR NOT EXISTS (SELECT 1 FROM files WHERE id=files.id))
          AND media_type IN ('image','video')
    """)
    missing_path = cur.fetchone()["cnt"]
    print(f"\nFiles with missing or invalid path: {missing_path}")

    conn.close()
    print("\n=== END OF REPORT ===")

if __name__ == "__main__":
    diagnostic_report()
