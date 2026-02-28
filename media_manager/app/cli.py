from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from media_manager.app.core.errors import MediaManagerError
from media_manager.app.persistence.apply import ApplyService
from media_manager.app.persistence.base import create_db_engine, create_session_factory
from media_manager.app.persistence.models import PlannedAction
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService


def _path_sort_key(path: Path) -> str:
    return path.resolve(strict=False).as_posix()


def _collect_input_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    files = [candidate for candidate in path.rglob("*") if candidate.is_file()]
    return sorted(files, key=_path_sort_key)


def _render_plan_output(run_id: uuid.UUID, planned_actions: list[PlannedAction], summary) -> None:
    grouped: dict[str, list[PlannedAction]] = {"MOVE": [], "MARK_DUPLICATE": [], "NOOP": []}
    for action in planned_actions:
        if action.action_type in grouped:
            grouped[action.action_type].append(action)

    section_order = [("MOVE", "MOVE"), ("MARK_DUPLICATE", "DUPLICATE"), ("NOOP", "NOOP")]
    first_section = True
    for action_type, label in section_order:
        entries = grouped[action_type]
        if not entries:
            continue
        if not first_section:
            print()
        first_section = False
        print(label)
        for action in entries:
            print(f"  {action.source_path}")
            if action.action_type != "NOOP" and action.target_path:
                print(f"    → {action.target_path}")

    print()
    print("----------------------------------------")
    print("Summary")
    print(f"  Files scanned: {summary.scanned_count}")
    print(f"  Moves: {summary.move_actions}")
    print(f"  Duplicates: {summary.duplicate_actions}")
    print(f"  No-op: {summary.noop_actions}")
    print(f"  Skipped: {summary.skipped_count}")
    print("----------------------------------------")
    print(f"Run ID: {run_id}")


def _render_apply_output(run_id: uuid.UUID, planned_actions: list[PlannedAction], summary) -> None:
    grouped: dict[str, list[PlannedAction]] = {"MOVE": [], "MARK_DUPLICATE": [], "NOOP": []}
    for action in planned_actions:
        if action.action_type in grouped:
            grouped[action.action_type].append(action)

    section_order = [("MOVE", "MOVE"), ("MARK_DUPLICATE", "DUPLICATE"), ("NOOP", "NOOP")]
    first_section = True
    for action_type, label in section_order:
        entries = grouped[action_type]
        if not entries:
            continue
        if not first_section:
            print()
        first_section = False
        print(label)
        for action in entries:
            print(f"  {action.source_path}")
            if action.action_type != "NOOP" and action.target_path:
                print(f"    → {action.target_path}")

    print()
    print("----------------------------------------")
    print("Summary")
    print(f"  Files applied: {summary.applied_count}")
    print(f"  Moves: {summary.moves_count}")
    print(f"  Duplicates: {summary.duplicates_count}")
    print(f"  No-op: {summary.noop_count}")
    print(f"  Skipped: {summary.skipped_count}")
    print(f"  Errors: {summary.errors_count}")
    print("----------------------------------------")
    print(f"Run ID: {run_id}")


def _plan_command(path_arg: str) -> int:
    path = Path(path_arg)
    if not path.exists():
        print(f"Path does not exist: {path}", file=sys.stderr)
        return 2

    files = _collect_input_files(path)
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    run_service = RunService(session_factory)
    planner = PlanningService(session_factory)

    run = run_service.create_run()
    summary = planner.plan_run(run.id, files)

    with session_factory() as session:
        planned_actions = session.scalars(
            select(PlannedAction)
            .where(PlannedAction.run_id == run.id)
            .order_by(PlannedAction.action_type.asc(), PlannedAction.source_path.asc(), PlannedAction.target_path.asc())
        ).all()

    _render_plan_output(run.id, planned_actions, summary)
    return 0


def _apply_command(run_id_arg: str) -> int:
    try:
        run_id = uuid.UUID(run_id_arg)
    except ValueError:
        print(f"Invalid run_id: {run_id_arg}", file=sys.stderr)
        return 2

    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    apply_service = ApplyService(session_factory)

    try:
        summary = apply_service.apply_run(run_id)
    except MediaManagerError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    with session_factory() as session:
        planned_actions = session.scalars(
            select(PlannedAction)
            .where(PlannedAction.run_id == run_id)
            .order_by(
                PlannedAction.action_type.asc(),
                PlannedAction.source_path.asc(),
                PlannedAction.target_path.asc(),
                PlannedAction.id.asc(),
            )
        ).all()

    _render_apply_output(run_id, planned_actions, summary)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="media-manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Create a deterministic plan for file organization.")
    plan_parser.add_argument("path", help="File or directory path to plan.")
    apply_parser = subparsers.add_parser("apply", help="Apply an existing planned run.")
    apply_parser.add_argument("run_id", help="Run identifier to apply.")

    args = parser.parse_args(argv)
    if args.command == "plan":
        return _plan_command(args.path)
    if args.command == "apply":
        return _apply_command(args.run_id)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
