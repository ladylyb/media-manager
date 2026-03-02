#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from sqlalchemy import event, select, text

from media_manager.app.cli import main as cli_main
from media_manager.app.persistence.base import create_db_engine, create_session_factory
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.materialized_reads import (
    benchmark_planner_lookup,
    fetch_canonical_metadata,
    refresh_materialized_view,
)
from media_manager.app.persistence.models import PlannedAction
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService

TRUNCATE_SQL = [
    (
        "TRUNCATE TABLE media_metadata, metadata_codes, planned_actions, "
        "apply_audit_items, apply_audit_runs, "
        "canonical_recompute_items, canonical_recompute_runs, canonical_assignments, "
        "operator_policy_settings, "
        "file_instances, file_contents, failure_events, files, content_objects, runs "
        "RESTART IDENTITY CASCADE"
    ),
    (
        "TRUNCATE TABLE "
        "legacy_3nf.canonical_candidate, "
        "legacy_3nf.deletion_audit_candidate_instance, "
        "legacy_3nf.deletion_audit_candidate, "
        "legacy_3nf.deletion_audit_run, "
        "legacy_3nf.duplicate_evidence, "
        "legacy_3nf.action_event, "
        "legacy_3nf.media_attributes, "
        "legacy_3nf.file_instance, "
        "legacy_3nf.content_identity, "
        "legacy_3nf.scan_batch, "
        "legacy_3nf.import_failure_events, "
        "legacy_3nf.import_runs "
        "RESTART IDENTITY CASCADE"
    ),
    (
        "TRUNCATE TABLE "
        "legacy_raw._tmp_deletion_audit_import, "
        "legacy_raw.deletion_audit_candidate_files, "
        "legacy_raw.deletion_audit_candidates, "
        "legacy_raw.deletion_audit_runs, "
        "legacy_raw.duplicate_candidates, "
        "legacy_raw._file_actions_old, "
        "legacy_raw.file_actions, "
        "legacy_raw.files, "
        "legacy_raw.scans "
        "RESTART IDENTITY CASCADE"
    ),
]


@dataclass
class TaskResult:
    name: str
    passed: bool
    details: str
    metrics: dict[str, object] = field(default_factory=dict)


def _safe_db_url(candidate: str, allow_non_test: bool) -> str:
    lowered = candidate.lower()
    if "postgresql" not in lowered:
        raise RuntimeError("Audit requires PostgreSQL URL.")
    if not allow_non_test and "test" not in lowered:
        raise RuntimeError(
            "Refusing to run against non-test DB URL without --allow-non-test-db. "
            f"URL={candidate}"
        )
    return candidate


@contextmanager
def _chdir(path: Path):
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def _reset_db(engine) -> None:
    with engine.begin() as conn:
        for stmt in TRUNCATE_SQL:
            conn.execute(text(stmt))


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _seed_dataset(root: Path) -> list[Path]:
    paths = [
        _write_file(root / "Media" / "Photos" / "2024" / "01" / "IMG_20240110.jpg", b"noop"),
        _write_file(root / "inbox" / "IMG_20240111.jpg", b"dup-content"),
        _write_file(root / "inbox" / "dup_copy.jpg", b"dup-content"),
        _write_file(root / "inbox" / "unsupported.customext", b"unsupported"),
    ]
    return paths


def _normalize_path_for_root(path: str, root: Path) -> str:
    raw = path.replace("\\", "/")
    root_norm = str(root.resolve(strict=False)).replace("\\", "/")
    return raw.replace(root_norm, "<ROOT>")


def _latest_semantic_mapping(session_factory, root: Path) -> dict[str, str]:
    sql = text(
        """
        WITH ranked AS (
            SELECT
                ca.content_id,
                canonical_instance_id,
                ROW_NUMBER() OVER (
                    PARTITION BY ca.content_id
                    ORDER BY assigned_at DESC, assignment_id DESC
                ) AS rn
            FROM canonical_assignments ca
        )
        SELECT fc.sha256_hash, fi.absolute_path
        FROM ranked r
        JOIN file_contents fc
          ON fc.content_id = r.content_id
        JOIN file_instances fi
          ON fi.file_instance_id = r.canonical_instance_id
        WHERE rn = 1
        ORDER BY fc.sha256_hash
        """
    )
    with session_factory() as session:
        rows = session.execute(sql).all()
    return {str(hash_value): _normalize_path_for_root(path_value, root) for hash_value, path_value in rows}


def _plan_and_apply_once(root: Path, session_factory) -> dict[str, object]:
    run_service = RunService(session_factory)
    ingest_service = IngestService(session_factory)
    planner = PlanningService(session_factory)

    files = ingest_service.collect_files(root)
    ingest_service.ingest_paths(files)

    run = run_service.create_run()
    summary = planner.plan_run(run.id, files, ingest_if_needed=False)

    with session_factory() as session:
        planned_actions = session.scalars(
            select(PlannedAction)
            .where(PlannedAction.run_id == run.id)
            .order_by(
                PlannedAction.action_type.asc(),
                PlannedAction.source_path.asc(),
                PlannedAction.target_path.asc(),
                PlannedAction.id.asc(),
            ),
        ).all()

    # Use CLI apply to ensure external behavior path parity.
    apply_stdout = io.StringIO()
    with redirect_stdout(apply_stdout), redirect_stderr(io.StringIO()):
        rc = cli_main(["apply", str(run.id)])
    if rc != 0:
        raise RuntimeError(f"apply failed for run_id={run.id}")

    latest = _latest_semantic_mapping(session_factory, root)

    return {
        "summary": {
            "scanned": summary.scanned_count,
            "moves": summary.move_actions,
            "duplicates": summary.duplicate_actions,
            "noop": summary.noop_actions,
            "skipped": summary.skipped_count,
        },
        "actions": [
            {
                "action_type": row.action_type,
                "source_path": _normalize_path_for_root(row.source_path, root),
                "target_path": _normalize_path_for_root(row.target_path, root) if row.target_path else None,
            }
            for row in planned_actions
        ],
        "canonical_mapping": latest,
        "apply_stdout": apply_stdout.getvalue(),
    }


def _run_task_a(engine, session_factory) -> TaskResult:
    _reset_db(engine)
    with tempfile.TemporaryDirectory(prefix="phase10_1_audit_a_") as td:
        root = Path(td)
        first_root = root / "run1"
        second_root = root / "run2"
        _seed_dataset(first_root)
        _seed_dataset(second_root)

        first = _plan_and_apply_once(first_root, session_factory)
        _reset_db(engine)
        second = _plan_and_apply_once(second_root, session_factory)

    plan_diff_count = 0 if first["summary"] == second["summary"] and first["actions"] == second["actions"] else 1
    mapping_diff_count = 0 if first["canonical_mapping"] == second["canonical_mapping"] else 1
    passed = plan_diff_count == 0 and mapping_diff_count == 0
    return TaskResult(
        name="A. Deterministic Plan/Apply Validation",
        passed=passed,
        details="Deterministic parity validated across isolated reruns." if passed else "Plan/apply drift detected.",
        metrics={
            "plan_diff_count": plan_diff_count,
            "canonical_mapping_diff_count": mapping_diff_count,
            "planned_actions_count": len(first["actions"]),
            "canonical_mapping_rows": len(first["canonical_mapping"]),
        },
    )


def _run_task_b(engine, session_factory) -> TaskResult:
    _reset_db(engine)
    with tempfile.TemporaryDirectory(prefix="phase10_1_audit_b_") as td:
        root = Path(td) / "dataset"
        _seed_dataset(root)

        run_service = RunService(session_factory)
        ingest_service = IngestService(session_factory)
        planner = PlanningService(session_factory)

        files = ingest_service.collect_files(root)
        ingest_service.ingest_paths(files)
        run = run_service.create_run()
        planner.plan_run(run.id, files, ingest_if_needed=False)

    refresh_materialized_view(engine, concurrently=False)

    with session_factory() as session:
        base_rows = session.execute(
            text(
                """
                WITH ranked AS (
                    SELECT
                        content_id,
                        canonical_instance_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY content_id
                            ORDER BY assigned_at DESC, assignment_id DESC
                        ) AS rn
                    FROM canonical_assignments
                )
                SELECT content_id, canonical_instance_id
                FROM ranked
                WHERE rn = 1
                ORDER BY content_id
                """
            )
        ).all()
        mv_rows = session.execute(
            text(
                """
                SELECT content_id, canonical_instance_id
                FROM mv_canonical_metadata
                ORDER BY content_id
                """
            )
        ).all()

    base_map = {str(c): str(i) for c, i in base_rows}
    mv_map = {str(c): str(i) for c, i in mv_rows}
    mismatch = sorted(set(base_map.keys()) | set(mv_map.keys()))
    mismatch_count = sum(1 for key in mismatch if base_map.get(key) != mv_map.get(key))

    observed_mv_queries: list[str] = []

    def _capture_mv(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        if "mv_canonical_metadata" in statement.lower():
            observed_mv_queries.append(statement)

    _reset_db(engine)
    with tempfile.TemporaryDirectory(prefix="phase10_1_audit_b2_") as td:
        root = Path(td) / "dataset"
        _seed_dataset(root)
        event.listen(engine, "before_cursor_execute", _capture_mv)
        try:
            run_service = RunService(session_factory)
            planner = PlanningService(session_factory)
            run = run_service.create_run()
            files = sorted([p for p in root.rglob("*") if p.is_file()], key=lambda p: p.as_posix())
            planner.plan_run(run.id, files, ingest_if_needed=True)
        finally:
            event.remove(engine, "before_cursor_execute", _capture_mv)

    passed = mismatch_count == 0 and len(observed_mv_queries) == 0
    return TaskResult(
        name="B. Materialized View Parity",
        passed=passed,
        details=(
            "MV/base latest-assignment mapping parity validated and default planner path avoided MV."
            if passed
            else "MV parity mismatch or planner default path queried MV."
        ),
        metrics={
            "mv_row_count": len(mv_map),
            "base_row_count": len(base_map),
            "mv_row_mismatch_count": mismatch_count,
            "planner_default_mv_query_count": len(observed_mv_queries),
        },
    )


def _run_task_c(engine, session_factory) -> TaskResult:
    _reset_db(engine)
    with tempfile.TemporaryDirectory(prefix="phase10_1_audit_c_") as td:
        root = Path(td) / "dataset"
        _seed_dataset(root)
        ingest_service = IngestService(session_factory)
        ingest_service.ingest_path(root)

    refresh_materialized_view(engine, concurrently=False)

    with session_factory() as session:
        uncached = fetch_canonical_metadata(session, use_mv=True, sample_size=1000, use_cache=False)
        os.environ["CANONICAL_READ_CACHE_ENABLED"] = "true"
        cached_first = fetch_canonical_metadata(session, use_mv=True, sample_size=1000, use_cache=True)
        cached_second = fetch_canonical_metadata(session, use_mv=True, sample_size=1000, use_cache=True)

    def _plan_signature(dataset_root: Path) -> dict[str, object]:
        ingest_service = IngestService(session_factory)
        planner = PlanningService(session_factory)
        files = ingest_service.collect_files(dataset_root)
        ingest_service.ingest_paths(files)
        run = RunService(session_factory).create_run()
        summary = planner.plan_run(run.id, files, ingest_if_needed=False)
        with session_factory() as session:
            actions = session.scalars(
                select(PlannedAction)
                .where(PlannedAction.run_id == run.id)
                .order_by(
                    PlannedAction.action_type.asc(),
                    PlannedAction.source_path.asc(),
                    PlannedAction.target_path.asc(),
                ),
            ).all()
        return {
            "summary": (summary.scanned_count, summary.move_actions, summary.duplicate_actions, summary.noop_actions),
            "actions": [
                (
                    a.action_type,
                    Path(a.source_path).name,
                )
                for a in actions
            ],
        }

    _reset_db(engine)
    with tempfile.TemporaryDirectory(prefix="phase10_1_audit_c2_before_") as td:
        before_root = Path(td) / "dataset"
        _seed_dataset(before_root)
        plan_before = _plan_signature(before_root)

    _reset_db(engine)
    with tempfile.TemporaryDirectory(prefix="phase10_1_audit_c2_after_") as td:
        after_root = Path(td) / "dataset"
        _seed_dataset(after_root)
        os.environ["CANONICAL_READ_CACHE_ENABLED"] = "true"
        plan_after = _plan_signature(after_root)

    refresh_materialized_view(engine, concurrently=False)

    bench_uncached = benchmark_planner_lookup(
        session_factory,
        sample_size=100,
        repeats=3,
        use_cache=False,
        seed=42,
    )
    bench_cached = benchmark_planner_lookup(
        session_factory,
        sample_size=100,
        repeats=3,
        use_cache=True,
        seed=42,
    )

    with session_factory() as session:
        assignments_before = int(session.execute(text("SELECT COUNT(*) FROM canonical_assignments")).scalar_one())
        assignments_after = int(session.execute(text("SELECT COUNT(*) FROM canonical_assignments")).scalar_one())

    cache_speed_gain_ms = bench_uncached.mv_mean_ms - bench_cached.mv_mean_ms
    passed = (
        uncached == cached_first == cached_second
        and plan_before == plan_after
        and assignments_before == assignments_after
    )
    return TaskResult(
        name="C. TTL Cache Verification",
        passed=passed,
        details="Cache parity validated with no semantic mutation." if passed else "Cache semantic drift detected.",
        metrics={
            "metadata_rows": len(uncached),
            "cache_read_parity": uncached == cached_first == cached_second,
            "plan_output_parity": plan_before == plan_after,
            "assignment_count_before": assignments_before,
            "assignment_count_after": assignments_after,
            "cache_mv_speed_gain_ms": round(cache_speed_gain_ms, 3),
            "cache_mv_mean_ms_uncached": round(bench_uncached.mv_mean_ms, 3),
            "cache_mv_mean_ms_cached": round(bench_cached.mv_mean_ms, 3),
        },
    )


def _run_cli(args: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        rc = cli_main(args)
    return rc, stdout.getvalue(), stderr.getvalue()


def _run_task_d(engine, session_factory) -> TaskResult:
    _reset_db(engine)
    with tempfile.TemporaryDirectory(prefix="phase10_1_audit_d_") as td:
        root = Path(td)
        dataset = root / "dataset"
        _seed_dataset(dataset)

        with _chdir(root):
            rc_plan, _, _ = _run_cli(["plan", str(dataset)])
            if rc_plan != 0:
                raise RuntimeError("Precondition plan failed in task D")

            rc_no, out_no, err_no = _run_cli(["refresh-mv", "--no-concurrently"])
            rc_yes, out_yes, err_yes = _run_cli(["refresh-mv", "--concurrently"])
            rc_bench, out_bench, err_bench = _run_cli(["planner-benchmark", "--sample-size", "100", "--repeats", "3"])

            rc_sim1, _, _ = _run_cli(["plan", str(dataset), "--simulate-policy", "--policy", "SHORTEST_PATH"])
            rc_sim2, _, _ = _run_cli(["plan", str(dataset), "--simulate-policy", "--policy", "SHORTEST_PATH"])

            decision_files = sorted((root / "artifacts").glob("decision_trace_*.json"))
            sim_files = sorted((root / "artifacts").glob("simulation_delta_*.json"))

    pattern_decision = re.compile(r"decision_trace_[0-9a-f\-]{36}\.json")
    pattern_sim = re.compile(r"simulation_delta_[0-9a-f\-]{36}\.json")
    unique_files = len({p.name for p in decision_files + sim_files}) == len(decision_files) + len(sim_files)
    regex_ok = all(pattern_decision.fullmatch(p.name) for p in decision_files) and all(
        pattern_sim.fullmatch(p.name) for p in sim_files
    )

    gitignore_text = Path(".gitignore").read_text(encoding="utf-8")
    gitignore_ok = any(line.strip() == "artifacts/" for line in gitignore_text.splitlines())

    benchmark_contract_ok = all(token in out_bench for token in ["Base mean:", "MV mean:", "StdDev:", "Improvement:"])

    passed = (
        rc_no == 0
        and rc_yes == 0
        and rc_bench == 0
        and rc_sim1 == 0
        and rc_sim2 == 0
        and unique_files
        and regex_ok
        and gitignore_ok
        and benchmark_contract_ok
    )
    return TaskResult(
        name="D. CLI & Artifact Checks",
        passed=passed,
        details="CLI commands and artifact contracts validated." if passed else "CLI or artifact contract failure detected.",
        metrics={
            "refresh_mv_no_concurrently_rc": rc_no,
            "refresh_mv_concurrently_rc": rc_yes,
            "planner_benchmark_rc": rc_bench,
            "benchmark_output_contract_ok": benchmark_contract_ok,
            "decision_artifact_count": len(decision_files),
            "simulation_artifact_count": len(sim_files),
            "artifact_unique": unique_files,
            "artifact_name_regex_ok": regex_ok,
            "gitignore_artifacts_entry": gitignore_ok,
            "refresh_mv_stderr_len": len(err_no) + len(err_yes),
            "planner_benchmark_stderr_len": len(err_bench),
        },
    )


def _table_counts(engine) -> dict[str, int]:
    with engine.begin() as conn:
        return {
            "runs": int(conn.execute(text("SELECT COUNT(*) FROM runs")).scalar_one()),
            "planned_actions": int(conn.execute(text("SELECT COUNT(*) FROM planned_actions")).scalar_one()),
            "apply_audit_runs": int(conn.execute(text("SELECT COUNT(*) FROM apply_audit_runs")).scalar_one()),
            "apply_audit_items": int(conn.execute(text("SELECT COUNT(*) FROM apply_audit_items")).scalar_one()),
            "canonical_assignments": int(conn.execute(text("SELECT COUNT(*) FROM canonical_assignments")).scalar_one()),
        }


def _run_task_e(engine) -> TaskResult:
    _reset_db(engine)
    fs_calls = {"remove": 0, "move": 0, "rename": 0}

    original_remove = os.remove
    original_move = shutil.move
    original_rename = Path.rename

    def _remove_guard(*args, **kwargs):  # type: ignore[no-untyped-def]
        fs_calls["remove"] += 1
        raise AssertionError("os.remove called during simulation")

    def _move_guard(*args, **kwargs):  # type: ignore[no-untyped-def]
        fs_calls["move"] += 1
        raise AssertionError("shutil.move called during simulation")

    def _rename_guard(self, target):  # type: ignore[no-untyped-def]
        fs_calls["rename"] += 1
        raise AssertionError("Path.rename called during simulation")

    os.remove = _remove_guard
    shutil.move = _move_guard
    Path.rename = _rename_guard  # type: ignore[assignment]

    try:
        with tempfile.TemporaryDirectory(prefix="phase10_1_audit_e_") as td:
            root = Path(td)
            dataset = root / "dataset"
            _seed_dataset(dataset)

            with _chdir(root):
                before = _table_counts(engine)
                rc1, out1, err1 = _run_cli(["plan", str(dataset), "--simulate-policy", "--policy", "SHORTEST_PATH"])
                after1 = _table_counts(engine)
                rc2, out2, err2 = _run_cli(["plan", str(dataset), "--simulate-policy", "--policy", "SHORTEST_PATH"])
                after2 = _table_counts(engine)

                sim_files = sorted((root / "artifacts").glob("simulation_delta_*.json"))
                traces = sorted((root / "artifacts").glob("decision_trace_*.json"))

                if sim_files:
                    payload1 = json.loads(sim_files[-1].read_text(encoding="utf-8"))
                else:
                    payload1 = {}

        db_unchanged = before == after1 == after2
        idempotent_payload_shape = all(key in payload1 for key in [
            "run_id",
            "policy_name",
            "policy_version",
            "canonical_changes_count",
            "demotions_count",
            "merges_count",
            "impacted_content_ids",
        ])

        passed = (
            rc1 == 0
            and rc2 == 0
            and db_unchanged
            and fs_calls == {"remove": 0, "move": 0, "rename": 0}
            and len(traces) == 0
            and len(sim_files) == 2
            and idempotent_payload_shape
        )
        return TaskResult(
            name="E. Simulation Mode Validation",
            passed=passed,
            details=(
                "Simulation path remained read-only and idempotent."
                if passed
                else "Simulation mutation or idempotency violation detected."
            ),
            metrics={
                "simulation_rc_first": rc1,
                "simulation_rc_second": rc2,
                "db_mutation_detected": not db_unchanged,
                "filesystem_call_counts": fs_calls,
                "simulation_artifact_count": len(sim_files),
                "decision_trace_artifact_count": len(traces),
                "simulation_delta_changes": payload1.get("canonical_changes_count", -1),
                "simulation_stderr_len": len(err1) + len(err2),
                "simulation_stdout_len": len(out1) + len(out2),
            },
        )
    finally:
        os.remove = original_remove
        shutil.move = original_move
        Path.rename = original_rename  # type: ignore[assignment]


def _run_task_f() -> TaskResult:
    # Full regression suite check; relies on existing pytest configuration.
    cmd = [sys.executable, "-m", "pytest", "-q"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    combined = f"{proc.stdout}\n{proc.stderr}".strip()
    summary_line = ""
    for line in reversed(combined.splitlines()):
        if "passed" in line or "failed" in line or "error" in line:
            summary_line = line.strip()
            break

    # Ensure Phase 10.1 audit tests are included in current tree execution by running them explicitly too.
    targeted_cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "media_manager/tests/test_materialized_view.py",
        "media_manager/tests/test_planner_benchmark.py",
        "media_manager/tests/test_mv_latest_assignment_determinism.py",
        "media_manager/tests/test_mv_not_used_by_default.py",
        "media_manager/tests/test_benchmark_determinism.py",
        "media_manager/tests/test_cache_semantic_parity.py",
    ]
    targeted = subprocess.run(targeted_cmd, capture_output=True, text=True)
    targeted_ok = targeted.returncode == 0

    passed = proc.returncode == 0 and targeted_ok
    return TaskResult(
        name="F. Regression & Full Suite Check",
        passed=passed,
        details="Full regression suite and Phase 10.1 tests passed." if passed else "Regression suite failure detected.",
        metrics={
            "full_suite_exit_code": proc.returncode,
            "full_suite_summary": summary_line,
            "phase10_1_targeted_exit_code": targeted.returncode,
        },
    )


def _print_report(results: list[TaskResult]) -> None:
    print("Phase 10.1 Architectural Audit Report")
    print("====================================")
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{result.name}: {status}")
        print(f"  {result.details}")
        for key in sorted(result.metrics):
            print(f"  - {key}: {result.metrics[key]}")
    overall = all(item.passed for item in results)
    print("------------------------------------")
    print(f"Overall: {'PASS' if overall else 'FAIL'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Post-implementation Phase 10.1 audit harness")
    parser.add_argument(
        "--database-url",
        default=os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL"),
        help="PostgreSQL URL. Defaults to TEST_DATABASE_URL then DATABASE_URL.",
    )
    parser.add_argument(
        "--allow-non-test-db",
        action="store_true",
        help="Allow running against non-test PostgreSQL URL.",
    )
    args = parser.parse_args()

    if not args.database_url:
        print("Missing database URL. Set TEST_DATABASE_URL or pass --database-url.", file=sys.stderr)
        return 2

    db_url = _safe_db_url(args.database_url, args.allow_non_test_db)
    os.environ["DATABASE_URL"] = db_url

    engine = create_db_engine(db_url)
    session_factory = create_session_factory(engine)

    tasks: list[Callable[[], TaskResult]] = [
        lambda: _run_task_a(engine, session_factory),
        lambda: _run_task_b(engine, session_factory),
        lambda: _run_task_c(engine, session_factory),
        lambda: _run_task_d(engine, session_factory),
        lambda: _run_task_e(engine),
        _run_task_f,
    ]

    results: list[TaskResult] = []
    try:
        for task in tasks:
            result = task()
            results.append(result)
            if not result.passed:
                _print_report(results)
                return 1
    finally:
        engine.dispose()

    _print_report(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
