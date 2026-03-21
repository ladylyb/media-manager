from __future__ import annotations

import importlib
import logging
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

import media_manager.app.persistence.apply as apply_module
import media_manager.app.persistence.canonicalization as canonical_module
import media_manager.app.persistence.ingest as ingest_module
import media_manager.app.persistence.planner as planner_module
import media_manager.app.persistence.tag_enrichment as tag_module
from media_manager.app.canonical.context import CanonicalContext
from media_manager.app.canonical.policies import ShortestPathPolicy
from media_manager.app.persistence.apply import ApplyService
from media_manager.app.persistence.canonicalization import RecomputeMode, recompute_canonical_assignments
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.models import FailureEvent, FailurePhase, Run
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService
from media_manager.app.persistence.tag_enrichment import EnrichmentScope, TagEnrichmentCommand, run_tag_enrichment
from media_manager.tests.test_tag_enrichment_service import _seed_canonical_item, _upsert_metadata


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


def test_ingest_logs_progress_for_long_scan_and_final_item(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict]] = []

    def _capture(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        calls.append((message, kwargs.get("extra", {})))

    monkeypatch.setattr(ingest_module.logger, "info", _capture)

    ingest = IngestService(session_factory)
    files = [_write_file(tmp_path / "batch" / f"{idx:03d}.jpg", f"file-{idx}".encode()) for idx in range(105)]
    ingest.ingest_paths(files)

    progress_logs = [(msg, extra) for msg, extra in calls if extra.get("action") == "PROGRESS"]
    assert len(progress_logs) == 2
    first_msg, first_extra = progress_logs[0]
    final_msg, final_extra = progress_logs[-1]
    assert "Progress: 100/105 files" in first_msg
    assert first_extra["phase"] == "ingest"
    assert first_extra["processed_count"] == 100
    assert first_extra["total_count"] == 105
    assert isinstance(first_extra["progress_percent"], float)
    assert isinstance(first_extra["elapsed_seconds"], float)
    assert isinstance(first_extra["throughput_fps"], float)
    assert "Progress: 105/105 files" in final_msg
    assert final_extra["processed_count"] == 105
    assert final_extra["total_count"] == 105


def test_ingest_short_scan_still_logs_final_progress(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict]] = []

    def _capture(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        calls.append((message, kwargs.get("extra", {})))

    monkeypatch.setattr(ingest_module.logger, "info", _capture)

    ingest = IngestService(session_factory)
    files = [_write_file(tmp_path / "short" / f"{idx:03d}.jpg", f"short-{idx}".encode()) for idx in range(3)]
    ingest.ingest_paths(files)

    progress_logs = [(msg, extra) for msg, extra in calls if extra.get("action") == "PROGRESS"]
    assert len(progress_logs) == 1
    message, extra = progress_logs[0]
    assert "Progress: 3/3 files" in message
    assert extra["processed_count"] == 3
    assert extra["total_count"] == 3


def test_ingest_logs_finalizing_stage_after_scan_completes(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict]] = []

    def _capture(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        calls.append((message, kwargs.get("extra", {})))

    monkeypatch.setattr(ingest_module.logger, "info", _capture)

    ingest = IngestService(session_factory)
    files = [_write_file(tmp_path / "finalize" / f"{idx:03d}.jpg", f"file-{idx}".encode()) for idx in range(3)]
    ingest.ingest_paths(files)

    assert any(
        msg == "Finalizing ingest after scan progress reached its latest checkpoint"
        and extra.get("phase") == "ingest"
        and extra.get("stage") == "finalize"
        and extra.get("status") == "running"
        for msg, extra in calls
    )


def test_plan_logs_progress_for_long_run_and_final_item(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict]] = []

    def _capture(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        calls.append((message, kwargs.get("extra", {})))

    monkeypatch.setattr(planner_module.logger, "info", _capture)

    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    run = run_service.create_run()
    files = [_write_file(tmp_path / "planner" / f"{idx:03d}.jpg", f"planner-{idx}".encode()) for idx in range(105)]
    planner.plan_run(run.id, files)

    progress_logs = [(msg, extra) for msg, extra in calls if "processed_count" in extra and extra.get("phase") == "plan"]
    assert len(progress_logs) == 2
    first_msg, first_extra = progress_logs[0]
    final_msg, final_extra = progress_logs[-1]
    assert "Progress: 100/105 files" in first_msg
    assert first_extra["run_id"] == str(run.id)
    assert first_extra["processed_count"] == 100
    assert first_extra["total_count"] == 105
    assert isinstance(first_extra["progress_percent"], float)
    assert isinstance(first_extra["elapsed_seconds"], float)
    assert isinstance(first_extra["throughput_fps"], float)
    assert "Progress: 105/105 files" in final_msg
    assert final_extra["processed_count"] == 105
    assert final_extra["total_count"] == 105


def test_plan_logs_stage_narration_for_realistic_run(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict]] = []

    def _capture(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        calls.append((message, kwargs.get("extra", {})))

    monkeypatch.setattr(planner_module.logger, "info", _capture)

    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    run = run_service.create_run()
    files = [_write_file(tmp_path / "planner-stages" / f"{idx:03d}.jpg", f"planner-{idx}".encode()) for idx in range(5)]
    planner.plan_run(run.id, files)

    stage_statuses = {(extra.get("stage"), extra.get("status")) for _, extra in calls if extra.get("phase") == "plan"}
    assert ("discovery", "running") in stage_statuses
    assert ("discovery", "completed") in stage_statuses
    assert ("load_candidates", "running") in stage_statuses
    assert ("load_candidates", "completed") in stage_statuses
    assert ("metadata_lookup", "running") in stage_statuses
    assert ("metadata_lookup", "completed") in stage_statuses
    assert ("action_generation", "running") in stage_statuses
    assert ("action_generation", "completed") in stage_statuses
    assert ("persist_actions", "running") in stage_statuses
    assert ("persist_actions", "completed") in stage_statuses
    assert ("trace_write", "running") in stage_statuses
    assert ("trace_write", "completed") in stage_statuses
    assert ("finalize", "running") in stage_statuses
    assert ("finalize", "completed") in stage_statuses


def test_plan_short_run_still_logs_final_progress(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict]] = []

    def _capture(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        calls.append((message, kwargs.get("extra", {})))

    monkeypatch.setattr(planner_module.logger, "info", _capture)

    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    run = run_service.create_run()
    candidate = _write_file(tmp_path / "single" / "candidate.jpg", b"x")
    planner.plan_run(run.id, [candidate])

    progress_logs = [(msg, extra) for msg, extra in calls if "processed_count" in extra and extra.get("phase") == "plan"]
    assert len(progress_logs) == 1
    message, extra = progress_logs[0]
    assert "Progress: 1/1 files" in message
    assert extra["run_id"] == str(run.id)
    assert extra["processed_count"] == 1
    assert extra["total_count"] == 1


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


def test_apply_logs_progress_for_long_run_and_final_item(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict]] = []

    def _capture(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        calls.append((message, kwargs.get("extra", {})))

    monkeypatch.setattr(apply_module.logger, "info", _capture)

    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)
    run = run_service.create_run()
    files = [_write_file(tmp_path / "apply-progress" / f"{idx:03d}.jpg", f"apply-{idx}".encode()) for idx in range(105)]
    planner.plan_run(run.id, files)

    service = ApplyService(session_factory)
    service.apply_run(run.id)

    progress_logs = [(msg, extra) for msg, extra in calls if extra.get("stage") == "execute_actions"]
    assert any(extra.get("processed_count") == 100 for _, extra in progress_logs)
    assert any(extra.get("processed_count") == 105 for _, extra in progress_logs)


def test_formatter_renders_transition_fields_without_placeholder_noise() -> None:
    import media_manager.app.core.logging_config as logging_config

    formatter = logging_config._StructuredFormatter()
    record = logging.makeLogRecord(
        {
            "name": "media_manager.app.persistence.planner",
            "levelno": logging.INFO,
            "levelname": "INFO",
            "msg": "Transitioning run state",
            "run_id": "run-1",
            "phase": "plan",
            "from": "CREATED",
            "to": "PLANNED",
            "stage": "finalize",
            "status": "completed",
            "action_type": "",
        }
    )

    rendered = formatter.format(record)
    assert "from=CREATED" in rendered
    assert "to=PLANNED" in rendered
    assert "stage=finalize" in rendered
    assert "status=completed" in rendered
    assert "action_type=" not in rendered
    assert "scanned=-" not in rendered


def test_formatter_keeps_operator_useful_progress_fields_visible() -> None:
    import media_manager.app.core.logging_config as logging_config

    formatter = logging_config._StructuredFormatter()
    record = logging.makeLogRecord(
        {
            "name": "media_manager.app.persistence.tag_enrichment",
            "levelno": logging.INFO,
            "levelname": "INFO",
            "msg": "Tag enrichment run completed",
            "run_id": "run-2",
            "phase": "tag_enrichment",
            "stage": "finalize",
            "status": "COMPLETED",
            "processed_count": 5,
            "total_count": 5,
            "progress_percent": 100.0,
            "elapsed_seconds": 0.25,
            "failed_items": 0,
            "scope": "ALL",
            "source": "SYSTEM",
        }
    )

    rendered = formatter.format(record)
    assert "phase=tag_enrichment" in rendered
    assert "stage=finalize" in rendered
    assert "processed_count=5" in rendered
    assert "total_count=5" in rendered
    assert "progress_percent=100.0" in rendered
    assert "elapsed_seconds=0.25" in rendered
    assert "failed_items=0" in rendered


def test_canonical_recompute_logs_run_start_progress_and_completion(
    tmp_path: Path, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict]] = []

    def _capture(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        calls.append((message, kwargs.get("extra", {})))

    monkeypatch.setattr(canonical_module.logger, "info", _capture)

    ingest = IngestService(session_factory)
    first = _write_file(tmp_path / "canonical" / "first.jpg", b"same")
    second = _write_file(tmp_path / "canonical" / "copy" / "second.jpg", b"same")
    ingest.ingest_paths([first, second])

    summary = recompute_canonical_assignments(
        session_factory,
        policy=ShortestPathPolicy(),
        context=CanonicalContext(),
        mode=RecomputeMode.DRY_RUN,
    )

    assert any(msg == "Run started" and extra.get("phase") == "canonical" for msg, extra in calls)
    assert any(extra.get("processed_count") == summary.scanned_count for _, extra in calls if extra.get("phase") == "canonical")
    assert any(msg == "Run completed" and extra.get("phase") == "canonical" for msg, extra in calls)


def test_tag_enrichment_logs_run_start_progress_and_completion(
    session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict]] = []

    def _capture(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        calls.append((message, kwargs.get("extra", {})))

    monkeypatch.setattr(tag_module.logger, "info", _capture)

    c1 = uuid.UUID("30000000-0000-0000-0000-000000000001")
    c2 = uuid.UUID("30000000-0000-0000-0000-000000000002")
    _seed_canonical_item(session_factory, content_id=c1, path_suffix="tag-a", sha_char="a")
    _seed_canonical_item(session_factory, content_id=c2, path_suffix="tag-b", sha_char="b")
    _upsert_metadata(session_factory, c1, "OWNER", "Alice")
    _upsert_metadata(session_factory, c2, "OWNER", "Bob")

    summary = run_tag_enrichment(
        session_factory,
        TagEnrichmentCommand(scope=EnrichmentScope.ALL, batch_size=1, source=tag_module.TagSource.SYSTEM),
    )

    assert any(msg == "Run started" and extra.get("phase") == "tag_enrichment" for msg, extra in calls)
    assert any(extra.get("processed_count") == summary.number_of_items_processed for _, extra in calls if extra.get("phase") == "tag_enrichment")
    assert any(msg == "Tag enrichment run completed" and extra.get("phase") == "tag_enrichment" for msg, extra in calls)


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
