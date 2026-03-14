from __future__ import annotations

from pathlib import Path

import media_manager.app.cli as cli_module
from media_manager.app.cli import main
import media_manager.app.persistence.materialized_reads as materialized_reads
from media_manager.app.core.ttl_cache import TTLCache
from media_manager.app.persistence.base import create_db_engine
from sqlalchemy import text


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _seed_and_refresh_mv(tmp_path: Path, test_database_url: str, monkeypatch) -> Path:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setattr(materialized_reads, "_READ_CACHE", TTLCache(ttl_seconds=60.0))
    root = tmp_path / "dataset"
    _write_file(root / "a" / "one.jpg", b"same")
    _write_file(root / "b" / "two.jpg", b"same")
    _write_file(root / "c" / "three.jpg", b"unique")
    assert main(["ingest", str(root)]) == 0
    assert main(["refresh-mv", "--no-concurrently"]) == 0
    return root


def test_quick_check_emits_expected_metric_lines_for_base_and_mv(
    tmp_path: Path,
    test_database_url: str,
    monkeypatch,
    capsys,
) -> None:
    _seed_and_refresh_mv(tmp_path, test_database_url, monkeypatch)
    run_id = "qc-lines"
    exit_code = main(["observability-quick-check", "--run-id", run_id, "--sample-size", "1000"])
    assert exit_code == 0

    stdout = capsys.readouterr().out
    for metric_name in (
        "canonical_read_cache_hits_total",
        "canonical_read_cache_misses_total",
        "canonical_read_cache_hit_ratio_percent",
    ):
        assert f'{metric_name}{{run_id="{run_id}",source="base"' in stdout
        assert f'{metric_name}{{run_id="{run_id}",source="mv"' in stdout
    assert "Metrics complete: True" in stdout


def test_quick_check_works_when_cache_env_disabled(
    tmp_path: Path,
    test_database_url: str,
    monkeypatch,
    capsys,
) -> None:
    _seed_and_refresh_mv(tmp_path, test_database_url, monkeypatch)
    monkeypatch.setenv("CANONICAL_READ_CACHE_ENABLED", "false")

    run_id = "qc-disabled"
    exit_code = main(["observability-quick-check", "--run-id", run_id])
    assert exit_code == 0
    stdout = capsys.readouterr().out
    assert f'canonical_read_cache_hit_ratio_percent{{run_id="{run_id}",source="base"' in stdout
    assert f'canonical_read_cache_hit_ratio_percent{{run_id="{run_id}",source="mv"' in stdout


def test_quick_check_does_not_mutate_planner_apply_state(
    tmp_path: Path,
    test_database_url: str,
    monkeypatch,
) -> None:
    _seed_and_refresh_mv(tmp_path, test_database_url, monkeypatch)
    engine = create_db_engine(test_database_url)
    with engine.begin() as conn:
        before = {
            "runs": int(conn.execute(text("SELECT COUNT(*) FROM runs")).scalar_one()),
            "planned_actions": int(conn.execute(text("SELECT COUNT(*) FROM planned_actions")).scalar_one()),
            "apply_audit_runs": int(conn.execute(text("SELECT COUNT(*) FROM apply_audit_runs")).scalar_one()),
            "apply_audit_items": int(conn.execute(text("SELECT COUNT(*) FROM apply_audit_items")).scalar_one()),
        }

    assert main(["observability-quick-check", "--run-id", "qc-no-mutate"]) == 0

    with engine.begin() as conn:
        after = {
            "runs": int(conn.execute(text("SELECT COUNT(*) FROM runs")).scalar_one()),
            "planned_actions": int(conn.execute(text("SELECT COUNT(*) FROM planned_actions")).scalar_one()),
            "apply_audit_runs": int(conn.execute(text("SELECT COUNT(*) FROM apply_audit_runs")).scalar_one()),
            "apply_audit_items": int(conn.execute(text("SELECT COUNT(*) FROM apply_audit_items")).scalar_one()),
        }
    assert before == after


def test_quick_check_returns_error_when_mv_read_fails(
    tmp_path: Path,
    test_database_url: str,
    monkeypatch,
    capsys,
) -> None:
    _seed_and_refresh_mv(tmp_path, test_database_url, monkeypatch)

    real_fetch = cli_module.fetch_canonical_metadata

    def _raise_for_mv(session, *, use_mv, sample_size, use_cache=None, metrics_run_id=None):  # type: ignore[no-untyped-def]
        if use_mv:
            raise RuntimeError("forced mv failure")
        return real_fetch(
            session,
            use_mv=use_mv,
            sample_size=sample_size,
            use_cache=use_cache,
            metrics_run_id=metrics_run_id,
        )

    monkeypatch.setattr(cli_module, "fetch_canonical_metadata", _raise_for_mv)

    exit_code = main(["observability-quick-check", "--run-id", "qc-mv-fail"])
    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "forced mv failure" in stderr
