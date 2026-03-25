"""add recycle bin soft delete tracking

Revision ID: 0026
Revises: 0025
Create Date: 2026-03-25 01:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE operation_run_type ADD VALUE IF NOT EXISTS 'RETENTION_RECYCLE'")

    op.add_column("duplicate_reclaim_items", sa.Column("recycle_path", sa.Text(), nullable=True))
    op.add_column("duplicate_reclaim_items", sa.Column("recycled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("duplicate_reclaim_items", sa.Column("purge_after_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint("ck_duplicate_reclaim_items_status", "duplicate_reclaim_items", type_="check")
    op.create_check_constraint(
        "ck_duplicate_reclaim_items_status",
        "duplicate_reclaim_items",
        "item_status IN ('PENDING', 'ARCHIVED', 'RESTORED', 'RECYCLED')",
    )

    op.add_column("integrity_quarantine_records", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("integrity_quarantine_records", sa.Column("recycle_path", sa.Text(), nullable=True))
    op.add_column("integrity_quarantine_records", sa.Column("recycled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("integrity_quarantine_records", sa.Column("purge_after_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint("ck_integrity_quarantine_records_status", "integrity_quarantine_records", type_="check")
    op.create_check_constraint(
        "ck_integrity_quarantine_records_status",
        "integrity_quarantine_records",
        "quarantine_status IN ('PENDING', 'QUARANTINED', 'RESTORED', 'RECYCLED')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_integrity_quarantine_records_status", "integrity_quarantine_records", type_="check")
    op.create_check_constraint(
        "ck_integrity_quarantine_records_status",
        "integrity_quarantine_records",
        "quarantine_status IN ('PENDING', 'QUARANTINED', 'RESTORED')",
    )
    op.drop_column("integrity_quarantine_records", "purge_after_at")
    op.drop_column("integrity_quarantine_records", "recycled_at")
    op.drop_column("integrity_quarantine_records", "recycle_path")
    op.drop_column("integrity_quarantine_records", "expires_at")

    op.drop_constraint("ck_duplicate_reclaim_items_status", "duplicate_reclaim_items", type_="check")
    op.create_check_constraint(
        "ck_duplicate_reclaim_items_status",
        "duplicate_reclaim_items",
        "item_status IN ('PENDING', 'ARCHIVED', 'RESTORED')",
    )
    op.drop_column("duplicate_reclaim_items", "purge_after_at")
    op.drop_column("duplicate_reclaim_items", "recycled_at")
    op.drop_column("duplicate_reclaim_items", "recycle_path")
