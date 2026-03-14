"""Phase 9 regression comparison helpers.

Compares current stage metrics against baseline metrics with deterministic
ordering and fixed governance thresholds.
"""

from __future__ import annotations

from typing import Any

STAGES: tuple[str, ...] = ("ingest", "planner", "apply")
METRICS_ORDER: tuple[str, ...] = (
    "runtime_ms",
    "db_query_ms_total",
    "cache_hit_rate",
    "verification_failures_count",
)

RUNTIME_SLOWDOWN_THRESHOLD_PCT = 20.0
DB_TIME_SLOWDOWN_THRESHOLD_PCT = 20.0
CACHE_HIT_DROP_THRESHOLD_PCT = 15.0


def _to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _to_stage_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _extract_stage_metric(stage_payload: dict[str, Any], metric_name: str) -> float | None:
    counters = stage_payload.get("counters")
    counters_payload = counters if isinstance(counters, dict) else {}

    if metric_name == "runtime_ms":
        return _to_number(stage_payload.get("duration_ms"))
    if metric_name == "db_query_ms_total":
        direct = _to_number(stage_payload.get("db_query_ms_total"))
        return direct if direct is not None else _to_number(counters_payload.get("db_query_ms_total"))
    if metric_name == "cache_hit_rate":
        direct = _to_number(stage_payload.get("hit_rate"))
        value = direct if direct is not None else _to_number(counters_payload.get("hit_rate"))
        if value is None:
            return None
        return value * 100.0 if value <= 1.0 else value
    if metric_name == "verification_failures_count":
        direct = _to_number(stage_payload.get("verification_failures_count"))
        value = (
            direct
            if direct is not None
            else _to_number(counters_payload.get("verification_failures_count"))
        )
        if value is None:
            return 0.0
        return value
    return None


def _make_result_row(
    *,
    stage_name: str,
    metric_name: str,
    baseline_value: float | int | None,
    current_value: float | int | None,
    delta: float | int | None,
    pass_fail: str,
    rule: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "stage_name": stage_name,
        "metric_name": metric_name,
        "baseline_value": baseline_value,
        "current_value": current_value,
        "delta": delta,
        "pass_fail": pass_fail,
        "rule": rule,
        "reason": reason,
    }


def _compare_runtime_or_db(
    *,
    stage_name: str,
    metric_name: str,
    baseline_value: float | None,
    current_value: float | None,
    threshold_pct: float,
    rule_name: str,
) -> dict[str, Any]:
    if baseline_value is None or current_value is None:
        return _make_result_row(
            stage_name=stage_name,
            metric_name=metric_name,
            baseline_value=baseline_value,
            current_value=current_value,
            delta=None,
            pass_fail="FAIL",
            rule=rule_name,
            reason="missing_or_invalid_metric",
        )
    if baseline_value <= 0:
        return _make_result_row(
            stage_name=stage_name,
            metric_name=metric_name,
            baseline_value=baseline_value,
            current_value=current_value,
            delta=None,
            pass_fail="FAIL",
            rule=rule_name,
            reason="invalid_baseline_value",
        )
    delta_pct = ((current_value - baseline_value) / baseline_value) * 100.0
    pass_fail = "PASS" if delta_pct <= threshold_pct else "FAIL"
    reason = "within_threshold" if pass_fail == "PASS" else "threshold_exceeded"
    return _make_result_row(
        stage_name=stage_name,
        metric_name=metric_name,
        baseline_value=baseline_value,
        current_value=current_value,
        delta=delta_pct,
        pass_fail=pass_fail,
        rule=rule_name,
        reason=reason,
    )


def _compare_cache_hit(
    *,
    stage_name: str,
    baseline_value: float | None,
    current_value: float | None,
) -> dict[str, Any]:
    if baseline_value is None or current_value is None:
        return _make_result_row(
            stage_name=stage_name,
            metric_name="cache_hit_rate",
            baseline_value=baseline_value,
            current_value=current_value,
            delta=None,
            pass_fail="FAIL",
            rule="cache_hit_drop_le_15pct",
            reason="missing_or_invalid_metric",
        )
    drop_pp = baseline_value - current_value
    pass_fail = "PASS" if drop_pp <= CACHE_HIT_DROP_THRESHOLD_PCT else "FAIL"
    reason = "within_threshold" if pass_fail == "PASS" else "threshold_exceeded"
    return _make_result_row(
        stage_name=stage_name,
        metric_name="cache_hit_rate",
        baseline_value=baseline_value,
        current_value=current_value,
        delta=drop_pp,
        pass_fail=pass_fail,
        rule="cache_hit_drop_le_15pct",
        reason=reason,
    )


def _compare_verification_failures(
    *,
    stage_name: str,
    baseline_value: float | None,
    current_value: float | None,
) -> dict[str, Any]:
    if current_value is None:
        return _make_result_row(
            stage_name=stage_name,
            metric_name="verification_failures_count",
            baseline_value=baseline_value,
            current_value=current_value,
            delta=None,
            pass_fail="FAIL",
            rule="verification_failures_must_equal_0",
            reason="missing_or_invalid_metric",
        )
    pass_fail = "PASS" if current_value <= 0 else "FAIL"
    return _make_result_row(
        stage_name=stage_name,
        metric_name="verification_failures_count",
        baseline_value=baseline_value,
        current_value=current_value,
        delta=current_value,
        pass_fail=pass_fail,
        rule="verification_failures_must_equal_0",
        reason="hard_fail_triggered" if pass_fail == "FAIL" else "no_verification_failures",
    )


def compare_to_baseline(current_metrics: dict, baseline_metrics: dict) -> dict:
    """Compare current stage metrics against baseline metrics.

    Returns deterministic per-stage verdict rows and summary pass/fail output.
    """

    if not isinstance(current_metrics, dict):
        raise ValueError("current_metrics must be object")
    if not isinstance(baseline_metrics, dict):
        raise ValueError("baseline_metrics must be object")

    results: list[dict[str, Any]] = []
    hard_fail_triggered = False

    for stage_name in STAGES:
        current_stage = _to_stage_payload(current_metrics.get(stage_name))
        baseline_stage = _to_stage_payload(baseline_metrics.get(stage_name))

        runtime_row = _compare_runtime_or_db(
            stage_name=stage_name,
            metric_name="runtime_ms",
            baseline_value=_extract_stage_metric(baseline_stage, "runtime_ms"),
            current_value=_extract_stage_metric(current_stage, "runtime_ms"),
            threshold_pct=RUNTIME_SLOWDOWN_THRESHOLD_PCT,
            rule_name="runtime_slowdown_le_20pct",
        )
        results.append(runtime_row)

        db_row = _compare_runtime_or_db(
            stage_name=stage_name,
            metric_name="db_query_ms_total",
            baseline_value=_extract_stage_metric(baseline_stage, "db_query_ms_total"),
            current_value=_extract_stage_metric(current_stage, "db_query_ms_total"),
            threshold_pct=DB_TIME_SLOWDOWN_THRESHOLD_PCT,
            rule_name="db_time_slowdown_le_20pct",
        )
        results.append(db_row)

        cache_row = _compare_cache_hit(
            stage_name=stage_name,
            baseline_value=_extract_stage_metric(baseline_stage, "cache_hit_rate"),
            current_value=_extract_stage_metric(current_stage, "cache_hit_rate"),
        )
        results.append(cache_row)

        verification_row = _compare_verification_failures(
            stage_name=stage_name,
            baseline_value=_extract_stage_metric(baseline_stage, "verification_failures_count"),
            current_value=_extract_stage_metric(current_stage, "verification_failures_count"),
        )
        results.append(verification_row)
        if verification_row["pass_fail"] == "FAIL":
            hard_fail_triggered = True

    failed_checks = sum(1 for row in results if row["pass_fail"] == "FAIL")
    summary = {
        "overall_pass_fail": "FAIL" if failed_checks > 0 else "PASS",
        "total_checks": len(results),
        "failed_checks": failed_checks,
        "hard_fail_triggered": hard_fail_triggered,
    }
    return {"summary": summary, "results": results}
