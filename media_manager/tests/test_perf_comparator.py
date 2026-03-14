from __future__ import annotations

from media_manager.app.core.perf_comparator import compare_to_baseline


def _metrics(
    *,
    runtime_ms: float = 100.0,
    db_ms: float = 50.0,
    hit_rate: float = 80.0,
    verification_failures: float = 0.0,
) -> dict:
    return {
        "duration_ms": runtime_ms,
        "db_query_ms_total": db_ms,
        "hit_rate": hit_rate,
        "verification_failures_count": verification_failures,
    }


def _pack(stage_payload: dict) -> dict:
    return {"ingest": stage_payload, "planner": stage_payload, "apply": stage_payload}


def test_compare_to_baseline_all_pass() -> None:
    baseline = _pack(_metrics())
    current = _pack(_metrics(runtime_ms=110.0, db_ms=55.0, hit_rate=75.0, verification_failures=0.0))
    result = compare_to_baseline(current, baseline)
    assert result["summary"]["overall_pass_fail"] == "PASS"
    assert result["summary"]["failed_checks"] == 0


def test_runtime_slowdown_over_20_fails() -> None:
    baseline = _pack(_metrics(runtime_ms=100.0))
    current = _pack(_metrics(runtime_ms=121.0))
    result = compare_to_baseline(current, baseline)
    runtime_rows = [r for r in result["results"] if r["metric_name"] == "runtime_ms"]
    assert any(row["pass_fail"] == "FAIL" for row in runtime_rows)
    assert result["summary"]["overall_pass_fail"] == "FAIL"


def test_db_time_over_20_fails() -> None:
    baseline = _pack(_metrics(db_ms=50.0))
    current = _pack(_metrics(db_ms=61.0))
    result = compare_to_baseline(current, baseline)
    db_rows = [r for r in result["results"] if r["metric_name"] == "db_query_ms_total"]
    assert any(row["pass_fail"] == "FAIL" for row in db_rows)


def test_cache_hit_drop_over_15_fails() -> None:
    baseline = _pack(_metrics(hit_rate=80.0))
    current = _pack(_metrics(hit_rate=64.0))
    result = compare_to_baseline(current, baseline)
    cache_rows = [r for r in result["results"] if r["metric_name"] == "cache_hit_rate"]
    assert any(row["pass_fail"] == "FAIL" for row in cache_rows)


def test_verification_failure_hard_fail() -> None:
    baseline = _pack(_metrics(verification_failures=0.0))
    current = _pack(_metrics(verification_failures=1.0))
    result = compare_to_baseline(current, baseline)
    verification_rows = [r for r in result["results"] if r["metric_name"] == "verification_failures_count"]
    assert any(row["pass_fail"] == "FAIL" for row in verification_rows)
    assert result["summary"]["hard_fail_triggered"] is True
    assert result["summary"]["overall_pass_fail"] == "FAIL"


def test_missing_stage_metrics_fail_deterministically() -> None:
    baseline = {"ingest": _metrics(), "planner": _metrics(), "apply": _metrics()}
    current = {"ingest": _metrics()}
    result = compare_to_baseline(current, baseline)
    planner_runtime = next(
        r for r in result["results"] if r["stage_name"] == "planner" and r["metric_name"] == "runtime_ms"
    )
    assert planner_runtime["pass_fail"] == "FAIL"
    assert planner_runtime["reason"] == "missing_or_invalid_metric"


def test_missing_or_invalid_metric_values_fail() -> None:
    baseline = _pack(_metrics())
    current = _pack({"duration_ms": "bad", "db_query_ms_total": 10.0, "hit_rate": 90.0})
    result = compare_to_baseline(current, baseline)
    runtime_row = next(r for r in result["results"] if r["metric_name"] == "runtime_ms")
    assert runtime_row["pass_fail"] == "FAIL"
    assert runtime_row["reason"] == "missing_or_invalid_metric"


def test_deterministic_output_order() -> None:
    baseline = _pack(_metrics())
    current = _pack(_metrics())
    first = compare_to_baseline(current, baseline)
    second = compare_to_baseline(current, baseline)
    assert first == second
    first_rows = first["results"]
    assert [row["stage_name"] for row in first_rows[:4]] == ["ingest", "ingest", "ingest", "ingest"]
    assert [row["metric_name"] for row in first_rows[:4]] == [
        "runtime_ms",
        "db_query_ms_total",
        "cache_hit_rate",
        "verification_failures_count",
    ]


def test_fractional_hit_rate_normalized() -> None:
    baseline = _pack(_metrics(hit_rate=0.80))
    current = _pack(_metrics(hit_rate=0.65))
    result = compare_to_baseline(current, baseline)
    cache_row = next(r for r in result["results"] if r["stage_name"] == "ingest" and r["metric_name"] == "cache_hit_rate")
    assert cache_row["baseline_value"] == 80.0
    assert cache_row["current_value"] == 65.0
    assert cache_row["pass_fail"] == "PASS"


def test_baseline_zero_runtime_fails_runtime_check() -> None:
    baseline = _pack(_metrics(runtime_ms=0.0))
    current = _pack(_metrics(runtime_ms=10.0))
    result = compare_to_baseline(current, baseline)
    runtime_row = next(r for r in result["results"] if r["stage_name"] == "ingest" and r["metric_name"] == "runtime_ms")
    assert runtime_row["pass_fail"] == "FAIL"
    assert runtime_row["reason"] == "invalid_baseline_value"


def test_result_row_schema_contains_required_fields() -> None:
    baseline = _pack(_metrics())
    current = _pack(_metrics())
    result = compare_to_baseline(current, baseline)
    row = result["results"][0]
    for key in ("stage_name", "metric_name", "baseline_value", "current_value", "delta", "pass_fail"):
        assert key in row
