"""phase 12 module 4 search indexes for discovery query layer

Revision ID: 0013_phase12_search_indexes
Revises: 0012_phase12_tag_enrichment_runs
Create Date: 2026-03-02 21:05:00
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0013_phase12_search_indexes"
down_revision = "0012_phase12_tag_enrichment_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.execute("CREATE INDEX IF NOT EXISTS idx_tags_normalized_name ON tags (normalized_name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_canonical_tags_tag_id ON canonical_tags (tag_id)")

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_canonical_tags_tag_canonical_confidence
        ON canonical_tags (tag_id, canonical_id, confidence_score DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_canonical_tags_canonical_confidence
        ON canonical_tags (canonical_id, confidence_score DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_file_contents_first_seen_content
        ON file_contents (first_seen_at DESC, content_id ASC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tags_normalized_name_trgm
        ON tags USING GIN (normalized_name gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tags_normalized_name_trgm")
    op.execute("DROP INDEX IF EXISTS idx_file_contents_first_seen_content")
    op.execute("DROP INDEX IF EXISTS idx_canonical_tags_canonical_confidence")
    op.execute("DROP INDEX IF EXISTS idx_canonical_tags_tag_canonical_confidence")
    op.execute("DROP INDEX IF EXISTS idx_tags_normalized_name")
