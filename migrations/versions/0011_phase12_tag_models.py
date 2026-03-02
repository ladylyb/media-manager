"""phase 12 tag and canonical_tag models

Revision ID: 0011_phase12_tag_models
Revises: 0010_mv_canonical_metadata
Create Date: 2026-03-02 18:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0011_phase12_tag_models"
down_revision = "0010_mv_canonical_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_tags_name_nonempty"),
        sa.CheckConstraint(
            "length(trim(normalized_name)) > 0",
            name="ck_tags_normalized_name_nonempty",
        ),
        sa.UniqueConstraint("normalized_name", name="uq_tags_normalized_name"),
    )

    op.create_table(
        "canonical_tags",
        sa.Column("canonical_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("enrichment_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "source IN ('ai','manual','import','system')",
            name="ck_canonical_tags_source",
        ),
        sa.CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 1.0",
            name="ck_canonical_tags_confidence_range",
        ),
        sa.CheckConstraint(
            "enrichment_version > 0",
            name="ck_canonical_tags_enrichment_version_positive",
        ),
        sa.ForeignKeyConstraint(["canonical_id"], ["file_contents.content_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "canonical_id",
            "tag_id",
            "source",
            name="uq_canonical_tags_canonical_tag_source",
        ),
    )
    op.create_index("idx_canonical_tags_canonical_id", "canonical_tags", ["canonical_id"])
    op.create_index("idx_canonical_tags_tag_id", "canonical_tags", ["tag_id"])


def downgrade() -> None:
    op.drop_index("idx_canonical_tags_tag_id", table_name="canonical_tags")
    op.drop_index("idx_canonical_tags_canonical_id", table_name="canonical_tags")
    op.drop_table("canonical_tags")
    op.drop_table("tags")
