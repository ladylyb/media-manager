"""add duplicate bin item fields

Revision ID: 0030
Revises: 0029
Create Date: 2026-04-02 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("duplicate_reclaim_items", sa.Column("planned_bin_path", sa.Text(), nullable=True))
    op.add_column("duplicate_reclaim_items", sa.Column("bin_path", sa.Text(), nullable=True))
    op.add_column("duplicate_reclaim_items", sa.Column("bin_entered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("duplicate_reclaim_items", sa.Column("restore_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("duplicate_reclaim_items", sa.Column("bin_state", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("duplicate_reclaim_items", "bin_state")
    op.drop_column("duplicate_reclaim_items", "restore_expires_at")
    op.drop_column("duplicate_reclaim_items", "bin_entered_at")
    op.drop_column("duplicate_reclaim_items", "bin_path")
    op.drop_column("duplicate_reclaim_items", "planned_bin_path")
