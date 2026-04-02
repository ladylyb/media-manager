"""drop dead duplicate reclaim record legacy columns

Revision ID: 0032
Revises: 0031
Create Date: 2026-04-02 02:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("duplicate_reclaim_records", "expires_at")
    op.drop_column("duplicate_reclaim_records", "reclaimed_at")
    op.drop_column("duplicate_reclaim_records", "archive_path")


def downgrade() -> None:
    # Destructive cleanup: downgrade restores schema shape only, not historical values.
    op.add_column("duplicate_reclaim_records", sa.Column("archive_path", sa.Text(), nullable=True))
    op.add_column("duplicate_reclaim_records", sa.Column("reclaimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("duplicate_reclaim_records", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
