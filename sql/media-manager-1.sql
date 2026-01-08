
    1 AS audit_run_id,   -- replace if needed
    file_id,
    to_be_deleted_path,
    reconstructed_filename,
    CASE
        WHEN LOWER(found_in_db) = 'true' THEN 1
        ELSE 0
    END AS found_in_files,
    actions,
    notes
FROM _tmp_deletion_audit_import;


-- DROP TABLE deletion_audit_candidates;

CREATE TABLE deletion_audit_candidates (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_run_id         INTEGER NOT NULL,
    reconstructed_name  TEXT,
    observed_path        TEXT NOT NULL,
    audit_notes          TEXT,
	raw_actions_snapshot TEXT,
    created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (audit_run_id)
        REFERENCES deletion_audit_runs(id)
);

CREATE TABLE deletion_audit_candidate_files (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_candidate_id  INTEGER NOT NULL,
    related_file_id     INTEGER NOT NULL,

    FOREIGN KEY (audit_candidate_id)
        REFERENCES deletion_audit_candidates(id),
    FOREIGN KEY (related_file_id)
        REFERENCES files(id)
);


INSERT INTO deletion_audit_candidates (
    audit_run_id,
    reconstructed_name,
    observed_path,
    audit_notes,
	raw_actions_snapshot
)
SELECT
    1,
    reconstructed_filename,
    to_be_deleted_path,
    notes,
	actions
FROM _tmp_deletion_audit_import;


SELECT * FROM deletion_audit_candidates;

WITH RECURSIVE split_ids AS (
    SELECT
        dac.id AS audit_candidate_id,
        TRIM(
            SUBSTR(t.file_id, 1,
                   INSTR(t.file_id || ',', ',') - 1)
        ) AS related_file_id,
        SUBSTR(
            t.file_id || ',',
            INSTR(t.file_id || ',', ',') + 1
        ) AS rest
    FROM _tmp_deletion_audit_import t
    JOIN deletion_audit_candidates dac
      ON dac.audit_run_id = 1
     AND dac.observed_path = t.to_be_deleted_path
     AND (
         dac.reconstructed_name = t.reconstructed_filename
         OR (dac.reconstructed_name IS NULL AND t.reconstructed_filename IS NULL)
     )
    WHERE t.file_id IS NOT NULL
      AND t.file_id <> ''

    UNION ALL

    SELECT
        audit_candidate_id,
        TRIM(
            SUBSTR(rest, 1,
                   INSTR(rest, ',') - 1)
        ),
        SUBSTR(rest, INSTR(rest, ',') + 1)
    FROM split_ids
    WHERE rest <> ''
)
INSERT INTO deletion_audit_candidate_files (
    audit_candidate_id,
    related_file_id
)
SELECT
    audit_candidate_id,
    CAST(related_file_id AS INTEGER)
FROM split_ids;



CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_audit_candidate_file
ON deletion_audit_candidate_files (audit_candidate_id, related_file_id);

SELECT * FROM deletion_audit_candidate_files WHERE audit_candidate_id = 902;

SELECT
    dac.id AS audit_candidate_id,
    dac.observed_path,
    COUNT(dacf.related_file_id) AS related_files
FROM deletion_audit_candidates dac
LEFT JOIN deletion_audit_candidate_files dacf
       ON dac.id = dacf.audit_candidate_id
WHERE dac.audit_run_id = 1
GROUP BY dac.id
ORDER BY related_files DESC;




SELECT
    dac.id AS audit_candidate_id,
    dac.observed_path,
    dac.reconstructed_name,
    dac.audit_notes,

    f.id AS related_file_id,
    f.path AS related_path,
    f.filename,
    f.size_bytes,
    f.hash_full,
    f.mtime,

    fa.action,
    fa.target_path,
    fa.decided_at

	FROM deletion_audit_candidate_files dacf
JOIN deletion_audit_candidates dac
     ON dac.id = dacf.audit_candidate_id
LEFT JOIN files f
     ON f.id = dacf.related_file_id
LEFT JOIN file_actions fa
     ON fa.file_id = f.id
WHERE dac.id <> 902
ORDER BY f.filename
;
