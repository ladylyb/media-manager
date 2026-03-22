"""add naming strategy and run owner context inputs

Revision ID: 0022
Revises: 0021
Create Date: 2026-03-22 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


_NAMING_STRATEGY = sa.Enum(
    "SHARED_CANONICAL_NAME",
    "DUPLICATE_OWNS_DATE_STANDARDIZED",
    "PRESERVE_DUPLICATE_ORIGINAL_NAME",
    name="naming_strategy",
)


def upgrade() -> None:
    bind = op.get_bind()
    _NAMING_STRATEGY.create(bind, checkfirst=True)
    op.drop_constraint("ck_operator_policy_settings_selected_policy", "operator_policy_settings", type_="check")
    op.create_check_constraint(
        "ck_operator_policy_settings_selected_policy",
        "operator_policy_settings",
        "selected_policy IN ('FIRST_SEEN','PREFER_ROOT','SHORTEST_PATH','EXIF_FILENAME_FALLBACK')",
    )
    op.add_column(
        "operator_policy_settings",
        sa.Column(
            "naming_strategy",
            _NAMING_STRATEGY,
            nullable=False,
            server_default="SHARED_CANONICAL_NAME",
        ),
    )
    op.add_column("runs", sa.Column("owner", sa.Text(), nullable=False, server_default="LL"))
    op.add_column("runs", sa.Column("context", sa.Text(), nullable=False, server_default="General"))
    op.add_column(
        "runs",
        sa.Column(
            "naming_strategy",
            _NAMING_STRATEGY,
            nullable=False,
            server_default="SHARED_CANONICAL_NAME",
        ),
    )
    op.add_column(
        "runs",
        sa.Column(
            "owner_context_override_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_constraint("ck_operator_policy_settings_selected_policy", "operator_policy_settings", type_="check")
    op.create_check_constraint(
        "ck_operator_policy_settings_selected_policy",
        "operator_policy_settings",
        "selected_policy IN ('FIRST_SEEN','PREFER_ROOT','SHORTEST_PATH')",
    )
    op.drop_column("runs", "owner_context_override_confirmed")
    op.drop_column("runs", "naming_strategy")
    op.drop_column("runs", "context")
    op.drop_column("runs", "owner")
    op.drop_column("operator_policy_settings", "naming_strategy")
    bind = op.get_bind()
    _NAMING_STRATEGY.drop(bind, checkfirst=True)
