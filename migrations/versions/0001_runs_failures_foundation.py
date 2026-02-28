"""create runs and failure_events foundation tables

Revision ID: 0001_runs_failures_foundation
Revises:
Create Date: 2026-02-27 22:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_runs_failures_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_state = postgresql.ENUM(
        "CREATED",
        "PLANNED",
        "APPLYING",
        "FAILED",
        "COMPLETED",
        "ABORTED",
        name="run_state",
    )
    failure_phase = postgresql.ENUM("planning", "apply", name="failure_phase")

    run_state.create(op.get_bind(), checkfirst=True)
    failure_phase.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("state", run_state, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )

    op.create_index(
        "uq_runs_single_applying",
        "runs",
        ["state"],
        unique=True,
        postgresql_where=sa.text("state = 'APPLYING'"),
    )

    op.create_table(
        "failure_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phase", failure_phase, nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="RESTRICT"),
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_failure_events_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'failure_events is append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_failure_events_no_update
        BEFORE UPDATE ON failure_events
        FOR EACH ROW
        EXECUTE FUNCTION prevent_failure_events_mutation();
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_failure_events_no_delete
        BEFORE DELETE ON failure_events
        FOR EACH ROW
        EXECUTE FUNCTION prevent_failure_events_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_failure_events_no_delete ON failure_events")
    op.execute("DROP TRIGGER IF EXISTS trg_failure_events_no_update ON failure_events")
    op.execute("DROP FUNCTION IF EXISTS prevent_failure_events_mutation")

    op.drop_table("failure_events")
    op.drop_index("uq_runs_single_applying", table_name="runs")
    op.drop_table("runs")

    failure_phase = postgresql.ENUM("planning", "apply", name="failure_phase")
    run_state = postgresql.ENUM(
        "CREATED",
        "PLANNED",
        "APPLYING",
        "FAILED",
        "COMPLETED",
        "ABORTED",
        name="run_state",
    )

    failure_phase.drop(op.get_bind(), checkfirst=True)
    run_state.drop(op.get_bind(), checkfirst=True)
