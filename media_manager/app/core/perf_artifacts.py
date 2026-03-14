"""Performance governance JSON artifact helpers for Phase 9.

This module is intentionally side-effect light and deterministic:
it serializes captured metrics into a stable schema and provides baseline
loading helpers for comparator modules.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

METRICS_VERSION: str = "phase9.v1"
BASELINE_DIR: Path = Path("artifacts/perf/baselines")


@dataclass(frozen=True)
class RunArtifactMetadata:
    """Top-level metadata for a performance artifact."""

    run_id: str
    phase: str
    dataset_id: str
    env_class: str
    metrics_version: str
    git_commit: str
    command_args: list[str]


@dataclass(frozen=True)
class StageMetrics:
    """Stage-specific performance metrics."""

    duration_ms: float | int | None
    substeps: dict[str, dict[str, float | int | str | None]]
    counters: dict[str, int | float]
    notes: dict[str, str | int | float | bool | None]


@dataclass(frozen=True)
class PerformanceArtifact:
    """Canonical performance artifact with fixed stage keys."""

    run_id: str
    phase: str
    dataset_id: str
    env_class: str
    metrics_version: str
    git_commit: str
    command_args: list[str]
    ingest: StageMetrics | None
    planner: StageMetrics | None
    apply: StageMetrics | None


def _require_non_empty(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _sorted_mapping(values: dict[str, Any]) -> dict[str, Any]:
    return {key: values[key] for key in sorted(values)}


def _canonical_stage(stage: StageMetrics) -> StageMetrics:
    substeps_sorted = {}
    for substep_name in sorted(stage.substeps):
        substeps_sorted[substep_name] = _sorted_mapping(stage.substeps[substep_name])
    return StageMetrics(
        duration_ms=stage.duration_ms,
        substeps=substeps_sorted,
        counters=_sorted_mapping(stage.counters),
        notes=_sorted_mapping(stage.notes),
    )


def build_performance_artifact(
    *,
    run_id: str,
    phase: str,
    dataset_id: str,
    env_class: str,
    metrics_version: str,
    git_commit: str,
    command_args: list[str],
    ingest: StageMetrics | None = None,
    planner: StageMetrics | None = None,
    apply: StageMetrics | None = None,
) -> PerformanceArtifact:
    """Build a validated, canonical `PerformanceArtifact` instance.

    Validation rules:
    - required top-level string identifiers must be non-empty
    - `command_args` must be a list
    - optional stage payloads are normalized to deterministic key ordering
    """

    if not isinstance(command_args, list):
        raise ValueError("command_args must be a list")

    normalized_args = [str(arg) for arg in command_args]
    return PerformanceArtifact(
        run_id=_require_non_empty("run_id", run_id),
        phase=_require_non_empty("phase", phase),
        dataset_id=_require_non_empty("dataset_id", dataset_id),
        env_class=_require_non_empty("env_class", env_class),
        metrics_version=_require_non_empty("metrics_version", metrics_version),
        git_commit=_require_non_empty("git_commit", git_commit),
        command_args=normalized_args,
        ingest=_canonical_stage(ingest) if ingest is not None else None,
        planner=_canonical_stage(planner) if planner is not None else None,
        apply=_canonical_stage(apply) if apply is not None else None,
    )


def _stage_to_ordered_dict(stage: StageMetrics | None) -> dict[str, Any] | None:
    if stage is None:
        return None
    return {
        "duration_ms": stage.duration_ms,
        "substeps": stage.substeps,
        "counters": stage.counters,
        "notes": stage.notes,
    }


def artifact_to_ordered_dict(artifact: PerformanceArtifact) -> dict[str, Any]:
    """Convert artifact to a dict with deterministic key ordering."""

    return {
        "run_id": artifact.run_id,
        "phase": artifact.phase,
        "dataset_id": artifact.dataset_id,
        "env_class": artifact.env_class,
        "metrics_version": artifact.metrics_version,
        "git_commit": artifact.git_commit,
        "command_args": list(artifact.command_args),
        "ingest": _stage_to_ordered_dict(artifact.ingest),
        "planner": _stage_to_ordered_dict(artifact.planner),
        "apply": _stage_to_ordered_dict(artifact.apply),
    }


def _safe_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    normalized = normalized.strip("._-")
    return normalized or "na"


def write_performance_artifact_json(
    artifact: PerformanceArtifact,
    out_dir: Path,
    *,
    filename_prefix: str = "perf_artifact",
) -> Path:
    """Persist a performance artifact JSON file and return its path."""

    out_dir.mkdir(parents=True, exist_ok=True)
    filename = (
        f"{_safe_name(filename_prefix)}_"
        f"{_safe_name(artifact.dataset_id)}_"
        f"{_safe_name(artifact.env_class)}_"
        f"{_safe_name(artifact.run_id)}.json"
    )
    out_path = out_dir / filename
    payload = artifact_to_ordered_dict(artifact)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    return out_path


def read_performance_artifact_json(path: Path) -> dict[str, Any]:
    """Read and parse an artifact JSON file for comparator consumption."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON artifact at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Artifact at {path} must decode to an object")
    return payload


def baseline_file_path(
    dataset_id: str,
    env_class: str,
    baseline_dir: Path = BASELINE_DIR,
) -> Path:
    """Return deterministic baseline file path for dataset/environment."""

    return baseline_dir / f"baseline_{_safe_name(dataset_id)}_{_safe_name(env_class)}.json"


def _validate_baseline_payload(
    payload: dict[str, Any],
    *,
    dataset_id: str,
    env_class: str,
    expected_metrics_version: str | None,
) -> None:
    required = ("dataset_id", "env_class", "metrics_version")
    for field in required:
        if field not in payload:
            raise ValueError(f"Baseline payload missing required field: {field}")
        if not isinstance(payload[field], str) or not payload[field].strip():
            raise ValueError(f"Baseline field {field} must be a non-empty string")

    if payload["dataset_id"] != dataset_id:
        raise ValueError(
            f"Baseline dataset_id mismatch: expected {dataset_id!r}, got {payload['dataset_id']!r}"
        )
    if payload["env_class"] != env_class:
        raise ValueError(
            f"Baseline env_class mismatch: expected {env_class!r}, got {payload['env_class']!r}"
        )

    if expected_metrics_version is not None and payload["metrics_version"] != expected_metrics_version:
        raise ValueError(
            "Baseline metrics_version mismatch: "
            f"expected {expected_metrics_version!r}, got {payload['metrics_version']!r}"
        )


def store_baseline_json(
    payload: dict[str, Any],
    *,
    dataset_id: str,
    env_class: str,
    baseline_dir: Path = BASELINE_DIR,
    expected_metrics_version: str = METRICS_VERSION,
) -> Path:
    """Persist a baseline JSON artifact for explicit dataset/environment keys."""

    if not isinstance(payload, dict):
        raise ValueError("Baseline payload must be an object")
    _validate_baseline_payload(
        payload,
        dataset_id=dataset_id,
        env_class=env_class,
        expected_metrics_version=expected_metrics_version,
    )
    baseline_dir.mkdir(parents=True, exist_ok=True)
    path = baseline_file_path(dataset_id, env_class, baseline_dir)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    return path


def load_baseline_json(
    dataset_id: str,
    env_class: str,
    baseline_dir: Path = BASELINE_DIR,
    expected_metrics_version: str | None = METRICS_VERSION,
) -> dict[str, Any]:
    """Load one explicit baseline JSON by dataset/environment key."""

    path = baseline_file_path(dataset_id, env_class, baseline_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"Baseline not found for dataset_id={dataset_id!r}, env_class={env_class!r} at {path}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid baseline JSON at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Baseline at {path} must decode to an object")
    _validate_baseline_payload(
        payload,
        dataset_id=dataset_id,
        env_class=env_class,
        expected_metrics_version=expected_metrics_version,
    )
    return payload


def load_all_baselines(baseline_dir: Path = BASELINE_DIR) -> list[dict[str, Any]]:
    """Load all baseline JSON files sorted by filename."""

    if not baseline_dir.exists():
        return []
    baselines: list[dict[str, Any]] = []
    for path in sorted(baseline_dir.glob("baseline_*.json"), key=lambda candidate: candidate.name):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid baseline JSON at {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Baseline at {path} must decode to an object")
        baselines.append(payload)
    return baselines
