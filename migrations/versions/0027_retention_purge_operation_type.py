"""add retention purge operation type

Revision ID: 0027
Revises: 0026
Create Date: 2026-03-25 01:45:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE operation_run_type ADD VALUE IF NOT EXISTS 'RETENTION_PURGE'")
    op.add_column("duplicate_reclaim_items", sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("integrity_quarantine_records", sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("integrity_quarantine_records", "purged_at")
    op.drop_column("duplicate_reclaim_items", "purged_at")
