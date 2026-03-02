from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from media_manager.app.persistence.base import create_db_engine, create_session_factory
from media_manager.app.persistence.materialized_reads import fetch_canonical_metadata, refresh_materialized_view
from media_manager.app.persistence.models import PlannedAction
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _plan_struct(session_factory, paths: list[Path]) -> tuple[dict[str, int], list[tuple[str, str, str]]]:
    run = RunService(session_factory).create_run()
    summary = PlanningService(session_factory).plan_run(run.id, paths, ingest_if_needed=True)
    with session_factory() as session:
        actions = session.scalars(
            select(PlannedAction)
            .where(PlannedAction.run_id == run.id)
            .order_by(PlannedAction.action_type.asc(), PlannedAction.source_path.asc(), PlannedAction.target_path.asc())
        ).all()
    return (
        {
            "scanned": summary.scanned_count,
            "moves": summary.move_actions,
            "duplicates": summary.duplicate_actions,
            "noop": summary.noop_actions,
            "skipped": summary.skipped_count,
        },
        [(row.action_type, row.source_path, row.target_path or "") for row in actions],
    )


def test_cache_reads_and_planner_outputs_are_semantically_identical(
    tmp_path: Path,
    test_database_url: str,
    session_factory,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)

    dataset = tmp_path / "dataset"
    a = _write_file(dataset / "a" / "one.jpg", b"same")
    b = _write_file(dataset / "b" / "two.jpg", b"same")
    c = _write_file(dataset / "c" / "three.jpg", b"unique")

    plan_no_cache = _plan_struct(session_factory, [a, b, c])
    monkeypatch.setenv("CANONICAL_READ_CACHE_ENABLED", "true")
    plan_with_cache = _plan_struct(session_factory, [a, b, c])
    assert plan_no_cache == plan_with_cache

    engine = create_db_engine(test_database_url)
    refresh_materialized_view(engine, concurrently=False)
    with create_session_factory(engine)() as session:
        uncached = fetch_canonical_metadata(session, use_mv=True, sample_size=1000, use_cache=False)
        cached = fetch_canonical_metadata(session, use_mv=True, sample_size=1000, use_cache=True)
    assert uncached == cached


def test_planner_module_does_not_import_ttl_cache() -> None:
    planner_source = Path("media_manager/app/persistence/planner.py").read_text(encoding="utf-8").lower()
    assert "ttl_cache" not in planner_source
