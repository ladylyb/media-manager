"""add phase 3 reclaim item and quarantine records

Revision ID: 0025
Revises: 0024
Create Date: 2026-03-25 00:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE operation_run_type ADD VALUE IF NOT EXISTS 'INTEGRITY_QUARANTINE'")
    op.execute("ALTER TYPE operation_run_type ADD VALUE IF NOT EXISTS 'INTEGRITY_RESTORE'")
    op.execute("ALTER TYPE operation_run_type ADD VALUE IF NOT EXISTS 'DUPLICATE_RECLAIM_EXECUTE'")
    op.execute("ALTER TYPE operation_run_type ADD VALUE IF NOT EXISTS 'DUPLICATE_RECLAIM_RESTORE'")

    op.create_table(
        "duplicate_reclaim_items",
        sa.Column("file_instance_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_path", sa.Text(), nullable=False),
        sa.Column("archive_path", sa.Text(), nullable=False),
        sa.Column("item_status", sa.Text(), nullable=False),
        sa.Column("reclaimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("item_status IN ('PENDING', 'ARCHIVED', 'RESTORED')", name="ck_duplicate_reclaim_items_status"),
        sa.ForeignKeyConstraint(["file_instance_id"], ["file_instances.file_instance_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["content_id"], ["file_contents.content_id"], ondelete="CASCADE"),
    )
    op.create_index("idx_duplicate_reclaim_items_content_id", "duplicate_reclaim_items", ["content_id"], unique=False)
    op.create_index("idx_duplicate_reclaim_items_status", "duplicate_reclaim_items", ["item_status"], unique=False)

    op.create_table(
        "integrity_quarantine_records",
        sa.Column("file_instance_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("check_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("original_path", sa.Text(), nullable=False),
        sa.Column("quarantine_path", sa.Text(), nullable=False),
        sa.Column("quarantine_status", sa.Text(), nullable=False),
        sa.Column("quarantined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "quarantine_status IN ('PENDING', 'QUARANTINED', 'RESTORED')",
            name="ck_integrity_quarantine_records_status",
        ),
        sa.ForeignKeyConstraint(["file_instance_id"], ["file_instances.file_instance_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["check_id"], ["integrity_checks.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_integrity_quarantine_records_status", "integrity_quarantine_records", ["quarantine_status"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_integrity_quarantine_records_status", table_name="integrity_quarantine_records")
    op.drop_table("integrity_quarantine_records")

    op.drop_index("idx_duplicate_reclaim_items_status", table_name="duplicate_reclaim_items")
    op.drop_index("idx_duplicate_reclaim_items_content_id", table_name="duplicate_reclaim_items")
    op.drop_table("duplicate_reclaim_items")
