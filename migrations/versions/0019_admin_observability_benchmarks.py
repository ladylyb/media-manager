"""add benchmark run persistence for admin benchmarks

Revision ID: 0019_admin_benchmarks
Revises: 0018_operation_runs_unified_log
Create Date: 2026-03-14 12:30:00
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0019_admin_benchmarks"
down_revision = "0018_operation_runs_unified_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'operation_run_type') THEN
                BEGIN
                    ALTER TYPE operation_run_type ADD VALUE IF NOT EXISTS 'BENCHMARK_METADATA';
                EXCEPTION
                    WHEN duplicate_object THEN NULL;
                END;
                BEGIN
                    ALTER TYPE operation_run_type ADD VALUE IF NOT EXISTS 'BENCHMARK_DISCOVERY';
                EXCEPTION
                    WHEN duplicate_object THEN NULL;
                END;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'benchmark_run_type') THEN
                CREATE TYPE benchmark_run_type AS ENUM ('METADATA', 'DISCOVERY');
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'benchmark_run_status') THEN
                CREATE TYPE benchmark_run_status AS ENUM (
                    'QUEUED',
                    'RUNNING',
                    'COMPLETED',
                    'FAILED',
                    'CANCEL_REQUESTED',
                    'CANCELLED'
                );
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS benchmark_runs (
            id UUID PRIMARY KEY,
            operation_run_id UUID NOT NULL UNIQUE REFERENCES operation_runs(id) ON DELETE CASCADE,
            benchmark_type benchmark_run_type NOT NULL,
            status benchmark_run_status NOT NULL DEFAULT 'QUEUED',
            parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
            report_payload JSONB NULL,
            summary_payload JSONB NULL,
            cleanup_status TEXT NULL,
            cleanup_error TEXT NULL,
            error_message TEXT NULL,
            queued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at TIMESTAMPTZ NULL,
            completed_at TIMESTAMPTZ NULL,
            cancel_requested_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_benchmark_runs_status ON benchmark_runs (status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_benchmark_runs_type ON benchmark_runs (benchmark_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_benchmark_runs_queued_at ON benchmark_runs (queued_at DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_benchmark_runs_queued_at")
    op.execute("DROP INDEX IF EXISTS idx_benchmark_runs_type")
    op.execute("DROP INDEX IF EXISTS idx_benchmark_runs_status")
    op.execute("DROP TABLE IF EXISTS benchmark_runs")
    op.execute("DROP TYPE IF EXISTS benchmark_run_status")
    op.execute("DROP TYPE IF EXISTS benchmark_run_type")
