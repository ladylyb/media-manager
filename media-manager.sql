/*
## 1. Core principles behind this schema

* **One row = one file instance**
* Raw facts are stored once; decisions are layered on top
* Nullable metadata (recovered files are messy)
* Everything is explainable via SQL
* Safe to re-run scans without clobbering old data
*/

--  2. `scans` — track multiple runs (important)
/*
This lets you re-scan later without overwriting history.
**Why**

* You *will* rerun this
* Makes rollback and comparison trivial
*/

CREATE TABLE scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    root_path TEXT NOT NULL,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at DATETIME,
    notes TEXT
);

---
/*
### Design notes

* `REAL` for times = Unix timestamps (portable)
* Flags let you resume interrupted runs
* `path` is full path → guaranteed uniqueness *within a scan*
* `extension` is advisory only (recovered files lie)

*/
-- 3. `files` — the heart of the system
CREATE TABLE files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Scan context
    scan_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    filename TEXT NOT NULL,
    extension TEXT,

    -- Filesystem metadata
    size_bytes INTEGER NOT NULL,
    mtime REAL,
    ctime REAL,

    -- Hashing
    hash_partial TEXT,
    hash_full TEXT,
    hash_algo TEXT,

    -- Media classification
    media_type TEXT CHECK (media_type IN ('image','video','audio','other')),

    -- Media metadata
    duration REAL,
    width INTEGER,
    height INTEGER,
    codec TEXT,
    bitrate INTEGER,
    exif_datetime TEXT,

    -- Status flags
    is_hashed INTEGER DEFAULT 0,
    is_metadata_extracted INTEGER DEFAULT 0,

    FOREIGN KEY (scan_id) REFERENCES scans(id)
);


ALTER TABLE files ADD COLUMN camera_model TEXT;
ALTER TABLE files ADD COLUMN orientation TEXT;

-- 4. Indexes (critical for performance)
-- SQLite lives or dies on indexes — these matter.
/*
**Why**

* Size grouping becomes instant
* Hash lookups stay fast even with 100k+ files
*/

```sql
CREATE INDEX idx_files_scan ON files(scan_id);
CREATE INDEX idx_files_size ON files(size_bytes);
CREATE INDEX idx_files_hash_full ON files(hash_full);
CREATE INDEX idx_files_hash_partial ON files(hash_partial);
CREATE INDEX idx_files_media_type ON files(media_type);

SELECT filename FROM files;

--- 5. `duplicate_candidates` — relationships, not actions
/*
This is *the most important design choice*.

### `match_type` examples

* `exact_hash`
* `same_size_same_duration`
* `metadata_similarity`
* `manual_mark`

**Why**

* Keeps detection separate from deletion
* Allows multiple match theories per pair
* Makes audit trails possible

*/
CREATE TABLE duplicate_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    file_id_1 INTEGER NOT NULL,
    file_id_2 INTEGER NOT NULL,

    match_type TEXT NOT NULL,
    confidence_score INTEGER NOT NULL CHECK (confidence_score BETWEEN 0 AND 100),

    reason TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (file_id_1) REFERENCES files(id),
    FOREIGN KEY (file_id_2) REFERENCES files(id),

    UNIQUE (file_id_1, file_id_2, match_type)
);

--- 6. Optional but powerful: `file_actions`
/*
Use this only **after** you trust detection.
*/
CREATE TABLE file_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,

    action TEXT CHECK (action IN ('keep','move','delete','ignore')) NOT NULL,
    target_path TEXT,
    decided_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,

    FOREIGN KEY (file_id) REFERENCES files(id)
);


--  7. Optional: views for sanity & speed
-- Files that even need hashing
CREATE VIEW files_needing_hash AS
SELECT f.*
FROM files f
JOIN (
    SELECT size_bytes
    FROM files
    GROUP BY size_bytes
    HAVING COUNT(*) > 1
) s ON f.size_bytes = s.size_bytes
WHERE f.hash_full IS NULL;


-- Exact duplicates view
CREATE VIEW exact_duplicates AS
SELECT hash_full, COUNT(*) AS cnt
FROM files
WHERE hash_full IS NOT NULL
GROUP BY hash_full
HAVING cnt > 1;


-- Query #1
SELECT COUNT(*) FROM files;
SELECT * FROM files;

-- Query #2
SELECT size_bytes, COUNT(*)
FROM files
GROUP BY size_bytes
HAVING COUNT(*) > 1
ORDER BY COUNT(*) DESC;


-- Insert exact duplicates into duplicate_candidates
INSERT OR IGNORE INTO duplicate_candidates (
    file_id_1,
    file_id_2,
    match_type,
    confidence_score,
    reason
)
SELECT
    f1.id,
    f2.id,
    'exact_hash',
    100,
    'Full SHA256 hash match'
FROM files f1
JOIN files f2
  ON f1.hash_full = f2.hash_full
 AND f1.hash_full IS NOT NULL
 AND f1.id < f2.id;

-- Inspect exact duplicates
SELECT
    dc.confidence_score,
    dc.reason,
    f1.path AS file_1,
    f2.path AS file_2
FROM duplicate_candidates dc
JOIN files f1 ON dc.file_id_1 = f1.id
JOIN files f2 ON dc.file_id_2 = f2.id
WHERE dc.match_type = 'exact_hash'
ORDER BY f1.size_bytes DESC;

-- STEP 2 — Probable duplicate scoring (metadata-based)
/*

— Define a scoring heuristic (transparent & tunable)

We’ll use a 100-point scale:

| Signal                      | Points   |
| --------------------------- | -------- |
| Same media_type             | required |
| Same size_bytes             | +30      |
| Duration within 1 second    | +30      |
| Same width & height         | +20      |
| Same codec                  | +10      |
| Same EXIF datetime (images) | +10      |


👉 Threshold: ≥70 = probable duplicate

- Insert probable duplicates

This SQL looks long, but it’s intentionally explicit so you can reason about it later.
*/
INSERT OR IGNORE INTO duplicate_candidates (
    file_id_1,
    file_id_2,
    match_type,
    confidence_score,
    reason
)
SELECT
    f1.id,
    f2.id,
    'probable_metadata',
    (
        CASE WHEN f1.size_bytes = f2.size_bytes THEN 30 ELSE 0 END +
        CASE
            WHEN f1.duration IS NOT NULL
             AND f2.duration IS NOT NULL
             AND ABS(f1.duration - f2.duration) <= 1.0
            THEN 30 ELSE 0
        END +
        CASE
            WHEN f1.width = f2.width
             AND f1.height = f2.height
             AND f1.width IS NOT NULL
            THEN 20 ELSE 0
        END +
        CASE
            WHEN f1.codec = f2.codec
             AND f1.codec IS NOT NULL
            THEN 10 ELSE 0
        END +
        CASE
            WHEN f1.exif_datetime = f2.exif_datetime
             AND f1.exif_datetime IS NOT NULL
            THEN 10 ELSE 0
        END
    ) AS confidence_score,
    'Metadata similarity (size/duration/resolution/codec)'
FROM files f1
JOIN files f2
  ON f1.media_type = f2.media_type
 AND f1.id < f2.id
WHERE
    f1.media_type IN ('image', 'video')
    AND f1.hash_full IS NULL
    AND f2.hash_full IS NULL;

CREATE INDEX IF NOT EXISTS idx_files_size_media
ON files(size_bytes, media_type);

CREATE INDEX IF NOT EXISTS idx_files_metadata
ON files(duration, width, height, codec);

/*
STEP 3 — Inspect probable duplicates
3️⃣A — High-confidence only
*/
SELECT
    dc.confidence_score,
    f1.path AS file_1,
    f2.path AS file_2,
    f1.size_bytes,
    f1.duration,
    f1.width,
    f1.height,
    f1.codec
FROM duplicate_candidates dc
JOIN files f1 ON dc.file_id_1 = f1.id
JOIN files f2 ON dc.file_id_2 = f2.id
WHERE dc.match_type = 'probable_metadata'
  AND dc.confidence_score >= 70
ORDER BY dc.confidence_score DESC;


SELECT size_bytes, media_type
FROM files
WHERE media_type IN ('image','video')
  AND hash_full IS NULL
GROUP BY size_bytes, media_type
HAVING COUNT(*) > 1;

SELECT match_type, count(1) FROM duplicate_candidates
group by match_type;

SELECT * FROM duplicate_candidates
WHERE match_type = 'probable_metadata';

PRAGMA wal_checkpoint(FULL);

/*SELECT f.*
FROM files f
LEFT JOIN file_actions fa ON f.id = fa.file_id AND fa.action IN ('move', 'rename')
WHERE fa.id IS NULL
AND f.media_type IN ('image', 'video');*/

SELECT f.*
FROM files f
WHERE f.media_type IN ('image','video')
  AND f.id NOT IN (
      SELECT file_id
      FROM file_actions
      WHERE action IN ('move','rename')
  );



ALTER TABLE file_actions RENAME TO _file_actions_old;


CREATE TABLE file_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    action TEXT CHECK (action IN ('keep','move','delete','ignore','rename')) NOT NULL,
    target_path TEXT,
    decided_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    FOREIGN KEY (file_id) REFERENCES files(id)
);

INSERT INTO file_actions (id, file_id, action, target_path, decided_at, notes)
SELECT id, file_id, action, target_path, decided_at, notes
FROM _file_actions_old;

SELECT * FROM file_actions;
SELECT * FROM _file_actions_old;

DROP TABLE _file_actions_old;



SELECT f.id, f.path, f.filename, f.extension, f.exif_datetime, f.mtime
FROM files f
WHERE f.media_type IN ('image','video')
    AND NOT EXISTS (
        SELECT 1
        FROM file_actions fa
        WHERE fa.file_id = f.id
        AND fa.action IN ('move','rename')
    )        
;        

SELECT f.id, f.filename, f.media_type, f.path, fa.action, fa.target_path 
FROM files f
    JOIN file_actions fa
  ON fa.file_id = f.id AND fa.action IN ('move','rename')
WHERE f.media_type IN ('image','video');

SELECT * FROM file_actions;