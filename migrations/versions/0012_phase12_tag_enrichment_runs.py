"""phase 12 module 2 tag enrichment runs and item facts

Revision ID: 0012_phase12_tag_enrichment_runs
Revises: 0011_phase12_tag_models
Create Date: 2026-03-02 19:20:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0012_phase12_tag_enrichment_runs"
down_revision = "0011_phase12_tag_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tag_enrichment_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("target_canonical_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("batch_size", sa.Integer(), nullable=False),
        sa.Column("number_of_items_processed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("average_confidence", sa.Float(), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("failed_items", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["target_canonical_id"],
            ["file_contents.content_id"],
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("scope IN ('ALL','SINGLE')", name="ck_tag_enrichment_runs_scope"),
        sa.CheckConstraint(
            "source IN ('ai','manual','import','system')",
            name="ck_tag_enrichment_runs_source",
        ),
        sa.CheckConstraint("batch_size > 0", name="ck_tag_enrichment_runs_batch_size_positive"),
        sa.CheckConstraint(
            "status IN ('STARTED','COMPLETED','COMPLETED_WITH_ERRORS','FAILED')",
            name="ck_tag_enrichment_runs_status",
        ),
        sa.CheckConstraint(
            "number_of_items_processed >= 0",
            name="ck_tag_enrichment_runs_items_processed_nonnegative",
        ),
        sa.CheckConstraint(
            "failed_items >= 0",
            name="ck_tag_enrichment_runs_failed_items_nonnegative",
        ),
        sa.CheckConstraint("duration_ms >= 0", name="ck_tag_enrichment_runs_duration_ms_nonnegative"),
    )
    op.create_index("idx_tag_enrichment_runs_started_at", "tag_enrichment_runs", ["started_at"])
    op.create_index("idx_tag_enrichment_runs_status", "tag_enrichment_runs", ["status"])

    op.create_table(
        "tag_enrichment_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("tags_emitted_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("average_confidence", sa.Float(), nullable=True),
        sa.Column("previous_version", sa.Integer(), nullable=True),
        sa.Column("new_version", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["tag_enrichment_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["canonical_id"], ["file_contents.content_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "sequence_no", name="uq_tag_enrichment_items_run_sequence"),
        sa.UniqueConstraint("run_id", "canonical_id", name="uq_tag_enrichment_items_run_canonical"),
        sa.CheckConstraint(
            "result IN ('UNCHANGED','UPDATED','FAILED','SKIPPED')",
            name="ck_tag_enrichment_items_result",
        ),
        sa.CheckConstraint(
            "tags_emitted_count >= 0",
            name="ck_tag_enrichment_items_tags_emitted_count_nonnegative",
        ),
        sa.CheckConstraint("duration_ms >= 0", name="ck_tag_enrichment_items_duration_ms_nonnegative"),
    )
    op.create_index("idx_tag_enrichment_items_run_id", "tag_enrichment_items", ["run_id"])
    op.create_index("idx_tag_enrichment_items_canonical_id", "tag_enrichment_items", ["canonical_id"])


def downgrade() -> None:
    op.drop_index("idx_tag_enrichment_items_canonical_id", table_name="tag_enrichment_items")
    op.drop_index("idx_tag_enrichment_items_run_id", table_name="tag_enrichment_items")
    op.drop_table("tag_enrichment_items")

    op.drop_index("idx_tag_enrichment_runs_status", table_name="tag_enrichment_runs")
    op.drop_index("idx_tag_enrichment_runs_started_at", table_name="tag_enrichment_runs")
    op.drop_table("tag_enrichment_runs")
