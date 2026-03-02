"""phase 12 module 6 enrichment audit metadata additions

Revision ID: 0014_phase12_enrich_audit
Revises: 0013_phase12_search_indexes
Create Date: 2026-03-02 22:40:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0014_phase12_enrich_audit"
down_revision = "0013_phase12_search_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tag_enrichment_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute("UPDATE tag_enrichment_runs SET run_id = id WHERE run_id IS NULL")
    op.alter_column("tag_enrichment_runs", "run_id", nullable=False)
    op.create_unique_constraint(
        "uq_tag_enrichment_runs_run_id",
        "tag_enrichment_runs",
        ["run_id"],
    )
    op.create_index("idx_tag_enrichment_runs_run_id", "tag_enrichment_runs", ["run_id"])

    op.add_column(
        "tag_enrichment_items",
        sa.Column("previous_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "tag_enrichment_items",
        sa.Column("previous_confidence", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tag_enrichment_items", "previous_confidence")
    op.drop_column("tag_enrichment_items", "previous_tags")

    op.drop_index("idx_tag_enrichment_runs_run_id", table_name="tag_enrichment_runs")
    op.drop_constraint("uq_tag_enrichment_runs_run_id", "tag_enrichment_runs", type_="unique")
    op.drop_column("tag_enrichment_runs", "run_id")
