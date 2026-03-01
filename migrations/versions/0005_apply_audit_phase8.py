"""phase 8 apply audit tables

Revision ID: 0005_apply_audit_phase8
Revises: 0004_identity_ingestion_split
Create Date: 2026-03-01 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0005_apply_audit_phase8"
down_revision = "0004_identity_ingestion_split"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "apply_audit_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("total_actions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("applied_actions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("skipped_actions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("collision_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('PLANNED','APPLYING','COMPLETED','FAILED')",
            name="ck_apply_audit_runs_status",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="RESTRICT"),
    )
    op.create_index("idx_apply_audit_runs_run_id", "apply_audit_runs", ["run_id"])

    op.create_table(
        "apply_audit_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("planned_action_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("target_path", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("result IN ('APPLIED','SKIPPED','FAILED')", name="ck_apply_audit_items_result"),
        sa.ForeignKeyConstraint(["run_id"], ["apply_audit_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["planned_action_id"], ["planned_actions.id"], ondelete="RESTRICT"),
    )
    op.create_index("idx_apply_audit_items_run_id", "apply_audit_items", ["run_id"])
    op.create_index("idx_apply_audit_items_planned_action_id", "apply_audit_items", ["planned_action_id"])


def downgrade() -> None:
    op.drop_index("idx_apply_audit_items_planned_action_id", table_name="apply_audit_items")
    op.drop_index("idx_apply_audit_items_run_id", table_name="apply_audit_items")
    op.drop_table("apply_audit_items")

    op.drop_index("idx_apply_audit_runs_run_id", table_name="apply_audit_runs")
    op.drop_table("apply_audit_runs")
