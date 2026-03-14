"""phase 13 remove media_file canonical_id ledger field

Revision ID: 0017_phase13_drop_media_file_ci
Revises: 0016_phase13_media_file_ledger
Create Date: 2026-03-03 16:10:00
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0017_phase13_drop_media_file_ci"
down_revision = "0016_phase13_media_file_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE media_file DROP CONSTRAINT IF EXISTS fk_media_file_canonical_id")
    op.execute("ALTER TABLE media_file DROP CONSTRAINT IF EXISTS ck_media_file_not_self_canonical")
    op.execute("DROP INDEX IF EXISTS idx_media_file_canonical_id")
    op.execute("ALTER TABLE media_file DROP COLUMN IF EXISTS canonical_id")


def downgrade() -> None:
    op.execute("ALTER TABLE media_file ADD COLUMN IF NOT EXISTS canonical_id UUID")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = 'media_file'::regclass
                  AND conname = 'fk_media_file_canonical_id'
            ) THEN
                ALTER TABLE media_file
                    ADD CONSTRAINT fk_media_file_canonical_id
                    FOREIGN KEY (canonical_id)
                    REFERENCES media_file(id)
                    ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = 'media_file'::regclass
                  AND conname = 'ck_media_file_not_self_canonical'
            ) THEN
                ALTER TABLE media_file
                    ADD CONSTRAINT ck_media_file_not_self_canonical
                    CHECK (canonical_id IS NULL OR canonical_id <> id);
            END IF;
        END $$;
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_media_file_canonical_id ON media_file (canonical_id)")
