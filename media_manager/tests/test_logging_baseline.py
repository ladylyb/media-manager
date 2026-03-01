from __future__ import annotations

import importlib
import logging
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

import media_manager.app.persistence.apply as apply_module
import media_manager.app.persistence.planner as planner_module
from media_manager.app.persistence.apply import ApplyService
from media_manager.app.persistence.models import FailureEvent, FailurePhase, Run
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _create_planned_run(tmp_path: Path, session_factory) -> uuid.UUID:
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    run = run_service.create_run()

    noop_path = _write_file(tmp_path / "Media" / "Photos" / "2024" / "01" / "IMG_20240110.jpg", b"noop")
    move_path = _write_file(tmp_path / "inbox" / "IMG_20240111.jpg", b"dup-content")
    dup_path = _write_file(tmp_path / "inbox" / "dup_copy.jpg", b"dup-content")
    planner.plan_run(run.id, [noop_path, move_path, dup_path])
    return run.id


def test_plan_logs_run_start_and_end(tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict]] = []

    def _capture(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        calls.append((message, kwargs.get("extra", {})))

    monkeypatch.setattr(planner_module.logger, "info", _capture)

    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    run = run_service.create_run()
    candidate = _write_file(tmp_path / "inbox" / "IMG_20240111.jpg", b"x")
    planner.plan_run(run.id, [candidate])

    assert any(msg == "Run started" and extra.get("phase") == "plan" for msg, extra in calls)
    assert any(msg == "Run completed" and extra.get("phase") == "plan" for msg, extra in calls)


def test_plan_logs_transition_and_summary_counts(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict]] = []

    def _capture(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        calls.append((message, kwargs.get("extra", {})))

    monkeypatch.setattr(planner_module.logger, "info", _capture)

    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    run = run_service.create_run()

    noop_path = _write_file(tmp_path / "Media" / "Photos" / "2024" / "01" / "IMG_20240110.jpg", b"noop")
    move_path = _write_file(tmp_path / "inbox" / "IMG_20240111.jpg", b"dup-content")
    dup_path = _write_file(tmp_path / "inbox" / "dup_copy.jpg", b"dup-content")
    summary = planner.plan_run(run.id, [noop_path, move_path, dup_path])

    transition_logs = [extra for msg, extra in calls if msg == "Transitioning run state"]
    summary_logs = [extra for msg, extra in calls if msg == "Summary counts"]
    assert len(transition_logs) >= 1
    assert len(summary_logs) == 1
    extra = summary_logs[0]
    assert extra["scanned"] == summary.scanned_count
    assert extra["supported"] == summary.supported_count
    assert extra["skipped"] == summary.skipped_count
    assert extra["moves"] == summary.move_actions
    assert extra["duplicates"] == summary.duplicate_actions
    assert extra["noop"] == summary.noop_actions
    assert extra["errors"] == 0


def test_apply_logs_run_start_transition_end(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict]] = []

    def _capture(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        calls.append((message, kwargs.get("extra", {})))

    monkeypatch.setattr(apply_module.logger, "info", _capture)

    run_id = _create_planned_run(tmp_path, session_factory)
    service = ApplyService(session_factory)
    summary = service.apply_run(run_id)

    assert any(msg == "Run started" and extra.get("phase") == "apply" for msg, extra in calls)
    assert len([1 for msg, _ in calls if msg == "Transitioning run state"]) >= 2
    assert any(msg == "Run completed" and extra.get("phase") == "apply" for msg, extra in calls)

    summary_logs = [extra for msg, extra in calls if msg == "Summary counts"]
    assert len(summary_logs) == 1
    extra = summary_logs[0]
    assert extra["applied"] == summary.applied_count
    assert extra["moves"] == summary.moves_count
    assert extra["duplicates"] == summary.duplicates_count
    assert extra["noop"] == summary.noop_count
    assert extra["errors"] == summary.errors_count


def test_apply_logs_exception_on_simulated_failure(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    info_calls: list[tuple[str, dict]] = []
    exception_calls: list[tuple[str, dict]] = []

    def _capture_info(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        info_calls.append((message, kwargs.get("extra", {})))

    def _capture_exception(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        exception_calls.append((message, kwargs.get("extra", {})))

    monkeypatch.setattr(apply_module.logger, "info", _capture_info)
    monkeypatch.setattr(apply_module.logger, "exception", _capture_exception)

    run_id = _create_planned_run(tmp_path, session_factory)
    service = ApplyService(session_factory)

    def _raise(_run_id, _action, _collision_mode) -> None:
        raise RuntimeError("simulated apply failure")

    monkeypatch.setattr(service, "_execute_action", _raise)
    with pytest.raises(RuntimeError, match="simulated apply failure"):
        service.apply_run(run_id)

    assert any(msg == "Apply failed" and extra.get("phase") == "apply" for msg, extra in exception_calls)
    assert any(msg == "Apply failed" and extra.get("collision_mode") == "rename" for msg, extra in exception_calls)
    assert any(
        msg == "Apply action failed"
        and extra.get("planned_action_id")
        and extra.get("file_instance_id")
        and extra.get("collision_mode") == "rename"
        for msg, extra in exception_calls
    )

    with session_factory() as session:
        run = session.scalar(select(Run).where(Run.id == run_id))
        assert run is not None
        failures = session.scalars(select(FailureEvent).where(FailureEvent.run_id == run_id)).all()
        assert len(failures) == 1
        assert failures[0].phase == FailurePhase.APPLY


def test_log_level_from_env(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv("LOG_LEVEL", "WARNING")

    import media_manager.app.core.logging_config as logging_config

    logging_config._CONFIGURED = False
    importlib.reload(logging_config)
    logging_config.configure_logging()

    logger = logging.getLogger("media_manager.logleveltest")
    logger.setLevel(logging.NOTSET)
    with caplog.at_level(logging.WARNING):
        logger.info("info should be filtered")
        logger.warning("warning should be present")

    text = caplog.text
    assert "info should be filtered" not in text
    assert "warning should be present" in text
