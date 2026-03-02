from __future__ import annotations

import types
from pathlib import Path

from sqlalchemy import event

from media_manager.app.persistence.materialized_reads import fetch_canonical_metadata
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_planner_default_path_does_not_query_mv(tmp_path: Path, db_engine, session_factory) -> None:
    dataset = tmp_path / "dataset"
    a = _write_file(dataset / "a" / "one.jpg", b"same")
    b = _write_file(dataset / "b" / "two.jpg", b"same")

    observed_mv_queries: list[str] = []

    def _capture_mv_sql(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        if "mv_canonical_metadata" in statement.lower():
            observed_mv_queries.append(statement)

    event.listen(db_engine, "before_cursor_execute", _capture_mv_sql)
    try:
        run = RunService(session_factory).create_run()
        PlanningService(session_factory).plan_run(run.id, [a, b], ingest_if_needed=True)
    finally:
        event.remove(db_engine, "before_cursor_execute", _capture_mv_sql)

    assert observed_mv_queries == []


def test_mv_guard_raises_for_planner_call_stack(test_database_url: str, session_factory, monkeypatch) -> None:
    monkeypatch.delenv("MEDIA_MANAGER_ALLOW_PLANNER_MV_READS", raising=False)

    # Compile with planner module filename so guard sees a planner call-stack frame.
    planner_filename = "media_manager/app/persistence/planner.py"
    module = types.ModuleType("planner_stack_probe")
    code = compile(
        "def invoke(session, fetch):\n"
        "    return fetch(session, use_mv=True, sample_size=1, use_cache=False)\n",
        planner_filename,
        "exec",
    )
    exec(code, module.__dict__)

    with session_factory() as session:
        try:
            module.invoke(session, fetch_canonical_metadata)  # type: ignore[attr-defined]
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            assert "MV reads from planner path are blocked by default" in str(exc)
