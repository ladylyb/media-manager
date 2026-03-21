"""add duplicate group review state

Revision ID: 0021
Revises: 0020
Create Date: 2026-03-21 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "duplicate_group_reviews",
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_status", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("reviewed_canonical_instance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("group_signature", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "review_status IN ('looks_right', 'needs_review', 'not_sure')",
            name="ck_duplicate_group_reviews_status",
        ),
        sa.ForeignKeyConstraint(["content_id"], ["file_contents.content_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["reviewed_canonical_instance_id"],
            ["file_instances.file_instance_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("content_id"),
    )
    op.create_index(
        "idx_duplicate_group_reviews_reviewed_at",
        "duplicate_group_reviews",
        ["reviewed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_duplicate_group_reviews_reviewed_at", table_name="duplicate_group_reviews")
    op.drop_table("duplicate_group_reviews")
