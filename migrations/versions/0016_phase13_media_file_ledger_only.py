"""phase 13 ledger-only media_file semantics

Revision ID: 0016_phase13_media_file_ledger
Revises: 0015_phase13_media_file
Create Date: 2026-03-03 12:40:00
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0016_phase13_media_file_ledger"
down_revision = "0015_phase13_media_file"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE media_file ALTER COLUMN status SET DEFAULT 'INGESTED'")
    op.execute(
        """
        UPDATE media_file
        SET status = CASE
            WHEN status = 'DELETED' THEN 'DELETED'
            WHEN status IN ('ACTIVE', 'QUARANTINED') THEN 'PROCESSED'
            ELSE 'INGESTED'
        END
        """
    )
    op.execute(
        """
        UPDATE media_file
        SET quarantined_at = NULL
        WHERE status IN ('INGESTED', 'PROCESSED')
        """
    )

    op.execute("ALTER TABLE media_file DROP CONSTRAINT IF EXISTS ck_media_file_status")
    op.execute(
        """
        ALTER TABLE media_file
        ADD CONSTRAINT ck_media_file_status
        CHECK (status IN ('INGESTED', 'PROCESSED', 'DELETED'))
        """
    )

    op.execute("ALTER TABLE media_file DROP CONSTRAINT IF EXISTS ck_media_file_lifecycle_consistency")
    op.execute(
        """
        ALTER TABLE media_file
        ADD CONSTRAINT ck_media_file_lifecycle_consistency
        CHECK (
            (status = 'INGESTED' AND deleted_at IS NULL AND quarantined_at IS NULL)
            OR (status = 'PROCESSED' AND deleted_at IS NULL AND quarantined_at IS NULL)
            OR (status = 'DELETED' AND deleted_at IS NOT NULL)
        )
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_media_file_current_path_live
        ON media_file (current_path)
        WHERE current_path IS NOT NULL AND status <> 'DELETED'
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN media_file.canonical_id IS
        'Reserved for future phase; unused in Phase 13 ledger-only mode.'
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE media_file DROP CONSTRAINT IF EXISTS ck_media_file_lifecycle_consistency")
    op.execute(
        """
        ALTER TABLE media_file
        ADD CONSTRAINT ck_media_file_lifecycle_consistency
        CHECK (
            (status = 'ACTIVE' AND quarantined_at IS NULL AND deleted_at IS NULL)
            OR (status = 'QUARANTINED' AND quarantined_at IS NOT NULL AND deleted_at IS NULL)
            OR (status = 'DELETED' AND deleted_at IS NOT NULL)
        )
        """
    )
    op.execute("ALTER TABLE media_file DROP CONSTRAINT IF EXISTS ck_media_file_status")
    op.execute(
        """
        ALTER TABLE media_file
        ADD CONSTRAINT ck_media_file_status
        CHECK (status IN ('ACTIVE', 'QUARANTINED', 'DELETED'))
        """
    )
    op.execute("DROP INDEX IF EXISTS uq_media_file_current_path_live")
    op.execute("ALTER TABLE media_file ALTER COLUMN status SET DEFAULT 'ACTIVE'")
