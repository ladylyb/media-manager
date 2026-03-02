-- PostgreSQL-compatible legacy workflow script.
-- Includes schema bootstrap and duplicate candidate generation routines.

\i legacy_schema.sql

-- Exact-hash duplicate generation.
INSERT INTO duplicate_candidates (
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
 AND f1.id < f2.id
ON CONFLICT (file_id_1, file_id_2, match_type) DO NOTHING;

-- Metadata-similarity duplicate generation.
INSERT INTO duplicate_candidates (
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
    AND f2.hash_full IS NULL
ON CONFLICT (file_id_1, file_id_2, match_type) DO NOTHING;

-- Optional legacy action-table migration helpers.
\i media-manager-1.sql
\i media-manager-2.sql

-- Useful diagnostics.
SELECT COUNT(*) AS files_count FROM files;
SELECT COUNT(*) AS duplicate_candidates_count FROM duplicate_candidates;
SELECT match_type, COUNT(*) AS count_by_type
FROM duplicate_candidates
GROUP BY match_type
ORDER BY match_type;
