from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from media_manager.app.canonical.context import CanonicalContext
from media_manager.app.canonical.factory import build_canonical_policy
from media_manager.app.core import perf_cli
from media_manager.app.core.errors import MediaManagerError
from media_manager.app.persistence.apply import ApplyService
from media_manager.app.persistence.base import create_db_engine, create_session_factory
from media_manager.app.persistence.canonicalization import RecomputeMode, recompute_canonical_assignments
from media_manager.app.persistence.decision_intelligence import (
    explain_file_from_latest_trace,
    load_latest_decision_trace,
    simulate_policy_delta,
    write_simulation_delta_artifact,
)
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.legacy_import import LegacyImportService
from media_manager.app.persistence.materialized_reads import (
    benchmark_planner_lookup,
    fetch_canonical_metadata,
    refresh_materialized_view,
)
from media_manager.app.persistence.models import PlannedAction
from media_manager.app.persistence.models import TagSource
from media_manager.app.observability import generate_metrics_text, start_metrics_http_server_if_enabled
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService
from media_manager.app.persistence.tag_enrichment import (
    EnrichmentScope,
    TagEnrichmentCommand,
    run_tag_enrichment,
)


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
        if action.action_type in {"MOVE", "RENAME"}:
            grouped["MOVE"].append(action)
        elif action.action_type in {"MARK_DUPLICATE", "COLLISION_RESOLVED"}:
            grouped["MARK_DUPLICATE"].append(action)
        elif action.action_type in {"NOOP", "SKIP"}:
            grouped["NOOP"].append(action)

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
            if action.action_type not in {"NOOP", "SKIP"} and action.target_path:
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
        if action.action_type in {"MOVE", "RENAME"}:
            grouped["MOVE"].append(action)
        elif action.action_type in {"MARK_DUPLICATE", "COLLISION_RESOLVED"}:
            grouped["MARK_DUPLICATE"].append(action)
        elif action.action_type in {"NOOP", "SKIP"}:
            grouped["NOOP"].append(action)

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
            if action.action_type not in {"NOOP", "SKIP"} and action.target_path:
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


def _render_ingest_output(summary) -> None:
    print("----------------------------------------")
    print("Ingest Summary")
    print(f"  Files scanned: {summary.files_scanned}")
    print(f"  New contents: {summary.new_contents}")
    print(f"  New instances: {summary.new_instances}")
    print(f"  Duplicates detected: {summary.duplicates_detected}")
    print(f"  Metadata extracted: {summary.metadata_extracted}")
    print(f"  Duration (s): {summary.duration_s:.3f}")
    print("----------------------------------------")


def _render_canonical_recompute_output(summary) -> None:
    print("----------------------------------------")
    print("Canonical Recompute Summary")
    print(f"  Run ID: {summary.run_id}")
    print(f"  Status: {summary.status}")
    print(f"  Duplicate contents scanned: {summary.scanned_count}")
    print(f"  Assignments changed: {summary.changed_count}")
    print(f"  Assignments applied: {summary.applied_count}")
    print(f"  Failed contents: {summary.failed_count}")
    if summary.changed_content_ids:
        print("  Changed content IDs:")
        for content_id in summary.changed_content_ids:
            print(f"    {content_id}")
    if summary.failed_content_ids:
        print("  Failed content IDs:")
        for content_id in summary.failed_content_ids:
            print(f"    {content_id}")
    print("----------------------------------------")


def _render_policy_simulation_output(delta, artifact_path: Path) -> None:
    print("----------------------------------------")
    print("Policy Simulation Summary")
    print(f"  Run ID: {delta.run_id}")
    print(f"  Policy: {delta.policy_name} ({delta.policy_version})")
    print(f"  Canonical Changes: {delta.canonical_changes_count}")
    print(f"  Merges: {delta.merges_count}")
    print(f"  Demotions: {delta.demotions_count}")
    print(f"  Impacted Content IDs: {len(delta.impacted_content_ids)}")
    print(f"  Artifact: {artifact_path}")
    print("----------------------------------------")


def _render_file_explanation(payload: dict[str, object]) -> None:
    print("----------------------------------------")
    print("File Decision Explanation")
    print(f"  Run ID: {payload.get('run_id')}")
    print(f"  Content ID: {payload.get('content_id')}")
    print(f"  File ID: {payload.get('file_id')}")
    print(f"  Is Canonical: {payload.get('is_canonical')}")
    print(f"  Canonical Instance: {payload.get('canonical_instance_id')}")
    print(f"  Decision Reason: {payload.get('decision_reason')}")
    print(f"  Tie Breaker: {payload.get('tie_breaker_used')}")
    print("  Rules:")
    for rule in payload.get("applied_policy_rules", []):
        print(f"    - {rule}")
    print("  Candidates:")
    canonical_id = str(payload.get("canonical_instance_id"))
    file_id = str(payload.get("file_id"))
    for candidate in payload.get("candidate_instance_ids", []):
        marker = ""
        if str(candidate) == canonical_id:
            marker = " (canonical)"
        if str(candidate) == file_id and marker:
            marker += " [queried]"
        elif str(candidate) == file_id:
            marker = " [queried]"
        print(f"    - {candidate}{marker}")
    print("----------------------------------------")


def _render_legacy_import_output(summary) -> None:
    print("----------------------------------------")
    print("Legacy Import Summary")
    print(f"  Import run ID: {summary.import_run_id}")
    print(f"  State: {summary.state}")
    if summary.raw_counts:
        print("  Raw row counts:")
        for table_name in sorted(summary.raw_counts):
            print(f"    {table_name}: {summary.raw_counts[table_name]}")
    print(f"  Verification failures: {len(summary.verification_failures)}")
    print("----------------------------------------")


def _render_mv_refresh_output(summary) -> None:
    print("----------------------------------------")
    print("Materialized View Refresh Summary")
    print("  View: mv_canonical_metadata")
    print(f"  Mode: {'CONCURRENTLY' if summary.concurrently else 'STANDARD'}")
    print(f"  Scheduled flag: {summary.scheduled}")
    if summary.schedule_label:
        print(f"  Schedule label: {summary.schedule_label}")
    print("----------------------------------------")


def _render_planner_benchmark_output(summary) -> None:
    print("----------------------------------------")
    print("Planner Benchmark")
    print(f"Base mean: {summary.base_mean_ms:.3f} ms")
    print(f"MV mean: {summary.mv_mean_ms:.3f} ms")
    print(f"StdDev: {summary.stddev_ms:.3f} ms")
    print(f"Improvement: {summary.improvement_pct:.2f}%")
    print("----------------------------------------")


def _extract_metric_lines_for_run_id(run_id: str) -> list[str]:
    metric_names = (
        "canonical_read_cache_hits_total",
        "canonical_read_cache_misses_total",
        "canonical_read_cache_hit_ratio_percent",
    )
    payload = generate_metrics_text().decode("utf-8", errors="ignore")
    lines: list[str] = []
    for line in payload.splitlines():
        if not line or line.startswith("#"):
            continue
        if not any(line.startswith(metric_name) for metric_name in metric_names):
            continue
        if f'run_id="{run_id}"' not in line:
            continue
        lines.append(line)
    return sorted(lines)


def _render_observability_quick_check_output(
    *,
    run_id: str,
    sample_size: int,
    base_rows: int,
    mv_rows: int,
    metric_lines: list[str],
    complete: bool,
) -> None:
    print("----------------------------------------")
    print("Observability Quick Check")
    print(f"  Run ID: {run_id}")
    print(f"  Sample size: {sample_size}")
    print(f"  Base rows read: {base_rows}")
    print(f"  MV rows read: {mv_rows}")
    print(f"  Metrics complete: {complete}")
    print("----------------------------------------")
    print("Matching metric lines:")
    for line in metric_lines:
        print(f"  {line}")
    print("----------------------------------------")


def _render_tag_enrichment_output(summary) -> None:
    print("----------------------------------------")
    print("Tag Enrichment Summary")
    print(f"  Run ID: {summary.run_id}")
    print(f"  Scope: {summary.scope}")
    print(f"  Status: {summary.status}")
    print(f"  Items processed: {summary.number_of_items_processed}")
    print(f"  Failed items: {summary.failed_items}")
    print(f"  Average confidence: {summary.average_confidence if summary.average_confidence is not None else 'n/a'}")
    print(f"  Duration (ms): {summary.duration_ms}")
    print(f"  Timestamp: {summary.timestamp.isoformat()}")
    print("----------------------------------------")


def _tag_enrich_command(
    *,
    run_all: bool,
    canonical_id: str | None,
    batch_size: int,
    source: str,
) -> int:
    if run_all == (canonical_id is not None):
        print("Specify exactly one of --all or --canonical-id.", file=sys.stderr)
        return 2
    if batch_size <= 0:
        print("--batch-size must be > 0.", file=sys.stderr)
        return 2
    try:
        source_value = TagSource(source).value
    except Exception:
        print(f"Invalid --source value: {source}", file=sys.stderr)
        return 2

    target_id: uuid.UUID | None = None
    if canonical_id is not None:
        try:
            target_id = uuid.UUID(canonical_id)
        except ValueError:
            print(f"Invalid --canonical-id UUID: {canonical_id}", file=sys.stderr)
            return 2

    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    command = TagEnrichmentCommand(
        scope=EnrichmentScope.ALL if run_all else EnrichmentScope.SINGLE,
        canonical_id=target_id,
        batch_size=batch_size,
        source=TagSource(source_value),
    )
    try:
        summary = run_tag_enrichment(session_factory, command)
    except MediaManagerError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _render_tag_enrichment_output(summary)
    return 0


def _observability_quick_check_command(*, run_id: str | None, sample_size: int) -> int:
    normalized_sample_size = max(int(sample_size), 1)
    normalized_run_id = str(run_id).strip() if run_id is not None else ""
    if not normalized_run_id:
        normalized_run_id = f"obs-quickcheck-{uuid.uuid4()}"

    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            base_rows = fetch_canonical_metadata(
                session,
                use_mv=False,
                sample_size=normalized_sample_size,
                use_cache=True,
                metrics_run_id=normalized_run_id,
            )
            # Trigger one hit per source so all cache metric families are visible.
            fetch_canonical_metadata(
                session,
                use_mv=False,
                sample_size=normalized_sample_size,
                use_cache=True,
                metrics_run_id=normalized_run_id,
            )
            fetch_canonical_metadata(
                session,
                use_mv=True,
                sample_size=normalized_sample_size,
                use_cache=True,
                metrics_run_id=normalized_run_id,
            )
            mv_rows = fetch_canonical_metadata(
                session,
                use_mv=True,
                sample_size=normalized_sample_size,
                use_cache=True,
                metrics_run_id=normalized_run_id,
            )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    metric_lines = _extract_metric_lines_for_run_id(normalized_run_id)
    expected_tokens = tuple(
        f'{metric_name}{{run_id="{normalized_run_id}",source="{source}"'
        for metric_name in (
            "canonical_read_cache_hits_total",
            "canonical_read_cache_misses_total",
            "canonical_read_cache_hit_ratio_percent",
        )
        for source in ("base", "mv")
    )
    complete = all(any(token in line for line in metric_lines) for token in expected_tokens)
    _render_observability_quick_check_output(
        run_id=normalized_run_id,
        sample_size=normalized_sample_size,
        base_rows=len(base_rows),
        mv_rows=len(mv_rows),
        metric_lines=metric_lines,
        complete=complete,
    )
    if not complete:
        print("Missing expected canonical cache metric lines for this run_id.", file=sys.stderr)
        return 1
    return 0


def _legacy_import_command(
    *,
    sqlite_path: str,
    pg_url: str | None,
    raw_schema: str,
    normalized_schema: str,
    import_run_id: str | None,
    source_db_name: str | None,
) -> int:
    path = Path(sqlite_path)
    if not path.exists():
        print(f"SQLite path does not exist: {path}", file=sys.stderr)
        return 2

    parsed_run_id: uuid.UUID | None = None
    if import_run_id:
        try:
            parsed_run_id = uuid.UUID(import_run_id)
        except ValueError:
            print(f"Invalid import_run_id: {import_run_id}", file=sys.stderr)
            return 2

    engine = create_db_engine(pg_url)
    service = LegacyImportService(engine, raw_schema=raw_schema, normalized_schema=normalized_schema)
    try:
        summary = service.import_sqlite(
            path,
            import_run_id=parsed_run_id,
            source_db_name=source_db_name,
        )
    except MediaManagerError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    _render_legacy_import_output(summary)
    return 0


def _refresh_mv_command(
    *,
    concurrently: bool,
    scheduled: bool,
    schedule_label: str | None,
) -> int:
    engine = create_db_engine()
    try:
        # Advisory-only scheduling mode in this phase:
        # no background scheduler/trigger is created here.
        summary = refresh_materialized_view(
            engine,
            concurrently=concurrently,
            scheduled=scheduled,
            schedule_label=schedule_label,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    _render_mv_refresh_output(summary)
    return 0


def _planner_benchmark_command(
    *,
    sample_size: int,
    repeats: int,
    use_cache: bool,
    seed: int,
) -> int:
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    try:
        summary = benchmark_planner_lookup(
            session_factory,
            sample_size=sample_size,
            repeats=repeats,
            use_cache=use_cache,
            seed=seed,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    _render_planner_benchmark_output(summary)
    return 0


def _explain_file_command(file_id: str) -> int:
    latest = load_latest_decision_trace()
    if latest is None:
        print("No decision trace artifact available.", file=sys.stderr)
        return 1
    payload = explain_file_from_latest_trace(file_id=file_id)
    if payload is None:
        print(f"File not found in latest decision trace: {file_id}", file=sys.stderr)
        return 1
    _render_file_explanation(payload)
    return 0


def _plan_command(
    path_arg: str,
    *,
    strict_metadata: bool = False,
    simulate_policy: bool = False,
    policy_name: str | None = None,
    preferred_roots: list[str] | None = None,
) -> int:
    path = Path(path_arg)
    if not path.exists():
        print(f"Path does not exist: {path}", file=sys.stderr)
        return 2

    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    if simulate_policy:
        selected_policy = policy_name or "FIRST_SEEN"
        try:
            policy = build_canonical_policy(selected_policy)
        except MediaManagerError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        context = CanonicalContext(preferred_roots=tuple(Path(root) for root in (preferred_roots or [])))
        try:
            delta = simulate_policy_delta(
                session_factory,
                policy=policy,
                context=context,
            )
        except MediaManagerError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1
        artifact_path = write_simulation_delta_artifact(delta)
        _render_policy_simulation_output(delta, artifact_path)
        return 0

    run_service = RunService(session_factory)
    ingest_service = IngestService(session_factory)
    planner = PlanningService(session_factory)

    ingest_files = _collect_input_files(path)
    ingest_service.ingest_paths(ingest_files)

    run = run_service.create_run()
    summary = planner.plan_run(
        run.id,
        ingest_files,
        ingest_if_needed=False,
        strict_missing_metadata=strict_metadata,
    )

    with session_factory() as session:
        planned_actions = session.scalars(
            select(PlannedAction)
            .where(PlannedAction.run_id == run.id)
            .order_by(PlannedAction.action_type.asc(), PlannedAction.source_path.asc(), PlannedAction.target_path.asc())
        ).all()

    _render_plan_output(run.id, planned_actions, summary)
    return 0


def _apply_command(run_id_arg: str, *, collision_mode: str = "rename") -> int:
    try:
        run_id = uuid.UUID(run_id_arg)
    except ValueError:
        print(f"Invalid run_id: {run_id_arg}", file=sys.stderr)
        return 2

    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    apply_service = ApplyService(session_factory)

    try:
        summary = apply_service.apply_run(run_id, collision_mode=collision_mode)  # type: ignore[arg-type]
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


def _ingest_command(path_arg: str) -> int:
    path = Path(path_arg)
    if not path.exists():
        print(f"Path does not exist: {path}", file=sys.stderr)
        return 2

    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    ingest_service = IngestService(session_factory)
    summary = ingest_service.ingest_path(path)
    _render_ingest_output(summary)
    return 0


def _canonical_recompute_command(
    *,
    policy_name: str,
    dry_run: bool,
    apply: bool,
    preferred_roots: list[str],
) -> int:
    if dry_run and apply:
        print("Specify only one of --dry-run or --apply.", file=sys.stderr)
        return 2

    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    mode = RecomputeMode.APPLY if apply else RecomputeMode.DRY_RUN
    try:
        policy = build_canonical_policy(policy_name)
    except MediaManagerError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    context = CanonicalContext(preferred_roots=tuple(Path(root) for root in preferred_roots))
    try:
        summary = recompute_canonical_assignments(
            session_factory,
            policy=policy,
            context=context,
            mode=mode,
        )
    except MediaManagerError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    _render_canonical_recompute_output(summary)
    return 0


def main(argv: list[str] | None = None) -> int:
    # Optional, non-blocking metrics endpoint for CLI-driven deployments.
    try:
        start_metrics_http_server_if_enabled()
    except Exception:
        # Observability must not block CLI command execution.
        pass

    parser = argparse.ArgumentParser(prog="media-manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Create a deterministic plan for file organization.")
    plan_parser.add_argument("path", help="File or directory path to plan.")
    plan_parser.add_argument(
        "--strict-metadata",
        action="store_true",
        help="Raise on missing required metadata codes during planning.",
    )
    plan_parser.add_argument(
        "--simulate-policy",
        action="store_true",
        help="Run policy simulation only (no planner/apply mutation).",
    )
    plan_parser.add_argument(
        "--policy",
        help="Canonical policy name for simulation mode (e.g. FIRST_SEEN, PREFER_ROOT, SHORTEST_PATH).",
    )
    plan_parser.add_argument(
        "--preferred-root",
        action="append",
        default=[],
        help="Preferred root path for PREFER_ROOT simulation policy. Can be provided multiple times.",
    )
    ingest_parser = subparsers.add_parser("ingest", help="Ingest files into logical content/instance tables.")
    ingest_parser.add_argument("path", help="File or directory path to ingest.")
    apply_parser = subparsers.add_parser("apply", help="Apply an existing planned run.")
    apply_parser.add_argument("run_id", help="Run identifier to apply.")
    apply_parser.add_argument(
        "--collision-mode",
        choices=["rename", "skip", "fail"],
        default="rename",
        help="Collision behavior when target path already exists.",
    )
    canonical_parser = subparsers.add_parser("canonical", help="Canonicalization commands.")
    canonical_subparsers = canonical_parser.add_subparsers(dest="canonical_command", required=True)
    canonical_recompute = canonical_subparsers.add_parser(
        "recompute",
        help="Deterministically recompute canonical assignments for duplicate contents.",
    )
    canonical_recompute.add_argument("--policy", required=True, help="Canonical policy name.")
    canonical_recompute.add_argument("--dry-run", action="store_true", help="Compute diff without appending assignments.")
    canonical_recompute.add_argument("--apply", action="store_true", help="Append changed canonical assignments.")
    canonical_recompute.add_argument(
        "--preferred-root",
        action="append",
        default=[],
        help="Preferred root path for PREFER_ROOT policy. Can be provided multiple times.",
    )
    perf_run_parser = subparsers.add_parser(
        "perf-run",
        help="Run ingest/plan/apply perf workflow and emit performance artifact JSON.",
    )
    perf_run_parser.add_argument("--dataset", required=True, help="Dataset path to process.")
    perf_run_parser.add_argument("--env-class", required=True, help="Environment class label (e.g., ci/local).")
    perf_run_parser.add_argument("--policy", default="FIRST_SEEN", help="Policy label for perf metadata context.")
    perf_run_parser.add_argument("--dry-run", action="store_true", help="Run ingest+plan only (skip apply).")
    perf_run_parser.add_argument(
        "--strict-metadata",
        action="store_true",
        help="Raise on missing required metadata codes during planning.",
    )

    perf_compare_parser = subparsers.add_parser(
        "perf-compare",
        help="Compare current perf artifact against baseline.",
    )
    perf_compare_parser.add_argument("--dataset", required=True, help="Dataset id key for baseline lookup.")
    perf_compare_parser.add_argument("--env-class", required=True, help="Environment class label.")
    perf_compare_parser.add_argument("--artifact", help="Optional current artifact path.")
    perf_compare_parser.add_argument("--policy", default="FIRST_SEEN", help="Policy label passthrough.")
    perf_compare_parser.add_argument("--dry-run", action="store_true", help="No-op flag for workflow parity.")

    perf_refresh_parser = subparsers.add_parser(
        "perf-refresh-baseline",
        help="Store current perf artifact as baseline for dataset/env.",
    )
    perf_refresh_parser.add_argument("--dataset", required=True, help="Dataset id key.")
    perf_refresh_parser.add_argument("--env-class", required=True, help="Environment class label.")
    perf_refresh_parser.add_argument("--artifact", help="Optional current artifact path.")
    perf_refresh_parser.add_argument("--policy", default="FIRST_SEEN", help="Policy label passthrough.")
    perf_refresh_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate baseline write contract without persisting.",
    )
    legacy_import_parser = subparsers.add_parser(
        "legacy-import",
        help="One-off import of legacy SQLite DB into legacy_raw and legacy_3nf schemas.",
    )
    legacy_import_parser.add_argument("--sqlite-path", required=True, help="Path to legacy SQLite database file.")
    legacy_import_parser.add_argument("--pg-url", help="Optional PostgreSQL URL override. Defaults to DATABASE_URL.")
    legacy_import_parser.add_argument("--raw-schema", default="legacy_raw", help="Raw mirror schema name.")
    legacy_import_parser.add_argument(
        "--normalized-schema",
        default="legacy_3nf",
        help="Normalized legacy schema name.",
    )
    legacy_import_parser.add_argument("--import-run-id", help="Optional stable import run UUID for resume/idempotency.")
    legacy_import_parser.add_argument("--source-db-name", help="Optional source database label.")
    explain_file_parser = subparsers.add_parser(
        "explain-file",
        help="Explain canonical decision for a file instance from latest decision trace artifact.",
    )
    explain_file_parser.add_argument("file_id", help="File instance UUID.")
    refresh_mv_parser = subparsers.add_parser(
        "refresh-mv",
        help="Refresh optional mv_canonical_metadata materialized view.",
    )
    refresh_mv_parser.add_argument(
        "--concurrently",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use REFRESH MATERIALIZED VIEW CONCURRENTLY (default: true).",
    )
    refresh_mv_parser.add_argument(
        "--scheduled",
        action="store_true",
        help="Advisory schedule mode only (still performs one refresh in this phase).",
    )
    refresh_mv_parser.add_argument("--schedule-label", help="Optional schedule strategy label for logs/output.")
    planner_benchmark_parser = subparsers.add_parser(
        "planner-benchmark",
        help="Compare canonical metadata lookup cost between base tables and MV.",
    )
    planner_benchmark_parser.add_argument("--sample-size", type=int, default=1000, help="Max canonical rows to query.")
    planner_benchmark_parser.add_argument("--repeats", type=int, default=5, help="Benchmark repeat count.")
    planner_benchmark_parser.add_argument("--seed", type=int, default=42, help="Deterministic benchmark seed.")
    planner_benchmark_parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Enable optional in-memory canonical read cache for MV lookup.",
    )
    observability_quick_check_parser = subparsers.add_parser(
        "observability-quick-check",
        help="Run one base+MV canonical metadata read and print matching Prometheus lines.",
    )
    observability_quick_check_parser.add_argument(
        "--run-id",
        help="Optional explicit run_id label for filtering emitted metric lines.",
    )
    observability_quick_check_parser.add_argument(
        "--sample-size",
        type=int,
        default=1000,
        help="Maximum canonical metadata rows to read per source.",
    )
    tag_enrich_parser = subparsers.add_parser(
        "tag-enrich",
        help="Manually run deterministic tag enrichment for canonical items.",
    )
    tag_enrich_parser.add_argument(
        "--all",
        action="store_true",
        help="Enrich all current canonical content ids.",
    )
    tag_enrich_parser.add_argument(
        "--canonical-id",
        help="Single canonical content id (file_contents.content_id) to enrich.",
    )
    tag_enrich_parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Deterministic batch size for enrichment processing.",
    )
    tag_enrich_parser.add_argument(
        "--source",
        choices=[member.value for member in TagSource],
        default=TagSource.SYSTEM.value,
        help="Tag source label for enrichment writes.",
    )

    args = parser.parse_args(argv)
    if args.command == "plan":
        return _plan_command(
            args.path,
            strict_metadata=args.strict_metadata,
            simulate_policy=args.simulate_policy,
            policy_name=args.policy,
            preferred_roots=args.preferred_root,
        )
    if args.command == "ingest":
        return _ingest_command(args.path)
    if args.command == "apply":
        return _apply_command(args.run_id, collision_mode=args.collision_mode)
    if args.command == "canonical" and args.canonical_command == "recompute":
        return _canonical_recompute_command(
            policy_name=args.policy,
            dry_run=args.dry_run,
            apply=args.apply,
            preferred_roots=args.preferred_root,
        )
    if args.command == "perf-run":
        return perf_cli.run_perf_run(
            dataset=args.dataset,
            env_class=args.env_class,
            policy=args.policy,
            dry_run=args.dry_run,
            strict_metadata=args.strict_metadata,
            argv=argv or sys.argv[1:],
        )
    if args.command == "perf-compare":
        return perf_cli.run_perf_compare(
            dataset=args.dataset,
            env_class=args.env_class,
            policy=args.policy,
            dry_run=args.dry_run,
            artifact=args.artifact,
        )
    if args.command == "perf-refresh-baseline":
        return perf_cli.run_perf_refresh_baseline(
            dataset=args.dataset,
            env_class=args.env_class,
            policy=args.policy,
            dry_run=args.dry_run,
            artifact=args.artifact,
        )
    if args.command == "legacy-import":
        return _legacy_import_command(
            sqlite_path=args.sqlite_path,
            pg_url=args.pg_url,
            raw_schema=args.raw_schema,
            normalized_schema=args.normalized_schema,
            import_run_id=args.import_run_id,
            source_db_name=args.source_db_name,
        )
    if args.command == "explain-file":
        return _explain_file_command(args.file_id)
    if args.command == "refresh-mv":
        return _refresh_mv_command(
            concurrently=args.concurrently,
            scheduled=args.scheduled,
            schedule_label=args.schedule_label,
        )
    if args.command == "planner-benchmark":
        return _planner_benchmark_command(
            sample_size=args.sample_size,
            repeats=args.repeats,
            use_cache=args.use_cache,
            seed=args.seed,
        )
    if args.command == "observability-quick-check":
        return _observability_quick_check_command(
            run_id=args.run_id,
            sample_size=args.sample_size,
        )
    if args.command == "tag-enrich":
        return _tag_enrich_command(
            run_all=args.all,
            canonical_id=args.canonical_id,
            batch_size=args.batch_size,
            source=args.source,
        )

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
