"""phase 10 operator policy settings table

Revision ID: 0007_operator_policy_settings
Revises: 0006_phase81_canonical
Create Date: 2026-03-01 01:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0007_operator_policy_settings"
down_revision = "0006_phase81_canonical"
branch_labels = None
depends_on = None


_SUPPORTED_POLICIES = "'FIRST_SEEN','PREFER_ROOT','SHORTEST_PATH'"


def upgrade() -> None:
    op.create_table(
        "operator_policy_settings",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("selected_policy", sa.Text(), nullable=False),
        sa.Column("preferred_roots_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("recanonicalization_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("id = 1", name="ck_operator_policy_settings_singleton"),
        sa.CheckConstraint(
            f"selected_policy IN ({_SUPPORTED_POLICIES})",
            name="ck_operator_policy_settings_selected_policy",
        ),
        sa.CheckConstraint("length(trim(preferred_roots_json)) > 0", name="ck_operator_policy_settings_roots_nonempty"),
    )


def downgrade() -> None:
    op.drop_table("operator_policy_settings")
