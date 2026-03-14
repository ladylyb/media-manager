"""phase 13 media_file create-or-augment hardened schema

Revision ID: 0015_phase13_media_file
Revises: 0014_phase12_enrich_audit
Create Date: 2026-03-03 10:20:00
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0015_phase13_media_file"
down_revision = "0014_phase12_enrich_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Coexistence strategy:
    # 1) This revision is additive only and does not alter file_contents/file_instances.
    # 2) Backfill from split identity/path tables is a separate idempotent data migration.
    # 3) Consumer cutover should happen only after explicit dual-read parity validation.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS media_file (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            discovered_path TEXT,
            current_path TEXT,
            size_bytes BIGINT,
            hash_sha256 TEXT,
            discovered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            ingested_at TIMESTAMPTZ,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            canonical_id UUID,
            quarantined_at TIMESTAMPTZ,
            deleted_at TIMESTAMPTZ
        )
        """
    )

    op.execute("ALTER TABLE media_file ADD COLUMN IF NOT EXISTS id UUID")
    op.execute("ALTER TABLE media_file ADD COLUMN IF NOT EXISTS discovered_path TEXT")
    op.execute("ALTER TABLE media_file ADD COLUMN IF NOT EXISTS current_path TEXT")
    op.execute("ALTER TABLE media_file ADD COLUMN IF NOT EXISTS size_bytes BIGINT")
    op.execute("ALTER TABLE media_file ADD COLUMN IF NOT EXISTS hash_sha256 TEXT")
    op.execute("ALTER TABLE media_file ADD COLUMN IF NOT EXISTS discovered_at TIMESTAMPTZ")
    op.execute("ALTER TABLE media_file ADD COLUMN IF NOT EXISTS ingested_at TIMESTAMPTZ")
    op.execute("ALTER TABLE media_file ADD COLUMN IF NOT EXISTS status TEXT")
    op.execute("ALTER TABLE media_file ADD COLUMN IF NOT EXISTS canonical_id UUID")
    op.execute("ALTER TABLE media_file ADD COLUMN IF NOT EXISTS quarantined_at TIMESTAMPTZ")
    op.execute("ALTER TABLE media_file ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ")

    op.execute("ALTER TABLE media_file ALTER COLUMN id SET DEFAULT gen_random_uuid()")
    op.execute("ALTER TABLE media_file ALTER COLUMN discovered_at SET DEFAULT now()")
    op.execute("ALTER TABLE media_file ALTER COLUMN status SET DEFAULT 'ACTIVE'")

    op.execute("UPDATE media_file SET id = gen_random_uuid() WHERE id IS NULL")
    op.execute("UPDATE media_file SET discovered_at = now() WHERE discovered_at IS NULL")
    op.execute("UPDATE media_file SET status = 'ACTIVE' WHERE status IS NULL")

    op.execute("ALTER TABLE media_file ALTER COLUMN id SET NOT NULL")
    op.execute("ALTER TABLE media_file ALTER COLUMN discovered_at SET NOT NULL")
    op.execute("ALTER TABLE media_file ALTER COLUMN status SET NOT NULL")

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = 'media_file'::regclass
                  AND contype = 'p'
            ) THEN
                ALTER TABLE media_file
                    ADD CONSTRAINT pk_media_file PRIMARY KEY (id);
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
                  AND conname = 'ck_media_file_status'
            ) THEN
                ALTER TABLE media_file
                    ADD CONSTRAINT ck_media_file_status
                    CHECK (status IN ('ACTIVE', 'QUARANTINED', 'DELETED'));
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

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = 'media_file'::regclass
                  AND conname = 'ck_media_file_lifecycle_consistency'
            ) THEN
                ALTER TABLE media_file
                    ADD CONSTRAINT ck_media_file_lifecycle_consistency
                    CHECK (
                        (status = 'ACTIVE' AND quarantined_at IS NULL AND deleted_at IS NULL)
                        OR (status = 'QUARANTINED' AND quarantined_at IS NOT NULL AND deleted_at IS NULL)
                        OR (status = 'DELETED' AND deleted_at IS NOT NULL)
                    );
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
                  AND conname = 'ck_media_file_ingest_after_discovery'
            ) THEN
                ALTER TABLE media_file
                    ADD CONSTRAINT ck_media_file_ingest_after_discovery
                    CHECK (ingested_at IS NULL OR ingested_at >= discovered_at);
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_media_file_hash_sha256_not_null
        ON media_file (hash_sha256)
        WHERE hash_sha256 IS NOT NULL
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_media_file_canonical_id ON media_file (canonical_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_media_file_status ON media_file (status)")


def downgrade() -> None:
    # This migration is designed as a safe create-or-augment operation for environments
    # that may already carry a partial media_file table. Downgrade is intentionally
    # non-destructive to avoid dropping pre-existing schema/data.
    pass
