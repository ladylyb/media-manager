from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text, update

from media_manager.app.persistence.models import (
    CanonicalAssignment,
    FileContent,
    FileInstance,
    MediaMetadata,
    MetadataCode,
    TagSource,
)
from media_manager.app.persistence.tag_enrichment import (
    EnrichmentScope,
    TagEnrichmentCommand,
    get_enrichment_delta,
    get_last_run_for_canonical,
    list_reprocessing_history,
    run_tag_enrichment,
)


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


def test_get_last_run_for_canonical_returns_latest_record(session_factory) -> None:
    content_id = uuid.uuid4()
    _seed_canonical_item(session_factory, content_id=content_id, path_suffix="latest", sha_char="a")
    _upsert_metadata(session_factory, content_id, "OWNER", "Alice")

    first = run_tag_enrichment(
        session_factory,
        TagEnrichmentCommand(scope=EnrichmentScope.SINGLE, canonical_id=content_id, source=TagSource.SYSTEM),
    )
    _upsert_metadata(session_factory, content_id, "OWNER", "Bob")
    second = run_tag_enrichment(
        session_factory,
        TagEnrichmentCommand(scope=EnrichmentScope.SINGLE, canonical_id=content_id, source=TagSource.SYSTEM),
    )

    latest = get_last_run_for_canonical(
        session_factory,
        canonical_id=content_id,
        source=TagSource.SYSTEM,
    )
    assert latest is not None
    assert latest.run_id == second.run_id
    assert latest.result == "UPDATED"
    assert latest.previous_version == 1
    assert latest.new_version == 2
    assert latest.run_id != first.run_id


def test_get_enrichment_delta_reports_confidence_changes(session_factory) -> None:
    content_id = uuid.uuid4()
    _seed_canonical_item(session_factory, content_id=content_id, path_suffix="delta", sha_char="b")
    _upsert_metadata(session_factory, content_id, "OWNER", "Alice")
    run_tag_enrichment(
        session_factory,
        TagEnrichmentCommand(scope=EnrichmentScope.SINGLE, canonical_id=content_id, source=TagSource.SYSTEM),
    )

    _upsert_metadata(session_factory, content_id, "TAGS", "Alice")
    second = run_tag_enrichment(
        session_factory,
        TagEnrichmentCommand(scope=EnrichmentScope.SINGLE, canonical_id=content_id, source=TagSource.SYSTEM),
    )

    delta_one = get_enrichment_delta(
        session_factory,
        run_id=second.run_id,
        canonical_id=content_id,
    )
    delta_two = get_enrichment_delta(
        session_factory,
        run_id=second.run_id,
        canonical_id=content_id,
    )
    assert delta_one is not None
    assert delta_two is not None
    assert delta_one.to_dict() == delta_two.to_dict()
    assert delta_one.added == ()
    assert delta_one.removed == ()
    assert delta_one.changed_confidence == (
        {
            "tag": "alice",
            "previous_confidence": 0.75,
            "current_confidence": 0.95,
        },
    )
    assert delta_one.version_before == 1
    assert delta_one.version_after == 2


def test_list_reprocessing_history_is_deterministic(session_factory) -> None:
    content_id = uuid.uuid4()
    _seed_canonical_item(session_factory, content_id=content_id, path_suffix="history", sha_char="c")
    _upsert_metadata(session_factory, content_id, "OWNER", "Alice")
    run_tag_enrichment(
        session_factory,
        TagEnrichmentCommand(scope=EnrichmentScope.SINGLE, canonical_id=content_id, source=TagSource.SYSTEM),
    )
    run_tag_enrichment(
        session_factory,
        TagEnrichmentCommand(scope=EnrichmentScope.SINGLE, canonical_id=content_id, source=TagSource.SYSTEM),
    )
    _upsert_metadata(session_factory, content_id, "OWNER", "Bob")
    run_tag_enrichment(
        session_factory,
        TagEnrichmentCommand(scope=EnrichmentScope.SINGLE, canonical_id=content_id, source=TagSource.SYSTEM),
    )

    history_one = list_reprocessing_history(
        session_factory,
        canonical_id=content_id,
        source=TagSource.SYSTEM,
        limit=50,
    )
    history_two = list_reprocessing_history(
        session_factory,
        canonical_id=content_id,
        source=TagSource.SYSTEM,
        limit=50,
    )
    assert [row.to_dict() for row in history_one] == [row.to_dict() for row in history_two]
    assert [row.result for row in history_one] == ["UPDATED", "UNCHANGED", "UPDATED"]
    assert [row.sequence_no for row in history_one] == [1, 1, 1]
