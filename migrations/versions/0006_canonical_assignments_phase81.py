"""phase 8.1 canonical assignments and recompute audit tables

Revision ID: 0006_phase81_canonical
Revises: 0005_apply_audit_phase8
Create Date: 2026-03-01 00:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0006_phase81_canonical"
down_revision = "0005_apply_audit_phase8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "canonical_assignments",
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_instance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_name", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("length(trim(policy_name)) > 0", name="ck_canonical_assignments_policy_name_nonempty"),
        sa.CheckConstraint(
            "length(trim(policy_version)) > 0",
            name="ck_canonical_assignments_policy_version_nonempty",
        ),
        sa.ForeignKeyConstraint(["content_id"], ["file_contents.content_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["canonical_instance_id"], ["file_instances.file_instance_id"], ondelete="RESTRICT"),
    )
    op.create_index("idx_canonical_assignments_content_id", "canonical_assignments", ["content_id"])
    op.create_index("idx_canonical_assignments_instance_id", "canonical_assignments", ["canonical_instance_id"])
    op.create_index(
        "idx_canonical_assignments_latest",
        "canonical_assignments",
        [sa.text("content_id"), sa.text("assigned_at DESC"), sa.text("assignment_id DESC")],
    )

    op.create_table(
        "canonical_recompute_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("policy_name", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("scanned_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("changed_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("applied_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint("mode IN ('DRY_RUN','APPLY')", name="ck_canonical_recompute_runs_mode"),
        sa.CheckConstraint(
            "status IN ('STARTED','COMPLETED','FAILED','COMPLETED_WITH_ERRORS')",
            name="ck_canonical_recompute_runs_status",
        ),
        sa.CheckConstraint(
            "length(trim(policy_name)) > 0",
            name="ck_canonical_recompute_runs_policy_name_nonempty",
        ),
        sa.CheckConstraint(
            "length(trim(policy_version)) > 0",
            name="ck_canonical_recompute_runs_policy_version_nonempty",
        ),
    )
    op.create_index("idx_canonical_recompute_runs_started_at", "canonical_recompute_runs", ["started_at"])

    op.create_table(
        "canonical_recompute_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("old_canonical_instance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("new_canonical_instance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "result IN ('UNCHANGED','CHANGED','APPLIED','FAILED')",
            name="ck_canonical_recompute_items_result",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["canonical_recompute_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["content_id"], ["file_contents.content_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "sequence_no", name="uq_canonical_recompute_items_run_sequence"),
    )
    op.create_index("idx_canonical_recompute_items_run_id", "canonical_recompute_items", ["run_id"])
    op.create_index("idx_canonical_recompute_items_content_id", "canonical_recompute_items", ["content_id"])

    op.execute(
        """
        INSERT INTO canonical_assignments (
            assignment_id,
            content_id,
            canonical_instance_id,
            policy_name,
            policy_version,
            assigned_at
        )
        SELECT
            fc.content_id AS assignment_id,
            fc.content_id,
            COALESCE(
                fc.canonical_file_instance_id,
                (
                    SELECT fi.file_instance_id
                    FROM file_instances fi
                    WHERE fi.content_id = fc.content_id
                    ORDER BY fi.first_seen_at ASC, fi.file_instance_id ASC
                    LIMIT 1
                )
            ) AS canonical_instance_id,
            'FIRST_SEEN' AS policy_name,
            'v1' AS policy_version,
            now() AS assigned_at
        FROM file_contents fc
        WHERE COALESCE(
            fc.canonical_file_instance_id,
            (
                SELECT fi.file_instance_id
                FROM file_instances fi
                WHERE fi.content_id = fc.content_id
                ORDER BY fi.first_seen_at ASC, fi.file_instance_id ASC
                LIMIT 1
            )
        ) IS NOT NULL
        ON CONFLICT (assignment_id) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.drop_index("idx_canonical_recompute_items_content_id", table_name="canonical_recompute_items")
    op.drop_index("idx_canonical_recompute_items_run_id", table_name="canonical_recompute_items")
    op.drop_table("canonical_recompute_items")

    op.drop_index("idx_canonical_recompute_runs_started_at", table_name="canonical_recompute_runs")
    op.drop_table("canonical_recompute_runs")

    op.drop_index("idx_canonical_assignments_latest", table_name="canonical_assignments")
    op.drop_index("idx_canonical_assignments_instance_id", table_name="canonical_assignments")
    op.drop_index("idx_canonical_assignments_content_id", table_name="canonical_assignments")
    op.drop_table("canonical_assignments")
