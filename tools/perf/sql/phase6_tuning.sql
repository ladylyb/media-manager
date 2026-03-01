-- Phase 6 PostgreSQL tuning checklist for metadata extraction and lookup paths.

-- 1) Validate index coverage and usage.
SELECT indexrelname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
  AND relname IN ('media_metadata', 'metadata_codes', 'file_contents', 'file_instances')
ORDER BY idx_scan DESC, indexrelname;

-- 2) Verify selective metadata lookup by content id.
EXPLAIN (ANALYZE, BUFFERS)
SELECT mc.code_type, mm.decode_value
FROM media_metadata mm
JOIN metadata_codes mc ON mc.id = mm.code_id
WHERE mm.content_id = '00000000-0000-0000-0000-000000000000';

-- 3) Inspect UPSERT path pressure by content_id/code_id key.
EXPLAIN (ANALYZE, BUFFERS)
INSERT INTO media_metadata (id, content_id, code_id, decode_value, extracted_at)
VALUES (gen_random_uuid(), '00000000-0000-0000-0000-000000000000', '11111111-1111-1111-1111-111111111111', 'LL', now())
ON CONFLICT (content_id, code_id)
DO UPDATE SET decode_value = EXCLUDED.decode_value, extracted_at = now();

-- 4) Optional: if pg_stat_statements is available, inspect hot statements.
-- SELECT query, calls, mean_exec_time, rows
-- FROM pg_stat_statements
-- WHERE query ILIKE '%media_metadata%' OR query ILIKE '%metadata_codes%'
-- ORDER BY mean_exec_time DESC
-- LIMIT 20;

-- 5) Table health checks for potential bloat and stale stats.
ANALYZE media_metadata;
ANALYZE metadata_codes;
