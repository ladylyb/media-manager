from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text, update

import media_manager.app.persistence.tag_enrichment as enrichment_module
from media_manager.app.persistence.models import (
    CanonicalAssignment,
    CanonicalTag,
    FileContent,
    FileInstance,
    MediaMetadata,
    MetadataCode,
    TagEnrichmentItem,
    TagEnrichmentRun,
    TagSource,
)
from media_manager.app.persistence.tag_enrichment import (
    EnrichmentScope,
    TagEnrichmentCommand,
    run_tag_enrichment,
)
from media_manager.app.persistence.tagging import upsert_canonical_tag


def _seed_canonical_item(session_factory, *, content_id: uuid.UUID, path_suffix: str, sha_char: str) -> None:
    with session_factory.begin() as session:
        instance_id = uuid.uuid4()
        session.add(FileContent(content_id=content_id, sha256_hash=sha_char * 64))
        session.flush()
        session.add(
            FileInstance(
                file_instance_id=instance_id,
                content_id=content_id,
                absolute_path=f"/dataset/{path_suffix}.jpg",
                status="ACTIVE",
            )
        )
        session.add(
            CanonicalAssignment(
                assignment_id=uuid.uuid4(),
                content_id=content_id,
                canonical_instance_id=instance_id,
                policy_name="FIRST_SEEN",
                policy_version="v1",
                assigned_at=datetime.now(timezone.utc),
            )
        )


def _ensure_code(session_factory, code_type: str) -> uuid.UUID:
    with session_factory.begin() as session:
        existing = session.scalar(select(MetadataCode.id).where(MetadataCode.code_type == code_type))
        if existing is not None:
            return existing
        code_id = uuid.uuid4()
        session.execute(
            text("INSERT INTO metadata_codes (id, code_type, description) VALUES (:id, :code, NULL)"),
            {"id": code_id, "code": code_type},
        )
        return code_id


def _upsert_metadata(session_factory, content_id: uuid.UUID, code_type: str, decode_value: str) -> None:
    code_id = _ensure_code(session_factory, code_type)
    with session_factory.begin() as session:
        existing = session.scalar(
            select(MediaMetadata.id).where(
                MediaMetadata.content_id == content_id,
                MediaMetadata.code_id == code_id,
            )
        )
        if existing is None:
            session.execute(
                text(
                    """
                    INSERT INTO media_metadata (id, content_id, code_id, decode_value)
                    VALUES (:id, :content_id, :code_id, :decode_value)
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "content_id": content_id,
                    "code_id": code_id,
                    "decode_value": decode_value,
                },
            )
        else:
            session.execute(
                update(MediaMetadata)
                .where(MediaMetadata.id == existing)
                .values(decode_value=decode_value)
            )


def test_all_scope_processes_canonical_ids_deterministically(session_factory) -> None:
    c1 = uuid.UUID("10000000-0000-0000-0000-000000000001")
    c2 = uuid.UUID("20000000-0000-0000-0000-000000000002")
    _seed_canonical_item(session_factory, content_id=c2, path_suffix="b", sha_char="b")
    _seed_canonical_item(session_factory, content_id=c1, path_suffix="a", sha_char="a")
    _upsert_metadata(session_factory, c1, "OWNER", "Alice")
    _upsert_metadata(session_factory, c2, "OWNER", "Bob")

    summary = run_tag_enrichment(
        session_factory,
        TagEnrichmentCommand(scope=EnrichmentScope.ALL, batch_size=1, source=TagSource.SYSTEM),
    )
    assert summary.number_of_items_processed == 2
    with session_factory() as session:
        rows = session.scalars(
            select(TagEnrichmentItem).where(TagEnrichmentItem.run_id == summary.run_id).order_by(TagEnrichmentItem.sequence_no.asc())
        ).all()
        assert [str(row.canonical_id) for row in rows] == [str(c1), str(c2)]


def test_rerun_idempotent_keeps_versions_when_unchanged(session_factory) -> None:
    content_id = uuid.uuid4()
    _seed_canonical_item(session_factory, content_id=content_id, path_suffix="same", sha_char="c")
    _upsert_metadata(session_factory, content_id, "OWNER", "Alice")
    _upsert_metadata(session_factory, content_id, "CONTEXT", "Travel")

    first = run_tag_enrichment(
        session_factory,
        TagEnrichmentCommand(scope=EnrichmentScope.SINGLE, canonical_id=content_id, source=TagSource.SYSTEM),
    )
    second = run_tag_enrichment(
        session_factory,
        TagEnrichmentCommand(scope=EnrichmentScope.SINGLE, canonical_id=content_id, source=TagSource.SYSTEM),
    )
    assert first.number_of_items_processed == second.number_of_items_processed == 1
    with session_factory() as session:
        tags = session.scalars(
            select(CanonicalTag)
            .where(CanonicalTag.canonical_id == content_id, CanonicalTag.source == TagSource.SYSTEM.value)
            .order_by(CanonicalTag.tag_id.asc())
        ).all()
        assert len(tags) >= 2
        versions = {row.enrichment_version for row in tags}
        assert versions == {1}
        latest_item = session.scalar(
            select(TagEnrichmentItem)
            .where(TagEnrichmentItem.run_id == second.run_id)
            .order_by(TagEnrichmentItem.sequence_no.asc())
        )
        assert latest_item is not None
        assert latest_item.result == "UNCHANGED"


def test_changed_output_bumps_version_once(session_factory) -> None:
    content_id = uuid.uuid4()
    _seed_canonical_item(session_factory, content_id=content_id, path_suffix="changed", sha_char="d")
    _upsert_metadata(session_factory, content_id, "OWNER", "Alice")
    run_tag_enrichment(
        session_factory,
        TagEnrichmentCommand(scope=EnrichmentScope.SINGLE, canonical_id=content_id, source=TagSource.SYSTEM),
    )
    _upsert_metadata(session_factory, content_id, "OWNER", "Bob")
    run_tag_enrichment(
        session_factory,
        TagEnrichmentCommand(scope=EnrichmentScope.SINGLE, canonical_id=content_id, source=TagSource.SYSTEM),
    )
    with session_factory() as session:
        tags = session.scalars(
            select(CanonicalTag)
            .where(CanonicalTag.canonical_id == content_id, CanonicalTag.source == TagSource.SYSTEM.value)
        ).all()
        assert tags
        assert {row.enrichment_version for row in tags} == {2}


def test_single_scope_touches_only_target(session_factory) -> None:
    c1 = uuid.uuid4()
    c2 = uuid.uuid4()
    _seed_canonical_item(session_factory, content_id=c1, path_suffix="single1", sha_char="e")
    _seed_canonical_item(session_factory, content_id=c2, path_suffix="single2", sha_char="f")
    _upsert_metadata(session_factory, c1, "OWNER", "A")
    _upsert_metadata(session_factory, c2, "OWNER", "B")

    run_tag_enrichment(
        session_factory,
        TagEnrichmentCommand(scope=EnrichmentScope.SINGLE, canonical_id=c1, source=TagSource.SYSTEM),
    )
    with session_factory() as session:
        touched_c1 = session.scalar(
            select(CanonicalTag)
            .where(CanonicalTag.canonical_id == c1, CanonicalTag.source == TagSource.SYSTEM.value)
        )
        touched_c2 = session.scalar(
            select(CanonicalTag)
            .where(CanonicalTag.canonical_id == c2, CanonicalTag.source == TagSource.SYSTEM.value)
        )
        assert touched_c1 is not None
        assert touched_c2 is None


def test_invalid_single_scope_canonical_id_fails(session_factory) -> None:
    with pytest.raises(ValueError, match="not a current canonical"):
        run_tag_enrichment(
            session_factory,
            TagEnrichmentCommand(
                scope=EnrichmentScope.SINGLE,
                canonical_id=uuid.uuid4(),
                source=TagSource.SYSTEM,
            ),
        )


def test_run_summary_fields_persisted(session_factory) -> None:
    content_id = uuid.uuid4()
    _seed_canonical_item(session_factory, content_id=content_id, path_suffix="summary", sha_char="a")
    _upsert_metadata(session_factory, content_id, "OWNER", "Owner")
    summary = run_tag_enrichment(
        session_factory,
        TagEnrichmentCommand(scope=EnrichmentScope.SINGLE, canonical_id=content_id, source=TagSource.SYSTEM),
    )
    assert summary.duration_ms >= 0
    assert summary.average_confidence is not None
    with session_factory() as session:
        row = session.get(TagEnrichmentRun, summary.run_id)
        assert row is not None
        assert row.number_of_items_processed == 1
        assert row.status == "COMPLETED"


def test_item_failure_records_durable_failure_fact(session_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    content_id = uuid.uuid4()
    _seed_canonical_item(session_factory, content_id=content_id, path_suffix="fail", sha_char="9")
    _upsert_metadata(session_factory, content_id, "OWNER", "Owner")

    def _raise(_session, _canonical_id):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    monkeypatch.setattr(enrichment_module, "_build_desired_tag_confidence_map", _raise)
    summary = run_tag_enrichment(
        session_factory,
        TagEnrichmentCommand(scope=EnrichmentScope.SINGLE, canonical_id=content_id, source=TagSource.SYSTEM),
    )
    assert summary.status == "COMPLETED_WITH_ERRORS"
    with session_factory() as session:
        item = session.scalar(select(TagEnrichmentItem).where(TagEnrichmentItem.run_id == summary.run_id))
        assert item is not None
        assert item.result == "FAILED"
        assert "boom" in (item.error_message or "")


def test_source_isolation_system_does_not_mutate_ai_rows(session_factory) -> None:
    content_id = uuid.uuid4()
    _seed_canonical_item(session_factory, content_id=content_id, path_suffix="source", sha_char="8")
    _upsert_metadata(session_factory, content_id, "OWNER", "Owner")
    with session_factory.begin() as session:
        upsert_canonical_tag(
            session,
            canonical_id=content_id,
            tag_name="ai-tag",
            source=TagSource.AI,
            confidence_score=0.88,
            enrichment_version=3,
        )
    run_tag_enrichment(
        session_factory,
        TagEnrichmentCommand(scope=EnrichmentScope.SINGLE, canonical_id=content_id, source=TagSource.SYSTEM),
    )
    with session_factory() as session:
        ai_rows = session.scalars(
            select(CanonicalTag).where(
                CanonicalTag.canonical_id == content_id,
                CanonicalTag.source == TagSource.AI.value,
            )
        ).all()
        assert len(ai_rows) == 1
        assert ai_rows[0].enrichment_version == 3
