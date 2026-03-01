"""phase 7 identity split: file_contents/file_instances and metadata content fk

Revision ID: 0004_identity_ingestion_split
Revises: 0003_metadata_tables
Create Date: 2026-02-28 21:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0004_identity_ingestion_split"
down_revision = "0003_metadata_tables"
branch_labels = None
depends_on = None


def _hash_to_uuid_expr(column_name: str) -> str:
    return (
        f"(substr({column_name},1,8)||'-'||substr({column_name},9,4)||'-'||"
        f"substr({column_name},13,4)||'-'||substr({column_name},17,4)||'-'||"
        f"substr({column_name},21,12))::uuid"
    )


def upgrade() -> None:
    op.create_table(
        "file_contents",
        sa.Column("content_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("sha256_hash", sa.Text(), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("canonical_file_instance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("sha256_hash", name="uq_file_contents_sha256_hash"),
    )
    op.create_index("idx_file_contents_sha256_hash", "file_contents", ["sha256_hash"])
    op.create_index(
        "idx_file_contents_canonical_instance",
        "file_contents",
        ["canonical_file_instance_id"],
    )

    op.create_table(
        "file_instances",
        sa.Column("file_instance_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("absolute_path", sa.Text(), nullable=False),
        sa.Column("filesystem_id", sa.Text(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("status IN ('ACTIVE','DELETED')", name="ck_file_instances_status"),
        sa.ForeignKeyConstraint(["content_id"], ["file_contents.content_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingestion_run_id"], ["runs.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("absolute_path", name="uq_file_instances_absolute_path"),
    )
    op.create_index("idx_file_instances_content_id", "file_instances", ["content_id"])
    op.create_index("idx_file_instances_absolute_path", "file_instances", ["absolute_path"])
    op.create_index("idx_file_instances_status", "file_instances", ["status"])

    op.create_foreign_key(
        "fk_file_contents_canonical_instance",
        "file_contents",
        "file_instances",
        ["canonical_file_instance_id"],
        ["file_instance_id"],
        ondelete="SET NULL",
    )

    # Backfill file_contents from distinct legacy hashes.
    op.execute(
        f"""
        INSERT INTO file_contents (content_id, sha256_hash, first_seen_at)
        SELECT {_hash_to_uuid_expr('co.hash')}, co.hash, co.created_at
        FROM content_objects co
        ON CONFLICT (sha256_hash) DO NOTHING;
        """
    )

    # Backfill file_instances using legacy files and preserve file UUID as instance UUID.
    op.execute(
        """
        INSERT INTO file_instances (
            file_instance_id, content_id, absolute_path, first_seen_at, last_seen_at, status
        )
        SELECT
            f.id,
            fc.content_id,
            f.path,
            f.created_at,
            f.created_at,
            'ACTIVE'
        FROM files f
        JOIN file_contents fc ON fc.sha256_hash = f.hash
        ON CONFLICT (absolute_path) DO UPDATE
        SET
            content_id = EXCLUDED.content_id,
            last_seen_at = EXCLUDED.last_seen_at,
            status = 'ACTIVE';
        """
    )

    op.execute(
        """
        WITH canonical AS (
            SELECT DISTINCT ON (fi.content_id)
                fi.content_id,
                fi.file_instance_id
            FROM file_instances fi
            ORDER BY fi.content_id, fi.first_seen_at ASC, fi.file_instance_id ASC
        )
        UPDATE file_contents fc
        SET canonical_file_instance_id = canonical.file_instance_id
        FROM canonical
        WHERE fc.content_id = canonical.content_id
          AND fc.canonical_file_instance_id IS NULL;
        """
    )

    # Remap planned_actions FK from legacy files -> file_instances (same UUID values after backfill).
    op.execute("ALTER TABLE planned_actions DROP CONSTRAINT IF EXISTS planned_actions_file_id_fkey")
    op.create_foreign_key(
        "planned_actions_file_id_fkey",
        "planned_actions",
        "file_instances",
        ["file_id"],
        ["file_instance_id"],
        ondelete="RESTRICT",
    )

    # Shift metadata binding from hash to content_id.
    op.add_column("media_metadata", sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(
        """
        UPDATE media_metadata mm
        SET content_id = fc.content_id
        FROM file_contents fc
        WHERE mm.file_hash = fc.sha256_hash;
        """
    )
    op.create_index("idx_media_metadata_content_id", "media_metadata", ["content_id"])
    op.create_foreign_key(
        "media_metadata_content_id_fkey",
        "media_metadata",
        "file_contents",
        ["content_id"],
        ["content_id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint("uq_media_metadata_hash_code", "media_metadata", type_="unique")
    op.create_unique_constraint("uq_media_metadata_content_code", "media_metadata", ["content_id", "code_id"])
    op.alter_column("media_metadata", "content_id", nullable=False)

    op.drop_index("idx_media_metadata_file_hash", table_name="media_metadata")
    op.execute("ALTER TABLE media_metadata DROP CONSTRAINT IF EXISTS media_metadata_file_hash_fkey")
    op.drop_column("media_metadata", "file_hash")


def downgrade() -> None:
    op.add_column("media_metadata", sa.Column("file_hash", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE media_metadata mm
        SET file_hash = fc.sha256_hash
        FROM file_contents fc
        WHERE mm.content_id = fc.content_id;
        """
    )
    op.create_index("idx_media_metadata_file_hash", "media_metadata", ["file_hash"])
    op.create_foreign_key(
        "media_metadata_file_hash_fkey",
        "media_metadata",
        "content_objects",
        ["file_hash"],
        ["hash"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("uq_media_metadata_content_code", "media_metadata", type_="unique")
    op.create_unique_constraint("uq_media_metadata_hash_code", "media_metadata", ["file_hash", "code_id"])
    op.execute("ALTER TABLE media_metadata DROP CONSTRAINT IF EXISTS media_metadata_content_id_fkey")
    op.drop_index("idx_media_metadata_content_id", table_name="media_metadata")
    op.drop_column("media_metadata", "content_id")
    op.alter_column("media_metadata", "file_hash", nullable=False)

    op.execute("ALTER TABLE planned_actions DROP CONSTRAINT IF EXISTS planned_actions_file_id_fkey")
    op.create_foreign_key(
        "planned_actions_file_id_fkey",
        "planned_actions",
        "files",
        ["file_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.execute("ALTER TABLE file_contents DROP CONSTRAINT IF EXISTS fk_file_contents_canonical_instance")
    op.drop_index("idx_file_instances_status", table_name="file_instances")
    op.drop_index("idx_file_instances_absolute_path", table_name="file_instances")
    op.drop_index("idx_file_instances_content_id", table_name="file_instances")
    op.drop_table("file_instances")

    op.drop_index("idx_file_contents_canonical_instance", table_name="file_contents")
    op.drop_index("idx_file_contents_sha256_hash", table_name="file_contents")
    op.drop_table("file_contents")
