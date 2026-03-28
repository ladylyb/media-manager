"""add integrity review tables and duplicate reclaim state

Revision ID: 0024
Revises: 0023
Create Date: 2026-03-25 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE operation_run_type ADD VALUE IF NOT EXISTS 'INTEGRITY_SCAN'")
    op.execute("ALTER TYPE operation_run_type ADD VALUE IF NOT EXISTS 'DUPLICATE_RECLAIM_REVIEW'")

    op.create_table(
        "integrity_check_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("operation_run_id", postgresql.UUID(as_uuid=True), nullable=True, unique=True),
        sa.Column("scan_mode", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("paths", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("scanned_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("issues_found", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("scan_mode IN ('FAST', 'DEEP')", name="ck_integrity_check_runs_mode"),
        sa.CheckConstraint("status IN ('STARTED', 'COMPLETED', 'FAILED')", name="ck_integrity_check_runs_status"),
        sa.ForeignKeyConstraint(["operation_run_id"], ["operation_runs.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "idx_integrity_check_runs_started_at",
        "integrity_check_runs",
        [sa.text("started_at DESC")],
        unique=False,
    )

    op.create_table(
        "integrity_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("file_instance_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("latest_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("readability_ok", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("probe_status", sa.Text(), nullable=True),
        sa.Column("decode_status", sa.Text(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('OK', 'SUSPECT', 'BROKEN')", name="ck_integrity_checks_status"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_integrity_checks_confidence"),
        sa.ForeignKeyConstraint(["file_instance_id"], ["file_instances.file_instance_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["latest_run_id"], ["integrity_check_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_integrity_checks_status", "integrity_checks", ["status"], unique=False)
    op.create_index(
        "idx_integrity_checks_last_checked_at",
        "integrity_checks",
        [sa.text("last_checked_at DESC")],
        unique=False,
    )

    op.create_table(
        "integrity_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("check_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal_type", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["check_id"], ["integrity_checks.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_integrity_signals_check_id", "integrity_signals", ["check_id"], unique=False)
    op.create_index("idx_integrity_signals_signal_type", "integrity_signals", ["signal_type"], unique=False)

    op.create_table(
        "integrity_review_decisions",
        sa.Column("check_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("decision IN ('MARK_OK', 'IGNORE')", name="ck_integrity_review_decisions_decision"),
        sa.ForeignKeyConstraint(["check_id"], ["integrity_checks.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_integrity_review_decisions_reviewed_at",
        "integrity_review_decisions",
        [sa.text("reviewed_at DESC")],
        unique=False,
    )

    op.create_table(
        "duplicate_reclaim_records",
        sa.Column("content_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("reclaim_status", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("archive_path", sa.Text(), nullable=True),
        sa.Column("reclaimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reclaim_status IN ('UNREVIEWED', 'REVIEWED_SAFE_TO_RECLAIM', 'ARCHIVED', 'SCHEDULED_FOR_DELETE', 'RESTORED')",
            name="ck_duplicate_reclaim_records_status",
        ),
        sa.ForeignKeyConstraint(["content_id"], ["file_contents.content_id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_duplicate_reclaim_records_reviewed_at",
        "duplicate_reclaim_records",
        [sa.text("reviewed_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_duplicate_reclaim_records_reviewed_at", table_name="duplicate_reclaim_records")
    op.drop_table("duplicate_reclaim_records")

    op.drop_index("idx_integrity_review_decisions_reviewed_at", table_name="integrity_review_decisions")
    op.drop_table("integrity_review_decisions")

    op.drop_index("idx_integrity_signals_signal_type", table_name="integrity_signals")
    op.drop_index("idx_integrity_signals_check_id", table_name="integrity_signals")
    op.drop_table("integrity_signals")

    op.drop_index("idx_integrity_checks_last_checked_at", table_name="integrity_checks")
    op.drop_index("idx_integrity_checks_status", table_name="integrity_checks")
    op.drop_table("integrity_checks")

    op.drop_index("idx_integrity_check_runs_started_at", table_name="integrity_check_runs")
    op.drop_table("integrity_check_runs")
