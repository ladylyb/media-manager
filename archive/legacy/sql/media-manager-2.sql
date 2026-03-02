-- PostgreSQL migration: add and backfill duplicate_group_id for exact_hash rows.

BEGIN;

ALTER TABLE duplicate_candidates
ADD COLUMN IF NOT EXISTS duplicate_group_id BIGINT;

WITH ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY file_id_1
            ORDER BY confidence_score DESC, id ASC
        ) AS grp
    FROM duplicate_candidates
    WHERE match_type = 'exact_hash'
)
UPDATE duplicate_candidates dc
SET duplicate_group_id = ranked.grp
FROM ranked
WHERE dc.id = ranked.id
  AND dc.match_type = 'exact_hash';

COMMIT;

SELECT
    duplicate_group_id,
    COUNT(*) AS pair_count,
    string_agg(file_id_1::text || '-' || file_id_2::text, ',' ORDER BY id) AS member_pairs
FROM duplicate_candidates
WHERE duplicate_group_id IS NOT NULL
GROUP BY duplicate_group_id
ORDER BY pair_count DESC;
