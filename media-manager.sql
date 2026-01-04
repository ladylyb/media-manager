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


