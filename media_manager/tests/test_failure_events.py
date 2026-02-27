from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from media_manager.app.persistence.models import FailurePhase
from media_manager.app.persistence.runs import RunService


def test_failure_events_cannot_be_updated(run_service: RunService, db_engine) -> None:
    run = run_service.create_run()
    event = run_service.append_failure(
        run.id,
        FailurePhase.APPLY,
        error_code="E_TEST_UPDATE",
        error_message="original message",
    )

    with pytest.raises(DBAPIError):
        with db_engine.begin() as conn:
            conn.execute(
                text("UPDATE failure_events SET error_message = 'changed' WHERE id = :id"),
                {"id": event.id},
            )


def test_failure_events_cannot_be_deleted(run_service: RunService, db_engine) -> None:
    run = run_service.create_run()
    event = run_service.append_failure(
        run.id,
        FailurePhase.APPLY,
        error_code="E_TEST_DELETE",
        error_message="cannot delete",
    )

    with pytest.raises(DBAPIError):
        with db_engine.begin() as conn:
            conn.execute(text("DELETE FROM failure_events WHERE id = :id"), {"id": event.id})
