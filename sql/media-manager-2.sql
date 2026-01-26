BEGIN TRANSACTION;

ALTER TABLE file_actions RENAME TO file_actions_old;

CREATE TABLE file_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,

    action TEXT CHECK (
        action IN ('keep','move','delete','ignore','organize', 'rename')
    ) NOT NULL,

    target_path TEXT,
    decided_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,

    FOREIGN KEY (file_id) REFERENCES files(id)
);

INSERT INTO file_actions (
    id, file_id, action, target_path, decided_at, notes
)
SELECT
    id, file_id, action, target_path, decided_at, notes
FROM file_actions_old;

DROP TABLE file_actions_old;

COMMIT;


-- DROP TABLE file_actions;

SELECT COUNT(1) FROM file_actions;
