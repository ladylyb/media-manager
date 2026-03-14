from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from media_manager.app.cli import main
from media_manager.app.persistence.models import CanonicalAssignment, FileContent, FileInstance


def _seed_canonical(session_factory, content_id: uuid.UUID) -> None:
    with session_factory.begin() as session:
        instance_id = uuid.uuid4()
        session.add(FileContent(content_id=content_id, sha256_hash=content_id.hex.ljust(64, "0")))
        session.flush()
        session.add(
            FileInstance(
                file_instance_id=instance_id,
                content_id=content_id,
                absolute_path=f"/dataset/{content_id}.jpg",
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


def _seed_owner_metadata(session_factory, content_id: uuid.UUID, owner: str) -> None:
    with session_factory.begin() as session:
        session.execute(
            text(
                """
            INSERT INTO metadata_codes (id, code_type, description)
            VALUES (:id, 'OWNER', NULL)
            ON CONFLICT (code_type) DO NOTHING
            """
            ),
            {"id": uuid.uuid4()},
        )
        code_id = session.execute(text("SELECT id FROM metadata_codes WHERE code_type = 'OWNER'")).scalar_one()
        session.execute(
            text(
                """
            INSERT INTO media_metadata (id, content_id, code_id, decode_value)
            VALUES (:id, :content_id, :code_id, :decode_value)
            ON CONFLICT (content_id, code_id) DO UPDATE SET decode_value = EXCLUDED.decode_value
            """
            ),
            {
                "id": uuid.uuid4(),
                "content_id": content_id,
                "code_id": code_id,
                "decode_value": owner,
            },
        )


def test_cli_tag_enrich_all_success(test_database_url: str, monkeypatch, capsys, session_factory) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    c1 = uuid.uuid4()
    c2 = uuid.uuid4()
    _seed_canonical(session_factory, c1)
    _seed_canonical(session_factory, c2)
    _seed_owner_metadata(session_factory, c1, "Alice")
    _seed_owner_metadata(session_factory, c2, "Bob")

    exit_code = main(["tag-enrich", "--all", "--batch-size", "1"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Tag Enrichment Summary" in out
    assert "Items processed: 2" in out
    assert re.search(r"Run ID:\s+[0-9a-fA-F-]{36}", out)


def test_cli_tag_enrich_single_success(test_database_url: str, monkeypatch, capsys, session_factory) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    content_id = uuid.uuid4()
    _seed_canonical(session_factory, content_id)
    _seed_owner_metadata(session_factory, content_id, "Alice")

    exit_code = main(["tag-enrich", "--canonical-id", str(content_id)])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Scope: SINGLE" in out


def test_cli_tag_enrich_invalid_flag_combinations_return_usage_error(
    test_database_url: str, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    random_id = str(uuid.uuid4())
    both = main(["tag-enrich", "--all", "--canonical-id", random_id])
    assert both == 2
    assert "Specify exactly one of --all or --canonical-id." in capsys.readouterr().err

    neither = main(["tag-enrich"])
    assert neither == 2
    assert "Specify exactly one of --all or --canonical-id." in capsys.readouterr().err
