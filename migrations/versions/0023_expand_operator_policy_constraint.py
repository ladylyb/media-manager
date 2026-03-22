"""expand operator policy constraint for exif filename fallback

Revision ID: 0023
Revises: 0022
Create Date: 2026-03-22 00:05:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_operator_policy_settings_selected_policy", "operator_policy_settings", type_="check")
    op.create_check_constraint(
        "ck_operator_policy_settings_selected_policy",
        "operator_policy_settings",
        "selected_policy IN ('FIRST_SEEN','PREFER_ROOT','SHORTEST_PATH','EXIF_FILENAME_FALLBACK')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_operator_policy_settings_selected_policy", "operator_policy_settings", type_="check")
    op.create_check_constraint(
        "ck_operator_policy_settings_selected_policy",
        "operator_policy_settings",
        "selected_policy IN ('FIRST_SEEN','PREFER_ROOT','SHORTEST_PATH','EXIF_FILENAME_FALLBACK')",
    )
