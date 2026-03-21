"""add planned action routing fields

Revision ID: 0020_planned_action_routing_fields
Revises: 0019_admin_observability_benchmarks
Create Date: 2026-03-21 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0020_planned_action_routing_fields"
down_revision = "0019_admin_observability_benchmarks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "planned_actions",
        sa.Column("role", sa.Text(), nullable=False, server_default="CANONICAL"),
    )
    op.add_column(
        "planned_actions",
        sa.Column("duplicate_index", sa.Integer(), nullable=True),
    )
    op.execute("ALTER TABLE planned_actions ALTER COLUMN role DROP DEFAULT")


def downgrade() -> None:
    op.drop_column("planned_actions", "duplicate_index")
    op.drop_column("planned_actions", "role")
