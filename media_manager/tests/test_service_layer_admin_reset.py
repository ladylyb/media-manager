from __future__ import annotations

from sqlalchemy import select, text

from media_manager.app.persistence.base import create_db_engine, create_session_factory, transactional_session
from media_manager.app.persistence.models import MediaFile, Run
from media_manager.app.service_layer.admin import AdminServices
from media_manager.app.service_layer.errors import ServiceLayerException


def _insert_fixture_rows(session_factory) -> None:  # type: ignore[no-untyped-def]
    with transactional_session(session_factory) as session:
        session.add(Run())
        session.add(MediaFile(current_path="/tmp/a.jpg", discovered_path="/tmp/a.jpg", status="INGESTED"))


def _counts(session_factory) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    with session_factory() as session:
        return (
            len(session.scalars(select(Run)).all()),
            len(session.scalars(select(MediaFile)).all()),
        )


def test_admin_db_reset_dry_run_lists_tables_without_deleting(test_database_url: str, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("MEDIA_MANAGER_ENV", "test")
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    _insert_fixture_rows(session_factory)
    before = _counts(session_factory)
    service = AdminServices(session_factory=session_factory)

    result = service.db_reset(dry_run=True, challenge_word=None)

    after = _counts(session_factory)
    assert result["success"] is True
    assert result["dry_run"] is True
    assert "media_file" in result["affected_tables"]
    assert before == after


def test_admin_db_reset_requires_correct_challenge(test_database_url: str, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("MEDIA_MANAGER_ENV", "test")
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    service = AdminServices(session_factory=session_factory)
    try:
        service.db_reset(dry_run=False, challenge_word="wrong")
        assert False, "expected challenge validation failure"
    except ServiceLayerException as exc:
        assert exc.http_status == 400


def test_admin_db_reset_hard_blocks_non_dev_test_env(test_database_url: str, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("MEDIA_MANAGER_ENV", "prod")
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    service = AdminServices(session_factory=session_factory)
    try:
        service.db_reset(dry_run=True, challenge_word=None)
        assert False, "expected forbidden env failure"
    except ServiceLayerException as exc:
        assert exc.http_status == 403


def test_admin_db_reset_is_idempotent(test_database_url: str, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("MEDIA_MANAGER_ENV", "test")
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    _insert_fixture_rows(session_factory)
    service = AdminServices(session_factory=session_factory)

    first = service.db_reset(dry_run=False, challenge_word="media-manager")
    second = service.db_reset(dry_run=False, challenge_word="media-manager")

    after = _counts(session_factory)
    assert first["success"] is True
    assert second["success"] is True
    assert after == (0, 0)


def test_admin_db_reset_dynamic_extras_included_when_enabled(test_database_url: str, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("MEDIA_MANAGER_ENV", "test")
    monkeypatch.setenv("MEDIA_MANAGER_DB_RESET_INCLUDE_DYNAMIC", "true")
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    with transactional_session(session_factory) as session:
        session.execute(text("CREATE TABLE IF NOT EXISTS admin_reset_extra(id integer)"))
    try:
        service = AdminServices(session_factory=session_factory)
        result = service.db_reset(dry_run=True, challenge_word=None)
        assert "admin_reset_extra" in result["affected_tables"]
    finally:
        with transactional_session(session_factory) as session:
            session.execute(text("DROP TABLE IF EXISTS admin_reset_extra"))


def test_admin_db_reset_rolls_back_on_partial_failure(test_database_url: str, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("MEDIA_MANAGER_ENV", "test")
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    _insert_fixture_rows(session_factory)
    service = AdminServices(session_factory=session_factory)
    before = _counts(session_factory)

    def _partial_then_fail(*, affected_tables):  # type: ignore[no-untyped-def]
        with transactional_session(session_factory) as session:
            session.execute(text('TRUNCATE TABLE "media_file"'))
            raise RuntimeError("boom")

    monkeypatch.setattr(service, "_execute_reset_transaction", _partial_then_fail)
    try:
        service.db_reset(dry_run=False, challenge_word="media-manager")
        assert False, "expected reset failure"
    except ServiceLayerException as exc:
        assert exc.http_status == 500

    after = _counts(session_factory)
    assert before == after
