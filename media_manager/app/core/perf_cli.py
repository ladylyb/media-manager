"""Internal legacy perf helpers for benchmarking only.

This module is not part of the supported application interface. It remains only
for narrow internal benchmarking tasks and may import persistence internals
directly.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from media_manager.app.core.errors import MediaManagerError
from media_manager.app.core.perf_artifacts import (
    BASELINE_DIR,
    METRICS_VERSION,
    StageMetrics,
    baseline_file_path,
    build_performance_artifact,
    load_baseline_json,
    read_performance_artifact_json,
    store_baseline_json,
    write_performance_artifact_json,
)
from media_manager.app.core.perf_comparator import compare_to_baseline
from media_manager.app.persistence.apply import ApplyService, ApplySummary
from media_manager.app.persistence.base import create_db_engine, create_session_factory
from media_manager.app.persistence.ingest import IngestService, IngestSummary
from media_manager.app.persistence.planner import PlanningService, PlanningSummary
from media_manager.app.persistence.runs import RunService

PERF_RUN_DIR = Path("artifacts/perf/runs")


def _path_sort_key(path: Path) -> str:
    return path.resolve(strict=False).as_posix()


def collect_dataset_files(dataset: Path) -> list[Path]:
    """Collect files from dataset path using deterministic ordering."""

    if dataset.is_file():
        return [dataset]
    return sorted((candidate for candidate in dataset.rglob("*") if candidate.is_file()), key=_path_sort_key)


def _git_commit() -> str:
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
        return out or "-"
    except Exception:
        return "-"


def _stage_from_ingest(summary: IngestSummary, *, policy: str) -> StageMetrics:
    return StageMetrics(
        duration_ms=summary.duration_s * 1000.0,
        substeps={},
        counters={
            "files_scanned": summary.files_scanned,
            "new_contents": summary.new_contents,
            "new_instances": summary.new_instances,
            "duplicates_detected": summary.duplicates_detected,
            "metadata_extracted": summary.metadata_extracted,
        },
        notes={"policy": policy},
    )


def _stage_from_plan(summary: PlanningSummary, *, policy: str) -> StageMetrics:
    return StageMetrics(
        duration_ms=None,
        substeps={},
        counters={
            "scanned_count": summary.scanned_count,
            "supported_count": summary.supported_count,
            "skipped_count": summary.skipped_count,
            "move_actions": summary.move_actions,
            "noop_actions": summary.noop_actions,
            "duplicate_actions": summary.duplicate_actions,
        },
        notes={"policy": policy},
    )


def _stage_from_apply(summary: ApplySummary, *, policy: str) -> StageMetrics:
    return StageMetrics(
        duration_ms=None,
        substeps={},
        counters={
            "applied_count": summary.applied_count,
            "skipped_count": summary.skipped_count,
            "duplicates_count": summary.duplicates_count,
            "noop_count": summary.noop_count,
            "errors_count": summary.errors_count,
            "moves_count": summary.moves_count,
        },
        notes={"policy": policy},
    )


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=False))


def _select_latest_artifact(dataset_id: str, env_class: str, *, run_dir: Path | None = None) -> Path:
    if run_dir is None:
        run_dir = PERF_RUN_DIR
    if not run_dir.exists():
        raise FileNotFoundError(f"No perf artifacts found at {run_dir}")
    candidates: list[Path] = []
    for candidate in sorted(run_dir.glob("perf_artifact_*.json"), key=lambda p: p.name):
        try:
            payload = read_performance_artifact_json(candidate)
        except Exception:
            continue
        if payload.get("dataset_id") == dataset_id and payload.get("env_class") == env_class:
            candidates.append(candidate)
    if not candidates:
        raise FileNotFoundError(
            f"No perf artifact found for dataset_id={dataset_id!r}, env_class={env_class!r} in {run_dir}"
        )
    return max(candidates, key=lambda p: (p.stat().st_mtime_ns, p.name))


def run_perf_run(
    *,
    dataset: str,
    env_class: str,
    policy: str,
    dry_run: bool,
    strict_metadata: bool,
    argv: list[str],
) -> int:
    """Run perf pipeline and emit a run artifact."""

    dataset_path = Path(dataset)
    if not dataset_path.exists():
        print(f"Path does not exist: {dataset_path}", file=sys.stderr)
        return 2

    files = collect_dataset_files(dataset_path)
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    run_service = RunService(session_factory)
    ingest_service = IngestService(session_factory)
    planner = PlanningService(session_factory)
    apply_service = ApplyService(session_factory)

    try:
        ingest_summary = ingest_service.ingest_paths(files)
        run = run_service.create_run()
        plan_summary = planner.plan_run(
            run.id,
            files,
            ingest_if_needed=False,
            strict_missing_metadata=strict_metadata,
        )
        apply_summary: ApplySummary | None = None
        if not dry_run:
            apply_summary = apply_service.apply_run(run.id)

        artifact = build_performance_artifact(
            run_id=str(run.id),
            phase="perf-run",
            dataset_id=str(dataset_path.resolve(strict=False)),
            env_class=env_class,
            metrics_version=METRICS_VERSION,
            git_commit=_git_commit(),
            command_args=argv,
            ingest=_stage_from_ingest(ingest_summary, policy=policy),
            planner=_stage_from_plan(plan_summary, policy=policy),
            apply=_stage_from_apply(apply_summary, policy=policy) if apply_summary is not None else None,
        )
        artifact_path = write_performance_artifact_json(artifact, PERF_RUN_DIR)
        summary_payload = {
            "status": "PASS",
            "run_id": str(run.id),
            "dataset_id": str(dataset_path.resolve(strict=False)),
            "env_class": env_class,
            "policy": policy,
            "dry_run": dry_run,
            "artifact_path": str(artifact_path),
            "counts": {
                "ingest": {
                    "files_scanned": ingest_summary.files_scanned,
                    "new_contents": ingest_summary.new_contents,
                    "new_instances": ingest_summary.new_instances,
                    "duplicates_detected": ingest_summary.duplicates_detected,
                },
                "planner": {
                    "scanned_count": plan_summary.scanned_count,
                    "move_actions": plan_summary.move_actions,
                    "duplicate_actions": plan_summary.duplicate_actions,
                    "noop_actions": plan_summary.noop_actions,
                    "skipped_count": plan_summary.skipped_count,
                },
                "apply": None
                if apply_summary is None
                else {
                    "applied_count": apply_summary.applied_count,
                    "moves_count": apply_summary.moves_count,
                    "duplicates_count": apply_summary.duplicates_count,
                    "noop_count": apply_summary.noop_count,
                    "errors_count": apply_summary.errors_count,
                    "skipped_count": apply_summary.skipped_count,
                },
            },
        }
        _print_json(summary_payload)
        return 0
    except MediaManagerError as exc:
        _print_json({"status": "FAIL", "error": str(exc)})
        return 1
    except Exception as exc:
        _print_json({"status": "FAIL", "error": str(exc)})
        return 1


def run_perf_compare(
    *,
    dataset: str,
    env_class: str,
    policy: str,
    dry_run: bool,
    artifact: str | None,
) -> int:
    """Compare current metrics artifact against baseline."""

    _ = policy
    _ = dry_run
    try:
        artifact_path = Path(artifact) if artifact else _select_latest_artifact(dataset, env_class)
        current_metrics = read_performance_artifact_json(artifact_path)
        baseline_metrics = load_baseline_json(dataset, env_class, baseline_dir=BASELINE_DIR)
        result = compare_to_baseline(current_metrics, baseline_metrics)
        summary = result.get("summary", {})
        payload = {
            "status": summary.get("overall_pass_fail", "FAIL"),
            "dataset_id": dataset,
            "env_class": env_class,
            "artifact_path": str(artifact_path),
            "summary": summary,
            "results": result.get("results", []),
        }
        _print_json(payload)
        return 0 if summary.get("overall_pass_fail") == "PASS" else 1
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        _print_json({"status": "FAIL", "error": str(exc)})
        return 1


def run_perf_refresh_baseline(
    *,
    dataset: str,
    env_class: str,
    policy: str,
    dry_run: bool,
    artifact: str | None,
) -> int:
    """Store selected metrics artifact as baseline."""

    _ = policy
    try:
        artifact_path = Path(artifact) if artifact else _select_latest_artifact(dataset, env_class)
        current_metrics = read_performance_artifact_json(artifact_path)
        target_path = baseline_file_path(dataset, env_class, BASELINE_DIR)
        if dry_run:
            if not isinstance(current_metrics, dict):
                raise ValueError("Artifact payload must be an object")
            for field in ("dataset_id", "env_class", "metrics_version"):
                if field not in current_metrics:
                    raise ValueError(f"Baseline payload missing required field: {field}")
            if current_metrics.get("dataset_id") != dataset:
                raise ValueError("Baseline dataset_id mismatch")
            if current_metrics.get("env_class") != env_class:
                raise ValueError("Baseline env_class mismatch")
            if current_metrics.get("metrics_version") != METRICS_VERSION:
                raise ValueError("Baseline metrics_version mismatch")
            payload = {
                "status": "PASS",
                "action": "validated",
                "artifact_path": str(artifact_path),
                "baseline_path": str(target_path),
                "metrics_version": current_metrics.get("metrics_version"),
            }
            _print_json(payload)
            return 0

        path = store_baseline_json(
            current_metrics,
            dataset_id=dataset,
            env_class=env_class,
            baseline_dir=BASELINE_DIR,
        )
        payload = {
            "status": "PASS",
            "action": "stored",
            "artifact_path": str(artifact_path),
            "baseline_path": str(path),
            "metrics_version": current_metrics.get("metrics_version"),
        }
        _print_json(payload)
        return 0
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        _print_json({"status": "FAIL", "error": str(exc)})
        return 1
