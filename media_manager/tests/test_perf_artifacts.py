from __future__ import annotations

import json
from pathlib import Path

import pytest

from media_manager.app.core.perf_artifacts import (
    METRICS_VERSION,
    BASELINE_DIR,
    StageMetrics,
    artifact_to_ordered_dict,
    baseline_file_path,
    build_performance_artifact,
    load_all_baselines,
    load_baseline_json,
    read_performance_artifact_json,
    store_baseline_json,
    write_performance_artifact_json,
)


def _stage_sample() -> StageMetrics:
    return StageMetrics(
        duration_ms=12.5,
        substeps={
            "z_step": {"b": 2, "a": 1},
            "a_step": {"y": "two", "x": "one"},
        },
        counters={"z_counter": 2, "a_counter": 1},
        notes={"z_note": "z", "a_note": "a"},
    )


def test_artifact_contains_required_top_level_fields() -> None:
    artifact = build_performance_artifact(
        run_id="r-1",
        phase="phase9",
        dataset_id="dataset-1",
        env_class="ci",
        metrics_version=METRICS_VERSION,
        git_commit="abc1234",
        command_args=["ingest", "/tmp/data"],
        ingest=_stage_sample(),
    )
    payload = artifact_to_ordered_dict(artifact)
    assert payload["run_id"] == "r-1"
    assert payload["phase"] == "phase9"
    assert payload["dataset_id"] == "dataset-1"
    assert payload["env_class"] == "ci"
    assert payload["metrics_version"] == METRICS_VERSION
    assert payload["git_commit"] == "abc1234"
    assert payload["command_args"] == ["ingest", "/tmp/data"]


def test_stage_keys_always_present_even_when_none() -> None:
    artifact = build_performance_artifact(
        run_id="r-1",
        phase="phase9",
        dataset_id="dataset-1",
        env_class="ci",
        metrics_version=METRICS_VERSION,
        git_commit="abc1234",
        command_args=[],
    )
    payload = artifact_to_ordered_dict(artifact)
    assert "ingest" in payload
    assert "planner" in payload
    assert "apply" in payload
    assert payload["ingest"] is None
    assert payload["planner"] is None
    assert payload["apply"] is None


def test_deterministic_ordering_for_stages_and_nested_keys() -> None:
    artifact = build_performance_artifact(
        run_id="r-1",
        phase="phase9",
        dataset_id="dataset-1",
        env_class="ci",
        metrics_version=METRICS_VERSION,
        git_commit="abc1234",
        command_args=["plan"],
        ingest=_stage_sample(),
        planner=_stage_sample(),
        apply=_stage_sample(),
    )
    payload = artifact_to_ordered_dict(artifact)
    assert list(payload.keys()) == [
        "run_id",
        "phase",
        "dataset_id",
        "env_class",
        "metrics_version",
        "git_commit",
        "command_args",
        "ingest",
        "planner",
        "apply",
    ]
    ingest = payload["ingest"]
    assert ingest is not None
    assert list(ingest.keys()) == ["duration_ms", "substeps", "counters", "notes"]
    assert list(ingest["substeps"].keys()) == ["a_step", "z_step"]
    assert list(ingest["substeps"]["a_step"].keys()) == ["x", "y"]
    assert list(ingest["substeps"]["z_step"].keys()) == ["a", "b"]
    assert list(ingest["counters"].keys()) == ["a_counter", "z_counter"]
    assert list(ingest["notes"].keys()) == ["a_note", "z_note"]


def test_write_and_read_roundtrip_json(tmp_path: Path) -> None:
    artifact = build_performance_artifact(
        run_id="r 1",
        phase="phase9",
        dataset_id="dataset #1",
        env_class="ci/linux",
        metrics_version=METRICS_VERSION,
        git_commit="abc1234",
        command_args=["apply", "1234"],
        ingest=_stage_sample(),
    )
    out_path = write_performance_artifact_json(artifact, tmp_path)
    assert out_path.exists()
    loaded = read_performance_artifact_json(out_path)
    assert loaded["run_id"] == "r 1"
    assert loaded["dataset_id"] == "dataset #1"
    assert loaded["env_class"] == "ci/linux"


def test_baseline_loader_explicit_dataset_env_match(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baselines"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    path = baseline_file_path("dataset-1", "ci", baseline_dir)
    path.write_text(
        json.dumps({"dataset_id": "dataset-1", "env_class": "ci", "metrics_version": METRICS_VERSION}),
        encoding="utf-8",
    )

    loaded = load_baseline_json("dataset-1", "ci", baseline_dir)
    assert loaded["dataset_id"] == "dataset-1"
    assert loaded["env_class"] == "ci"
    assert loaded["metrics_version"] == METRICS_VERSION


def test_baseline_loader_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_baseline_json("missing-dataset", "ci", tmp_path / "baselines")


def test_load_all_baselines_returns_sorted_results(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baselines"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    (baseline_dir / "baseline_b_ci.json").write_text(
        json.dumps({"id": "b", "dataset_id": "b", "env_class": "ci", "metrics_version": METRICS_VERSION}),
        encoding="utf-8",
    )
    (baseline_dir / "baseline_a_ci.json").write_text(
        json.dumps({"id": "a", "dataset_id": "a", "env_class": "ci", "metrics_version": METRICS_VERSION}),
        encoding="utf-8",
    )
    (baseline_dir / "baseline_c_ci.json").write_text(
        json.dumps({"id": "c", "dataset_id": "c", "env_class": "ci", "metrics_version": METRICS_VERSION}),
        encoding="utf-8",
    )

    loaded = load_all_baselines(baseline_dir)
    assert [item["id"] for item in loaded] == ["a", "b", "c"]


def test_command_args_preserved_as_list_of_strings() -> None:
    artifact = build_performance_artifact(
        run_id="r-1",
        phase="phase9",
        dataset_id="dataset-1",
        env_class="ci",
        metrics_version=METRICS_VERSION,
        git_commit="abc1234",
        command_args=["ingest", 123],  # type: ignore[list-item]
    )
    assert artifact.command_args == ["ingest", "123"]


def test_metrics_version_pass_through() -> None:
    artifact = build_performance_artifact(
        run_id="r-1",
        phase="phase9",
        dataset_id="dataset-1",
        env_class="ci",
        metrics_version="phase9.custom.v2",
        git_commit="abc1234",
        command_args=[],
    )
    payload = artifact_to_ordered_dict(artifact)
    assert payload["metrics_version"] == "phase9.custom.v2"


def test_constants_exposed() -> None:
    assert METRICS_VERSION == "phase9.v1"
    assert BASELINE_DIR.as_posix() == "artifacts/perf/baselines"


def test_store_baseline_json_writes_expected_path(tmp_path: Path) -> None:
    payload = {"dataset_id": "dataset-1", "env_class": "ci", "metrics_version": METRICS_VERSION, "x": 1}
    path = store_baseline_json(payload, dataset_id="dataset-1", env_class="ci", baseline_dir=tmp_path)
    assert path == tmp_path / "baseline_dataset-1_ci.json"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["dataset_id"] == "dataset-1"


def test_store_baseline_json_rejects_missing_metrics_version(tmp_path: Path) -> None:
    payload = {"dataset_id": "dataset-1", "env_class": "ci"}
    with pytest.raises(ValueError, match="missing required field: metrics_version"):
        store_baseline_json(payload, dataset_id="dataset-1", env_class="ci", baseline_dir=tmp_path)


def test_store_baseline_json_rejects_metrics_version_mismatch(tmp_path: Path) -> None:
    payload = {"dataset_id": "dataset-1", "env_class": "ci", "metrics_version": "phase9.v0"}
    with pytest.raises(ValueError, match="metrics_version mismatch"):
        store_baseline_json(payload, dataset_id="dataset-1", env_class="ci", baseline_dir=tmp_path)


def test_store_baseline_json_rejects_dataset_env_mismatch(tmp_path: Path) -> None:
    payload = {"dataset_id": "dataset-x", "env_class": "ci", "metrics_version": METRICS_VERSION}
    with pytest.raises(ValueError, match="dataset_id mismatch"):
        store_baseline_json(payload, dataset_id="dataset-1", env_class="ci", baseline_dir=tmp_path)


def test_load_baseline_json_validates_metrics_version(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baselines"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    path = baseline_file_path("dataset-1", "ci", baseline_dir)
    path.write_text(
        json.dumps({"dataset_id": "dataset-1", "env_class": "ci", "metrics_version": "phase9.v0"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="metrics_version mismatch"):
        load_baseline_json("dataset-1", "ci", baseline_dir)


def test_load_baseline_json_can_skip_version_check_when_none(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baselines"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    path = baseline_file_path("dataset-1", "ci", baseline_dir)
    path.write_text(
        json.dumps({"dataset_id": "dataset-1", "env_class": "ci", "metrics_version": "phase9.v0"}),
        encoding="utf-8",
    )
    loaded = load_baseline_json("dataset-1", "ci", baseline_dir, expected_metrics_version=None)
    assert loaded["metrics_version"] == "phase9.v0"
