"""add unified operation_runs log for all batch mutations

Revision ID: 0018_operation_runs_unified_log
Revises: 0017_phase13_drop_media_file_ci
Create Date: 2026-03-03 22:05:00
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0018_operation_runs_unified_log"
down_revision = "0017_phase13_drop_media_file_ci"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'operation_run_type') THEN
                CREATE TYPE operation_run_type AS ENUM (
                    'INGEST',
                    'PLAN',
                    'APPLY',
                    'OPERATOR_RUN',
                    'CANONICAL_RECOMPUTE',
                    'TAG_ENRICHMENT',
                    'DB_RESET'
                );
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'operation_run_status') THEN
                CREATE TYPE operation_run_status AS ENUM ('STARTED', 'COMPLETED', 'FAILED');
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS operation_runs (
            id UUID PRIMARY KEY,
            operation_type operation_run_type NOT NULL,
            status operation_run_status NOT NULL DEFAULT 'STARTED',
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ NULL,
            error_message TEXT NULL,
            context JSONB NOT NULL DEFAULT '{}'::jsonb,
            linked_run_id UUID NULL REFERENCES runs(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_operation_runs_started_at_desc ON operation_runs (started_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_operation_runs_operation_type ON operation_runs (operation_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_operation_runs_status ON operation_runs (status)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_operation_runs_status")
    op.execute("DROP INDEX IF EXISTS idx_operation_runs_operation_type")
    op.execute("DROP INDEX IF EXISTS idx_operation_runs_started_at_desc")
    op.execute("DROP TABLE IF EXISTS operation_runs")
    op.execute("DROP TYPE IF EXISTS operation_run_status")
    op.execute("DROP TYPE IF EXISTS operation_run_type")
