from __future__ import annotations

import pytest
from sqlalchemy import select

from media_manager.app.core.errors import InvalidRunTransitionError, TransitionConflictError
from media_manager.app.core.state_machine import RunState
from media_manager.app.persistence.models import Run
from media_manager.app.persistence.runs import RunService


def test_valid_transition_sequence(run_service: RunService) -> None:
    run = run_service.create_run()
    assert run.state == RunState.CREATED
    assert run.version == 1

    run = run_service.transition_run(run.id, RunState.PLANNED)
    assert run.state == RunState.PLANNED
    assert run.version == 2

    run = run_service.transition_run(run.id, RunState.APPLYING)
    assert run.state == RunState.APPLYING
    assert run.version == 3

    run = run_service.transition_run(run.id, RunState.COMPLETED)
    assert run.state == RunState.COMPLETED
    assert run.version == 4


def test_invalid_transition_rejected(run_service: RunService) -> None:
    run = run_service.create_run()

    with pytest.raises(InvalidRunTransitionError):
        run_service.transition_run(run.id, RunState.APPLYING)


def test_multiple_applying_runs_fail(run_service: RunService) -> None:
    run_1 = run_service.create_run()
    run_1 = run_service.transition_run(run_1.id, RunState.PLANNED)
    run_service.transition_run(run_1.id, RunState.APPLYING)

    run_2 = run_service.create_run()
    run_2 = run_service.transition_run(run_2.id, RunState.PLANNED)

    with pytest.raises(TransitionConflictError):
        run_service.transition_run(run_2.id, RunState.APPLYING)


def test_transition_rollback_on_error(run_service: RunService, session_factory) -> None:
    run_1 = run_service.create_run()
    run_service.transition_run(run_1.id, RunState.PLANNED)
    run_service.transition_run(run_1.id, RunState.APPLYING)

    run_2 = run_service.create_run()
    run_service.transition_run(run_2.id, RunState.PLANNED)

    with pytest.raises(TransitionConflictError):
        run_service.transition_run(run_2.id, RunState.APPLYING)

    with session_factory() as session:
        persisted = session.scalar(select(Run).where(Run.id == run_2.id))
        assert persisted is not None
        assert persisted.state.value == RunState.PLANNED.value
        assert persisted.version == 2


def test_resume_failed_to_applying(run_service: RunService) -> None:
    run = run_service.create_run()
    run = run_service.transition_run(run.id, RunState.PLANNED)
    run = run_service.transition_run(run.id, RunState.APPLYING)
    run = run_service.transition_run(run.id, RunState.FAILED)

    resumed = run_service.transition_run(run.id, RunState.APPLYING)
    assert resumed.state == RunState.APPLYING
