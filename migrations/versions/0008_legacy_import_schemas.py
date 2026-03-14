"""create legacy raw and 3nf import schemas

Revision ID: 0008_legacy_import_schemas
Revises: 0007_operator_policy_settings
Create Date: 2026-03-02 08:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0008_legacy_import_schemas"
down_revision = "0007_operator_policy_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS legacy_raw")
    op.execute("CREATE SCHEMA IF NOT EXISTS legacy_3nf")

    # legacy_raw mirror tables
    op.create_table(
        "scans",
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("root_path", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_db_name", sa.Text(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("import_run_id", "id", name="pk_legacy_raw_scans"),
        schema="legacy_raw",
    )

    op.create_table(
        "files",
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("scan_id", sa.BigInteger(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("extension", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("mtime", sa.Float(), nullable=True),
        sa.Column("ctime", sa.Float(), nullable=True),
        sa.Column("hash_partial", sa.Text(), nullable=True),
        sa.Column("hash_full", sa.Text(), nullable=True),
        sa.Column("hash_algo", sa.Text(), nullable=True),
        sa.Column("media_type", sa.Text(), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("codec", sa.Text(), nullable=True),
        sa.Column("bitrate", sa.Integer(), nullable=True),
        sa.Column("exif_datetime", sa.Text(), nullable=True),
        sa.Column("is_hashed", sa.Integer(), nullable=True),
        sa.Column("is_metadata_extracted", sa.Integer(), nullable=True),
        sa.Column("camera_model", sa.Text(), nullable=True),
        sa.Column("orientation", sa.Text(), nullable=True),
        sa.Column("source_db_name", sa.Text(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("import_run_id", "id", name="pk_legacy_raw_files"),
        schema="legacy_raw",
    )

    op.create_table(
        "file_actions",
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("file_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_path", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_db_name", sa.Text(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("import_run_id", "id", name="pk_legacy_raw_file_actions"),
        schema="legacy_raw",
    )

    op.create_table(
        "_file_actions_old",
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("file_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_path", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_db_name", sa.Text(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("import_run_id", "id", name="pk_legacy_raw_file_actions_old"),
        schema="legacy_raw",
    )

    op.create_table(
        "duplicate_candidates",
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("file_id_1", sa.BigInteger(), nullable=False),
        sa.Column("file_id_2", sa.BigInteger(), nullable=False),
        sa.Column("match_type", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=True),
        sa.Column("duplicate_group_id", sa.BigInteger(), nullable=True),
        sa.Column("source_db_name", sa.Text(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("import_run_id", "id", name="pk_legacy_raw_duplicate_candidates"),
        schema="legacy_raw",
    )

    op.create_table(
        "deletion_audit_runs",
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("audit_name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_db_name", sa.Text(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("import_run_id", "id", name="pk_legacy_raw_deletion_audit_runs"),
        schema="legacy_raw",
    )

    op.create_table(
        "deletion_audit_candidates",
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("audit_run_id", sa.BigInteger(), nullable=False),
        sa.Column("reconstructed_name", sa.Text(), nullable=True),
        sa.Column("observed_path", sa.Text(), nullable=False),
        sa.Column("audit_notes", sa.Text(), nullable=True),
        sa.Column("raw_actions_snapshot", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=True),
        sa.Column("source_db_name", sa.Text(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("import_run_id", "id", name="pk_legacy_raw_deletion_audit_candidates"),
        schema="legacy_raw",
    )

    op.create_table(
        "deletion_audit_candidate_files",
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("audit_candidate_id", sa.BigInteger(), nullable=False),
        sa.Column("related_file_id", sa.BigInteger(), nullable=False),
        sa.Column("source_db_name", sa.Text(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("import_run_id", "id", name="pk_legacy_raw_deletion_audit_candidate_files"),
        schema="legacy_raw",
    )

    op.create_table(
        "_tmp_deletion_audit_import",
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legacy_row_no", sa.BigInteger(), nullable=False),
        sa.Column("to_be_deleted_path", sa.Text(), nullable=True),
        sa.Column("reconstructed_filename", sa.Text(), nullable=True),
        sa.Column("found_in_db", sa.Text(), nullable=True),
        sa.Column("file_id", sa.BigInteger(), nullable=True),
        sa.Column("actions", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_db_name", sa.Text(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("import_run_id", "legacy_row_no", name="pk_legacy_raw_tmp_deletion_audit_import"),
        schema="legacy_raw",
    )

    # legacy_3nf operational tables
    op.create_table(
        "import_runs",
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("sqlite_path", sa.Text(), nullable=False),
        sa.Column("source_db_name", sa.Text(), nullable=False),
        sa.Column("source_db_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("source_db_mtime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_db_sha256", sa.Text(), nullable=False),
        sa.Column("raw_counts_json", sa.Text(), nullable=True),
        sa.Column("raw_checksums_json", sa.Text(), nullable=True),
        sa.Column("verification_report_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("raw_loaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("normalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('CREATED','RAW_LOADED','NORMALIZED','VERIFIED','FAILED')",
            name="ck_legacy_import_runs_state",
        ),
        schema="legacy_3nf",
    )

    op.create_table(
        "import_failure_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("context_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["import_run_id"], ["legacy_3nf.import_runs.import_run_id"], ondelete="CASCADE"),
        schema="legacy_3nf",
    )

    op.create_table(
        "scan_batch",
        sa.Column("scan_batch_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legacy_scan_id", sa.BigInteger(), nullable=False),
        sa.Column("root_path", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["import_run_id"], ["legacy_3nf.import_runs.import_run_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("import_run_id", "legacy_scan_id", name="uq_legacy_3nf_scan_batch_run_scan"),
        schema="legacy_3nf",
    )

    op.create_table(
        "content_identity",
        sa.Column("content_identity_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_tier", sa.Text(), nullable=False),
        sa.Column("identity_value", sa.Text(), nullable=False),
        sa.Column("hash_full", sa.Text(), nullable=True),
        sa.Column("hash_algo", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["import_run_id"], ["legacy_3nf.import_runs.import_run_id"], ondelete="CASCADE"),
        sa.CheckConstraint("identity_tier IN ('HASH_FULL','SURROGATE')", name="ck_legacy_3nf_identity_tier"),
        sa.UniqueConstraint(
            "import_run_id",
            "identity_tier",
            "identity_value",
            name="uq_legacy_3nf_content_identity_key",
        ),
        schema="legacy_3nf",
    )

    op.create_table(
        "file_instance",
        sa.Column("file_instance_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legacy_file_id", sa.BigInteger(), nullable=False),
        sa.Column("scan_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("absolute_path", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("extension", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("mtime", sa.Float(), nullable=True),
        sa.Column("ctime", sa.Float(), nullable=True),
        sa.Column("is_hashed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_metadata_extracted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["import_run_id"], ["legacy_3nf.import_runs.import_run_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scan_batch_id"], ["legacy_3nf.scan_batch.scan_batch_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["content_identity_id"],
            ["legacy_3nf.content_identity.content_identity_id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("import_run_id", "legacy_file_id", name="uq_legacy_3nf_file_instance_legacy_file"),
        sa.UniqueConstraint("import_run_id", "absolute_path", name="uq_legacy_3nf_file_instance_abs_path"),
        schema="legacy_3nf",
    )

    op.create_table(
        "media_attributes",
        sa.Column("file_instance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("codec", sa.Text(), nullable=True),
        sa.Column("bitrate", sa.Integer(), nullable=True),
        sa.Column("exif_datetime", sa.Text(), nullable=True),
        sa.Column("camera_model", sa.Text(), nullable=True),
        sa.Column("orientation", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("file_instance_id", name="pk_legacy_3nf_media_attributes"),
        sa.ForeignKeyConstraint(
            ["file_instance_id"],
            ["legacy_3nf.file_instance.file_instance_id"],
            ondelete="CASCADE",
        ),
        schema="legacy_3nf",
    )

    op.create_table(
        "action_event",
        sa.Column("action_event_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legacy_action_id", sa.BigInteger(), nullable=False),
        sa.Column("action_source", sa.Text(), nullable=False),
        sa.Column("file_instance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_path", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("action_source IN ('CURRENT','LEGACY_OLD')", name="ck_legacy_3nf_action_source"),
        sa.ForeignKeyConstraint(["import_run_id"], ["legacy_3nf.import_runs.import_run_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["file_instance_id"],
            ["legacy_3nf.file_instance.file_instance_id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "import_run_id",
            "action_source",
            "legacy_action_id",
            name="uq_legacy_3nf_action_event_source_id",
        ),
        schema="legacy_3nf",
    )

    op.create_table(
        "duplicate_evidence",
        sa.Column("duplicate_evidence_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legacy_duplicate_id", sa.BigInteger(), nullable=False),
        sa.Column("file_instance_1_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_instance_2_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_low_file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_high_file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_type", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("duplicate_group_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["import_run_id"], ["legacy_3nf.import_runs.import_run_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["file_instance_1_id"],
            ["legacy_3nf.file_instance.file_instance_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["file_instance_2_id"],
            ["legacy_3nf.file_instance.file_instance_id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "import_run_id",
            "legacy_duplicate_id",
            name="uq_legacy_3nf_duplicate_evidence_legacy_id",
        ),
        sa.UniqueConstraint(
            "import_run_id",
            "canonical_low_file_id",
            "canonical_high_file_id",
            "match_type",
            name="uq_legacy_3nf_duplicate_evidence_pair",
        ),
        schema="legacy_3nf",
    )

    op.create_table(
        "deletion_audit_run",
        sa.Column("deletion_audit_run_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legacy_audit_run_id", sa.BigInteger(), nullable=False),
        sa.Column("audit_name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["import_run_id"], ["legacy_3nf.import_runs.import_run_id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "import_run_id",
            "legacy_audit_run_id",
            name="uq_legacy_3nf_deletion_audit_run_legacy_id",
        ),
        schema="legacy_3nf",
    )

    op.create_table(
        "deletion_audit_candidate",
        sa.Column("deletion_audit_candidate_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legacy_candidate_id", sa.BigInteger(), nullable=False),
        sa.Column("deletion_audit_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reconstructed_name", sa.Text(), nullable=True),
        sa.Column("observed_path", sa.Text(), nullable=False),
        sa.Column("audit_notes", sa.Text(), nullable=True),
        sa.Column("raw_actions_snapshot", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["import_run_id"], ["legacy_3nf.import_runs.import_run_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["deletion_audit_run_id"],
            ["legacy_3nf.deletion_audit_run.deletion_audit_run_id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "import_run_id",
            "legacy_candidate_id",
            name="uq_legacy_3nf_deletion_audit_candidate_legacy_id",
        ),
        schema="legacy_3nf",
    )

    op.create_table(
        "deletion_audit_candidate_instance",
        sa.Column("deletion_audit_candidate_instance_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legacy_candidate_file_id", sa.BigInteger(), nullable=False),
        sa.Column("deletion_audit_candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_instance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["import_run_id"], ["legacy_3nf.import_runs.import_run_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["deletion_audit_candidate_id"],
            ["legacy_3nf.deletion_audit_candidate.deletion_audit_candidate_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["file_instance_id"],
            ["legacy_3nf.file_instance.file_instance_id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "import_run_id",
            "legacy_candidate_file_id",
            name="uq_legacy_3nf_deletion_audit_candidate_instance_legacy_id",
        ),
        schema="legacy_3nf",
    )

    op.create_table(
        "canonical_candidate",
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_file_instance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("selection_reason", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("import_run_id", "content_identity_id", name="pk_legacy_3nf_canonical_candidate"),
        sa.ForeignKeyConstraint(["import_run_id"], ["legacy_3nf.import_runs.import_run_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["content_identity_id"],
            ["legacy_3nf.content_identity.content_identity_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["canonical_file_instance_id"],
            ["legacy_3nf.file_instance.file_instance_id"],
            ondelete="RESTRICT",
        ),
        schema="legacy_3nf",
    )

    op.create_index("idx_legacy_3nf_scan_batch_import_run", "scan_batch", ["import_run_id"], schema="legacy_3nf")
    op.create_index("idx_legacy_3nf_content_identity_import_run", "content_identity", ["import_run_id"], schema="legacy_3nf")
    op.create_index("idx_legacy_3nf_file_instance_import_run", "file_instance", ["import_run_id"], schema="legacy_3nf")
    op.create_index("idx_legacy_3nf_file_instance_content", "file_instance", ["content_identity_id"], schema="legacy_3nf")
    op.create_index("idx_legacy_3nf_action_event_import_run", "action_event", ["import_run_id"], schema="legacy_3nf")
    op.create_index("idx_legacy_3nf_duplicate_evidence_import_run", "duplicate_evidence", ["import_run_id"], schema="legacy_3nf")
    op.create_index(
        "idx_legacy_3nf_deletion_audit_candidate_import_run",
        "deletion_audit_candidate",
        ["import_run_id"],
        schema="legacy_3nf",
    )


def downgrade() -> None:
    op.drop_index("idx_legacy_3nf_deletion_audit_candidate_import_run", table_name="deletion_audit_candidate", schema="legacy_3nf")
    op.drop_index("idx_legacy_3nf_duplicate_evidence_import_run", table_name="duplicate_evidence", schema="legacy_3nf")
    op.drop_index("idx_legacy_3nf_action_event_import_run", table_name="action_event", schema="legacy_3nf")
    op.drop_index("idx_legacy_3nf_file_instance_content", table_name="file_instance", schema="legacy_3nf")
    op.drop_index("idx_legacy_3nf_file_instance_import_run", table_name="file_instance", schema="legacy_3nf")
    op.drop_index("idx_legacy_3nf_content_identity_import_run", table_name="content_identity", schema="legacy_3nf")
    op.drop_index("idx_legacy_3nf_scan_batch_import_run", table_name="scan_batch", schema="legacy_3nf")

    op.drop_table("canonical_candidate", schema="legacy_3nf")
    op.drop_table("deletion_audit_candidate_instance", schema="legacy_3nf")
    op.drop_table("deletion_audit_candidate", schema="legacy_3nf")
    op.drop_table("deletion_audit_run", schema="legacy_3nf")
    op.drop_table("duplicate_evidence", schema="legacy_3nf")
    op.drop_table("action_event", schema="legacy_3nf")
    op.drop_table("media_attributes", schema="legacy_3nf")
    op.drop_table("file_instance", schema="legacy_3nf")
    op.drop_table("content_identity", schema="legacy_3nf")
    op.drop_table("scan_batch", schema="legacy_3nf")
    op.drop_table("import_failure_events", schema="legacy_3nf")
    op.drop_table("import_runs", schema="legacy_3nf")

    op.drop_table("_tmp_deletion_audit_import", schema="legacy_raw")
    op.drop_table("deletion_audit_candidate_files", schema="legacy_raw")
    op.drop_table("deletion_audit_candidates", schema="legacy_raw")
    op.drop_table("deletion_audit_runs", schema="legacy_raw")
    op.drop_table("duplicate_candidates", schema="legacy_raw")
    op.drop_table("_file_actions_old", schema="legacy_raw")
    op.drop_table("file_actions", schema="legacy_raw")
    op.drop_table("files", schema="legacy_raw")
    op.drop_table("scans", schema="legacy_raw")

    op.execute("DROP SCHEMA IF EXISTS legacy_3nf CASCADE")
    op.execute("DROP SCHEMA IF EXISTS legacy_raw CASCADE")
