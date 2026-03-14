"""fix legacy_raw tmp deletion audit file_id type to text

Revision ID: 0009_legacy_raw_tmp_file_id_text
Revises: 0008_legacy_import_schemas
Create Date: 2026-03-02 08:12:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0009_legacy_raw_tmp_file_id_text"
down_revision = "0008_legacy_import_schemas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "_tmp_deletion_audit_import",
        "file_id",
        schema="legacy_raw",
        existing_type=sa.BigInteger(),
        type_=sa.Text(),
        postgresql_using="file_id::text",
    )


def downgrade() -> None:
    op.alter_column(
        "_tmp_deletion_audit_import",
        "file_id",
        schema="legacy_raw",
        existing_type=sa.Text(),
        type_=sa.BigInteger(),
        postgresql_using="NULLIF(file_id, '')::bigint",
    )
