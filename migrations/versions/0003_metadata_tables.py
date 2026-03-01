"""add metadata code/decode tables for pre-extracted planning metadata

Revision ID: 0003_metadata_tables
Revises: 0002_planning_tables
Create Date: 2026-02-28 14:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0003_metadata_tables"
down_revision = "0002_planning_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metadata_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("code_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("code_type", name="uq_metadata_codes_code_type"),
    )

    op.create_table(
        "media_metadata",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("file_hash", sa.Text(), nullable=False),
        sa.Column("code_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decode_value", sa.Text(), nullable=False),
        sa.Column(
            "extracted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["file_hash"], ["content_objects.hash"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["code_id"], ["metadata_codes.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("file_hash", "code_id", name="uq_media_metadata_hash_code"),
    )

    op.create_index("idx_media_metadata_file_hash", "media_metadata", ["file_hash"])
    op.create_index("idx_media_metadata_code_id", "media_metadata", ["code_id"])


def downgrade() -> None:
    op.drop_index("idx_media_metadata_code_id", table_name="media_metadata")
    op.drop_index("idx_media_metadata_file_hash", table_name="media_metadata")
    op.drop_table("media_metadata")
    op.drop_table("metadata_codes")
