"""backfill duplicate bin item fields

Revision ID: 0031
Revises: 0030
Create Date: 2026-04-02 00:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def backfill_duplicate_bin_item_fields(connection: sa.engine.Connection) -> None:
    connection.execute(
        sa.text(
            """
            UPDATE duplicate_reclaim_items
            SET
                planned_bin_path = CASE
                    WHEN item_status = 'PENDING' THEN archive_path
                    WHEN item_status IN ('RECYCLED', 'RESTORED') THEN NULL
                    WHEN item_status = 'ARCHIVED' THEN planned_bin_path
                    ELSE NULL
                END,
                bin_path = CASE
                    WHEN item_status = 'ARCHIVED' THEN COALESCE(bin_path, archive_path)
                    WHEN item_status = 'RECYCLED' THEN COALESCE(recycle_path, archive_path)
                    ELSE NULL
                END,
                bin_entered_at = CASE
                    WHEN item_status IN ('ARCHIVED', 'RECYCLED', 'RESTORED') THEN COALESCE(bin_entered_at, reclaimed_at)
                    ELSE NULL
                END,
                restore_expires_at = COALESCE(restore_expires_at, expires_at),
                bin_state = CASE
                    WHEN item_status = 'PENDING' THEN 'PENDING_MOVE'
                    WHEN item_status IN ('ARCHIVED', 'RECYCLED') THEN 'IN_BIN'
                    WHEN item_status = 'RESTORED' THEN 'RESTORED'
                    ELSE bin_state
                END
            WHERE
                (
                    item_status = 'PENDING'
                    AND (
                        planned_bin_path IS NULL
                        OR planned_bin_path != archive_path
                        OR bin_path IS NOT NULL
                        OR bin_entered_at IS NOT NULL
                        OR restore_expires_at IS NULL
                        OR restore_expires_at != expires_at
                        OR bin_state IS NULL
                        OR bin_state != 'PENDING_MOVE'
                    )
                )
                OR (
                    item_status = 'ARCHIVED'
                    AND (
                        bin_path IS NULL
                        OR bin_entered_at IS NULL
                        OR restore_expires_at IS NULL
                        OR bin_state IS NULL
                        OR bin_state != 'IN_BIN'
                    )
                )
                OR (
                    item_status = 'RECYCLED'
                    AND (
                        planned_bin_path IS NOT NULL
                        OR bin_path IS NULL
                        OR bin_path != COALESCE(recycle_path, archive_path)
                        OR bin_entered_at IS NULL
                        OR restore_expires_at IS NULL
                        OR bin_state IS NULL
                        OR bin_state != 'IN_BIN'
                    )
                )
                OR (
                    item_status = 'RESTORED'
                    AND (
                        planned_bin_path IS NOT NULL
                        OR bin_path IS NOT NULL
                        OR bin_entered_at IS NULL
                        OR restore_expires_at IS NULL
                        OR bin_state IS NULL
                        OR bin_state != 'RESTORED'
                    )
                )
            """
        )
    )


def upgrade() -> None:
    backfill_duplicate_bin_item_fields(op.get_bind())


def downgrade() -> None:
    # Phase 3 is a historical backfill only. Reversing it would be operationally lossy and would
    # also risk clobbering Phase 2 dual-written rows, so downgrade is intentionally a no-op.
    pass
