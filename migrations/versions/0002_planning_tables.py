"""add planning backbone tables: content_objects, files, planned_actions

Revision ID: 0002_planning_tables
Revises: 0001_runs_failures_foundation
Create Date: 2026-02-28 00:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0002_planning_tables"
down_revision = "0001_runs_failures_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_objects",
        sa.Column("hash", sa.Text(), primary_key=True, nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("hash", sa.Text(), nullable=False),
        sa.Column("is_duplicate", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("original_file_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["hash"], ["content_objects.hash"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["original_file_id"], ["files.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("path", name="uq_files_path"),
    )
    op.create_index("idx_files_hash", "files", ["hash"])
    op.create_index("idx_files_original_file_id", "files", ["original_file_id"])

    op.create_table(
        "planned_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("target_path", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="RESTRICT"),
    )
    op.create_index("idx_planned_actions_run_id", "planned_actions", ["run_id"])
    op.create_index("idx_planned_actions_file_id", "planned_actions", ["file_id"])
    op.create_index("idx_planned_actions_action_type", "planned_actions", ["action_type"])

    op.execute(
        """
        CREATE UNIQUE INDEX uq_planned_actions_idempotent
        ON planned_actions (run_id, file_id, action_type, source_path, COALESCE(target_path, ''));
        """
    )


def downgrade() -> None:
    op.drop_index("uq_planned_actions_idempotent", table_name="planned_actions")
    op.drop_index("idx_planned_actions_action_type", table_name="planned_actions")
    op.drop_index("idx_planned_actions_file_id", table_name="planned_actions")
    op.drop_index("idx_planned_actions_run_id", table_name="planned_actions")
    op.drop_table("planned_actions")

    op.drop_index("idx_files_original_file_id", table_name="files")
    op.drop_index("idx_files_hash", table_name="files")
    op.drop_table("files")

    op.drop_table("content_objects")
