from __future__ import annotations

from sqlalchemy import inspect


def test_legacy_import_schemas_and_tables_exist(db_engine) -> None:
    inspector = inspect(db_engine)
    schemas = set(inspector.get_schema_names())
    assert "legacy_raw" in schemas
    assert "legacy_3nf" in schemas

    raw_tables = set(inspector.get_table_names(schema="legacy_raw"))
    assert {
        "scans",
        "files",
        "file_actions",
        "_file_actions_old",
        "duplicate_candidates",
        "deletion_audit_runs",
        "deletion_audit_candidates",
        "deletion_audit_candidate_files",
        "_tmp_deletion_audit_import",
    }.issubset(raw_tables)

    normalized_tables = set(inspector.get_table_names(schema="legacy_3nf"))
    assert {
        "import_runs",
        "import_failure_events",
        "scan_batch",
        "content_identity",
        "file_instance",
        "media_attributes",
        "action_event",
        "duplicate_evidence",
        "deletion_audit_run",
        "deletion_audit_candidate",
        "deletion_audit_candidate_instance",
        "canonical_candidate",
    }.issubset(normalized_tables)
