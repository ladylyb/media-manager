"""add incremental integrity scan snapshot fields

Revision ID: 0029
Revises: 0028
Create Date: 2026-03-28 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("integrity_checks", sa.Column("last_completed_scan_mode", sa.Text(), nullable=True))
    op.add_column("integrity_checks", sa.Column("last_scanned_absolute_path", sa.Text(), nullable=True))
    op.add_column("integrity_checks", sa.Column("last_scanned_size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("integrity_checks", sa.Column("last_scanned_mtime_ns", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("integrity_checks", "last_scanned_mtime_ns")
    op.drop_column("integrity_checks", "last_scanned_size_bytes")
    op.drop_column("integrity_checks", "last_scanned_absolute_path")
    op.drop_column("integrity_checks", "last_completed_scan_mode")
