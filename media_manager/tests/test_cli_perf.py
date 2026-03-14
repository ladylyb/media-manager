from __future__ import annotations

import json
import uuid
from pathlib import Path

from media_manager.app import cli
from media_manager.app.core import perf_cli
from media_manager.app.core.perf_artifacts import (
    METRICS_VERSION,
    StageMetrics,
    baseline_file_path,
    build_performance_artifact,
    store_baseline_json,
    write_performance_artifact_json,
)


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _make_stage(runtime_ms: float, db_ms: float, hit_rate: float, verification_failures: float = 0.0) -> StageMetrics:
    return StageMetrics(
        duration_ms=runtime_ms,
        substeps={},
        counters={
            "db_query_ms_total": db_ms,
            "hit_rate": hit_rate,
            "verification_failures_count": verification_failures,
        },
        notes={},
    )


def _write_artifact(run_dir: Path, *, dataset_id: str, env_class: str, runtime_ms: float) -> Path:
    artifact = build_performance_artifact(
        run_id=str(uuid.uuid4()),
        phase="perf-run",
        dataset_id=dataset_id,
        env_class=env_class,
        metrics_version=METRICS_VERSION,
        git_commit="abc123",
        command_args=["perf-run"],
        ingest=_make_stage(runtime_ms, 100.0, 80.0),
        planner=_make_stage(runtime_ms, 100.0, 80.0),
        apply=_make_stage(runtime_ms, 100.0, 80.0, verification_failures=0.0),
    )
    return write_performance_artifact_json(artifact, run_dir)


def _wire_perf_dirs(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    run_dir = tmp_path / "runs"
    baseline_dir = tmp_path / "baselines"
    monkeypatch.setattr(perf_cli, "PERF_RUN_DIR", run_dir)
    monkeypatch.setattr(perf_cli, "BASELINE_DIR", baseline_dir)
    return run_dir, baseline_dir


def test_perf_run_dry_run_generates_artifact_with_apply_null(
    tmp_path: Path, test_database_url: str, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    run_dir, _ = _wire_perf_dirs(monkeypatch, tmp_path)
    dataset = tmp_path / "dataset"
    _write_file(dataset / "a.jpg", b"a")
    _write_file(dataset / "b.jpg", b"b")

    exit_code = cli.main(
        ["perf-run", "--dataset", str(dataset), "--env-class", "ci", "--policy", "FIRST_SEEN", "--dry-run"]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PASS"
    assert payload["dry_run"] is True
    assert payload["counts"]["apply"] is None
    assert Path(payload["artifact_path"]).exists()
    assert len(list(run_dir.glob("perf_artifact_*.json"))) == 1


def test_perf_run_full_generates_artifact_with_all_stages(
    tmp_path: Path, test_database_url: str, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    _wire_perf_dirs(monkeypatch, tmp_path)
    dataset = tmp_path / "dataset"
    _write_file(dataset / "a.jpg", b"a")
    _write_file(dataset / "dup.jpg", b"a")

    exit_code = cli.main(["perf-run", "--dataset", str(dataset), "--env-class", "ci", "--policy", "FIRST_SEEN"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PASS"
    assert payload["dry_run"] is False
    assert payload["counts"]["apply"] is not None


def test_perf_compare_pass_returns_exit_0(tmp_path: Path, monkeypatch, capsys) -> None:
    run_dir, baseline_dir = _wire_perf_dirs(monkeypatch, tmp_path)
    dataset_id = "dataset-key"
    env_class = "ci"
    artifact_path = _write_artifact(run_dir, dataset_id=dataset_id, env_class=env_class, runtime_ms=100.0)
    current = json.loads(artifact_path.read_text(encoding="utf-8"))
    store_baseline_json(current, dataset_id=dataset_id, env_class=env_class, baseline_dir=baseline_dir)

    exit_code = cli.main(["perf-compare", "--dataset", dataset_id, "--env-class", env_class])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["overall_pass_fail"] == "PASS"


def test_perf_compare_fail_returns_exit_1(tmp_path: Path, monkeypatch, capsys) -> None:
    run_dir, baseline_dir = _wire_perf_dirs(monkeypatch, tmp_path)
    dataset_id = "dataset-key"
    env_class = "ci"
    current_path = _write_artifact(run_dir, dataset_id=dataset_id, env_class=env_class, runtime_ms=130.0)
    baseline_path = _write_artifact(run_dir, dataset_id=dataset_id, env_class=env_class, runtime_ms=100.0)
    baseline_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    store_baseline_json(baseline_payload, dataset_id=dataset_id, env_class=env_class, baseline_dir=baseline_dir)

    exit_code = cli.main(
        ["perf-compare", "--dataset", dataset_id, "--env-class", env_class, "--artifact", str(current_path)]
    )
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["overall_pass_fail"] == "FAIL"


def test_perf_refresh_baseline_writes_file(tmp_path: Path, monkeypatch, capsys) -> None:
    run_dir, baseline_dir = _wire_perf_dirs(monkeypatch, tmp_path)
    dataset_id = "dataset-key"
    env_class = "ci"
    artifact = _write_artifact(run_dir, dataset_id=dataset_id, env_class=env_class, runtime_ms=100.0)

    exit_code = cli.main(
        ["perf-refresh-baseline", "--dataset", dataset_id, "--env-class", env_class, "--artifact", str(artifact)]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "stored"
    assert baseline_file_path(dataset_id, env_class, baseline_dir).exists()


def test_perf_refresh_baseline_dry_run_no_write(tmp_path: Path, monkeypatch, capsys) -> None:
    run_dir, baseline_dir = _wire_perf_dirs(monkeypatch, tmp_path)
    dataset_id = "dataset-key"
    env_class = "ci"
    artifact = _write_artifact(run_dir, dataset_id=dataset_id, env_class=env_class, runtime_ms=100.0)

    exit_code = cli.main(
        [
            "perf-refresh-baseline",
            "--dataset",
            dataset_id,
            "--env-class",
            env_class,
            "--artifact",
            str(artifact),
            "--dry-run",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "validated"
    assert not baseline_file_path(dataset_id, env_class, baseline_dir).exists()


def test_perf_commands_use_deterministic_input_order(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    _write_file(dataset / "b.jpg", b"b")
    _write_file(dataset / "a.jpg", b"a")
    files = perf_cli.collect_dataset_files(dataset)
    assert [path.name for path in files] == ["a.jpg", "b.jpg"]


def test_perf_compare_structured_output_contains_required_fields(tmp_path: Path, monkeypatch, capsys) -> None:
    run_dir, baseline_dir = _wire_perf_dirs(monkeypatch, tmp_path)
    dataset_id = "dataset-key"
    env_class = "ci"
    artifact_path = _write_artifact(run_dir, dataset_id=dataset_id, env_class=env_class, runtime_ms=100.0)
    current = json.loads(artifact_path.read_text(encoding="utf-8"))
    store_baseline_json(current, dataset_id=dataset_id, env_class=env_class, baseline_dir=baseline_dir)

    exit_code = cli.main(["perf-compare", "--dataset", dataset_id, "--env-class", env_class])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    row = payload["results"][0]
    for key in ("stage_name", "metric_name", "baseline_value", "current_value", "delta", "pass_fail"):
        assert key in row


def test_perf_refresh_baseline_reports_metrics_version(tmp_path: Path, monkeypatch, capsys) -> None:
    run_dir, _ = _wire_perf_dirs(monkeypatch, tmp_path)
    dataset_id = "dataset-key"
    env_class = "ci"
    artifact = _write_artifact(run_dir, dataset_id=dataset_id, env_class=env_class, runtime_ms=100.0)

    exit_code = cli.main(
        ["perf-refresh-baseline", "--dataset", dataset_id, "--env-class", env_class, "--artifact", str(artifact)]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["metrics_version"] == METRICS_VERSION


def test_perf_compare_missing_baseline_returns_exit_2(tmp_path: Path, monkeypatch, capsys) -> None:
    run_dir, _ = _wire_perf_dirs(monkeypatch, tmp_path)
    dataset_id = "dataset-key"
    env_class = "ci"
    _write_artifact(run_dir, dataset_id=dataset_id, env_class=env_class, runtime_ms=100.0)

    exit_code = cli.main(["perf-compare", "--dataset", dataset_id, "--env-class", env_class])
    assert exit_code == 2
    stderr = capsys.readouterr().err
    assert "Baseline not found" in stderr
