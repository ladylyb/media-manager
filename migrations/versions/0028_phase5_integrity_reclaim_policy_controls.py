"""add phase 5 integrity and reclaim policy controls

Revision ID: 0028
Revises: 0027
Create Date: 2026-03-28 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "operator_policy_settings",
        sa.Column("integrity_scan_default_mode", sa.Text(), nullable=False, server_default="FAST"),
    )
    op.add_column(
        "operator_policy_settings",
        sa.Column("integrity_issue_min_confidence", sa.Float(), nullable=False, server_default="0.9"),
    )
    op.add_column(
        "operator_policy_settings",
        sa.Column("duplicate_reclaim_default_retention_days", sa.Integer(), nullable=False, server_default="14"),
    )
    op.add_column(
        "operator_policy_settings",
        sa.Column("integrity_quarantine_retention_days", sa.Integer(), nullable=False, server_default="14"),
    )
    op.add_column(
        "operator_policy_settings",
        sa.Column("recycle_purge_days", sa.Integer(), nullable=False, server_default="30"),
    )
    op.add_column(
        "operator_policy_settings",
        sa.Column(
            "recycle_bin_root",
            sa.Text(),
            nullable=False,
            server_default="/tmp/media-manager/recycle-bin",
        ),
    )
    op.add_column(
        "operator_policy_settings",
        sa.Column(
            "duplicate_reclaim_archive_root",
            sa.Text(),
            nullable=False,
            server_default="/tmp/media-manager/reclaim",
        ),
    )
    op.add_column(
        "operator_policy_settings",
        sa.Column(
            "integrity_quarantine_root",
            sa.Text(),
            nullable=False,
            server_default="/tmp/media-manager/quarantine",
        ),
    )
    op.add_column(
        "operator_policy_settings",
        sa.Column("integrity_notify_on_high_confidence", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "operator_policy_settings",
        sa.Column("duplicate_reclaim_notify_on_reviewed_safe", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "operator_policy_settings",
        sa.Column("automation_mode", sa.Text(), nullable=False, server_default="NOTIFY_ONLY"),
    )

    op.create_check_constraint(
        "ck_op_policy_integrity_scan_mode",
        "operator_policy_settings",
        "integrity_scan_default_mode IN ('FAST','DEEP')",
    )
    op.create_check_constraint(
        "ck_op_policy_integrity_confidence",
        "operator_policy_settings",
        "integrity_issue_min_confidence >= 0.0 AND integrity_issue_min_confidence <= 1.0",
    )
    op.create_check_constraint(
        "ck_op_policy_reclaim_retention_days",
        "operator_policy_settings",
        "duplicate_reclaim_default_retention_days > 0",
    )
    op.create_check_constraint(
        "ck_op_policy_quarantine_retention_days",
        "operator_policy_settings",
        "integrity_quarantine_retention_days > 0",
    )
    op.create_check_constraint(
        "ck_op_policy_recycle_purge_days",
        "operator_policy_settings",
        "recycle_purge_days > 0",
    )
    op.create_check_constraint(
        "ck_op_policy_automation_mode",
        "operator_policy_settings",
        "automation_mode IN ('NOTIFY_ONLY')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_op_policy_automation_mode", "operator_policy_settings", type_="check")
    op.drop_constraint(
        "ck_op_policy_recycle_purge_days",
        "operator_policy_settings",
        type_="check",
    )
    op.drop_constraint(
        "ck_op_policy_quarantine_retention_days",
        "operator_policy_settings",
        type_="check",
    )
    op.drop_constraint(
        "ck_op_policy_reclaim_retention_days",
        "operator_policy_settings",
        type_="check",
    )
    op.drop_constraint(
        "ck_op_policy_integrity_confidence",
        "operator_policy_settings",
        type_="check",
    )
    op.drop_constraint(
        "ck_op_policy_integrity_scan_mode",
        "operator_policy_settings",
        type_="check",
    )
    op.drop_column("operator_policy_settings", "automation_mode")
    op.drop_column("operator_policy_settings", "duplicate_reclaim_notify_on_reviewed_safe")
    op.drop_column("operator_policy_settings", "integrity_notify_on_high_confidence")
    op.drop_column("operator_policy_settings", "integrity_quarantine_root")
    op.drop_column("operator_policy_settings", "duplicate_reclaim_archive_root")
    op.drop_column("operator_policy_settings", "recycle_bin_root")
    op.drop_column("operator_policy_settings", "recycle_purge_days")
    op.drop_column("operator_policy_settings", "integrity_quarantine_retention_days")
    op.drop_column("operator_policy_settings", "duplicate_reclaim_default_retention_days")
    op.drop_column("operator_policy_settings", "integrity_issue_min_confidence")
    op.drop_column("operator_policy_settings", "integrity_scan_default_mode")
