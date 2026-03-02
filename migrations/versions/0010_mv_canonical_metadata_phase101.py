"""phase 10.1 materialized canonical metadata view

Revision ID: 0010_mv_canonical_metadata
Revises: 0009_legacy_raw_tmp_file_id_text
Create Date: 2026-03-02 13:10:00
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0010_mv_canonical_metadata"
down_revision = "0009_legacy_raw_tmp_file_id_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Deterministic latest-assignment selection contract:
    # - Primary ordering is assigned_at DESC (latest assignment timestamp).
    # - Secondary ordering is assignment_id DESC to guarantee a total order when
    #   assigned_at ties exist for the same content_id.
    # - assignment_id is the canonical_assignments primary key and therefore
    #   unique, which prevents tie ambiguity in the ORDER BY tuple.
    # Semantic correctness of "latest canonical assignment" depends on this
    # ordering remaining aligned with base-table read logic.
    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_canonical_metadata AS
        WITH latest AS (
            SELECT
                ca.content_id,
                ca.canonical_instance_id,
                ca.assigned_at,
                ca.assignment_id,
                ROW_NUMBER() OVER (
                    PARTITION BY ca.content_id
                    ORDER BY ca.assigned_at DESC, ca.assignment_id DESC
                ) AS rn
            FROM canonical_assignments ca
        )
        SELECT
            l.content_id,
            l.canonical_instance_id,
            fc.sha256_hash AS hash_identity,
            fi.absolute_path AS file_path,
            legacy.size_bytes AS file_size,
            l.assigned_at AS created_at
        FROM latest l
        JOIN file_contents fc
          ON fc.content_id = l.content_id
        JOIN file_instances fi
          ON fi.file_instance_id = l.canonical_instance_id
        LEFT JOIN files legacy
          ON legacy.path = fi.absolute_path
        WHERE l.rn = 1
        WITH NO DATA
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_canonical_metadata_content_id_uq
        ON mv_canonical_metadata (content_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mv_canonical_metadata_canonical_instance_id
        ON mv_canonical_metadata (canonical_instance_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_mv_canonical_metadata_canonical_instance_id")
    op.execute("DROP INDEX IF EXISTS idx_mv_canonical_metadata_content_id_uq")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_canonical_metadata")
