"""Phase 9 batch tuning utilities.

This module evaluates candidate batch sizes using deterministic ordering,
aggregates runtime/throughput statistics, and recommends a safe default.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median, pstdev
from typing import Any, Callable, Sequence

from media_manager.app.core.logging_config import get_logger

logger = get_logger(__name__)

CANDIDATE_BATCH_SIZES: tuple[int, ...] = (100, 250, 500, 1000, 2000, 5000)
MIN_REPEATS: int = 3
THROUGHPUT_FRACTION_THRESHOLD: float = 0.95
P95_STABILITY_CV_THRESHOLD: float = 0.10


@dataclass(frozen=True)
class BatchTrialSample:
    """Single measured trial for one batch size."""

    batch_size: int
    repeat_index: int
    runtime_ms: float
    files_processed: int
    throughput_fps: float


@dataclass(frozen=True)
class BatchAggregate:
    """Aggregate metrics for a candidate batch size."""

    batch_size: int
    runs: int
    runtime_ms_p50: float
    runtime_ms_p95: float
    runtime_ms_cv: float
    throughput_fps_p50: float
    throughput_fps_p95: float
    stable_p95: bool


@dataclass(frozen=True)
class BatchRecommendation:
    """Recommended batch size and safe operating range."""

    recommended_batch_size: int
    safe_range_min: int
    safe_range_max: int
    max_throughput_fps_p50: float
    eligible_batch_sizes: list[int]
    selection_reason: str


@dataclass(frozen=True)
class BatchTuningReport:
    """Top-level report for a batch tuning run."""

    dataset_id: str
    env_class: str
    policy_name: str
    candidate_batch_sizes: list[int]
    repeats: int
    aggregates: list[BatchAggregate]
    recommendation: BatchRecommendation


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * q))
    idx = max(0, min(idx, len(ordered) - 1))
    return float(ordered[idx])


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(median(values))


def _coefficient_of_variation(values: list[float]) -> float:
    if not values:
        return 0.0
    avg = mean(values)
    if avg == 0:
        return 0.0
    return float(pstdev(values) / avg)


def _validate_candidate_sizes(candidate_batch_sizes: Sequence[int]) -> list[int]:
    normalized: list[int] = sorted(set(candidate_batch_sizes))
    if not normalized:
        raise ValueError("candidate_batch_sizes must not be empty")
    if any(not isinstance(size, int) or size <= 0 for size in normalized):
        raise ValueError("candidate_batch_sizes must contain only positive integers")
    return normalized


def _build_aggregate(batch_size: int, samples: list[BatchTrialSample]) -> BatchAggregate:
    runtime_values = [sample.runtime_ms for sample in samples]
    throughput_values = [sample.throughput_fps for sample in samples]
    runtime_cv = _coefficient_of_variation(runtime_values)
    return BatchAggregate(
        batch_size=batch_size,
        runs=len(samples),
        runtime_ms_p50=_median(runtime_values),
        runtime_ms_p95=_percentile(runtime_values, 0.95),
        runtime_ms_cv=runtime_cv,
        throughput_fps_p50=_median(throughput_values),
        throughput_fps_p95=_percentile(throughput_values, 0.95),
        stable_p95=runtime_cv <= P95_STABILITY_CV_THRESHOLD,
    )


def recommend_batch_size(aggregates: Sequence[BatchAggregate]) -> BatchRecommendation:
    """Recommend a safe batch size from aggregate metrics.

    Selection rules:
    1. Consider stable candidates (`runtime_ms_cv <= 0.10`).
    2. Within stable candidates, mark eligible sizes whose throughput p50
       is at least 95% of the max stable throughput p50.
    3. Recommend the smallest eligible size.
    """

    ordered = sorted(aggregates, key=lambda row: row.batch_size)
    if not ordered:
        raise ValueError("aggregates must not be empty")

    stable = [row for row in ordered if row.stable_p95]
    if stable:
        max_throughput = max(row.throughput_fps_p50 for row in stable)
        threshold = max_throughput * THROUGHPUT_FRACTION_THRESHOLD
        eligible = [row for row in stable if row.throughput_fps_p50 >= threshold]
        if eligible:
            recommended = min(eligible, key=lambda row: row.batch_size)
            eligible_sizes = [row.batch_size for row in eligible]
            return BatchRecommendation(
                recommended_batch_size=recommended.batch_size,
                safe_range_min=min(eligible_sizes),
                safe_range_max=max(eligible_sizes),
                max_throughput_fps_p50=max_throughput,
                eligible_batch_sizes=eligible_sizes,
                selection_reason="smallest_within_95pct_of_max_stable_throughput",
            )

        # Defensive fallback if no candidate passes threshold filtering.
        best_stable = max(stable, key=lambda row: (row.throughput_fps_p50, -row.batch_size))
        return BatchRecommendation(
            recommended_batch_size=best_stable.batch_size,
            safe_range_min=best_stable.batch_size,
            safe_range_max=best_stable.batch_size,
            max_throughput_fps_p50=max_throughput,
            eligible_batch_sizes=[best_stable.batch_size],
            selection_reason="fallback_best_stable_by_throughput",
        )

    best_any = max(ordered, key=lambda row: (row.throughput_fps_p50, -row.batch_size))
    return BatchRecommendation(
        recommended_batch_size=best_any.batch_size,
        safe_range_min=best_any.batch_size,
        safe_range_max=best_any.batch_size,
        max_throughput_fps_p50=best_any.throughput_fps_p50,
        eligible_batch_sizes=[best_any.batch_size],
        selection_reason="fallback_no_stable_candidates",
    )


def run_batch_tuning(
    *,
    runner: Callable[[int], tuple[float, int]],
    dataset_id: str,
    env_class: str,
    policy_name: str = "-",
    candidate_batch_sizes: Sequence[int] = CANDIDATE_BATCH_SIZES,
    repeats: int = MIN_REPEATS,
) -> BatchTuningReport:
    """Run deterministic batch-size trials and return aggregate recommendation."""

    if repeats < MIN_REPEATS:
        raise ValueError(f"repeats must be >= {MIN_REPEATS}")

    normalized_sizes = _validate_candidate_sizes(candidate_batch_sizes)
    aggregate_rows: list[BatchAggregate] = []

    for batch_size in normalized_sizes:
        samples: list[BatchTrialSample] = []
        for repeat_index in range(1, repeats + 1):
            runtime_ms_raw, files_processed_raw = runner(batch_size)
            runtime_ms = float(runtime_ms_raw)
            files_processed = int(files_processed_raw)
            throughput_fps = 0.0
            if runtime_ms > 0:
                throughput_fps = (files_processed * 1000.0) / runtime_ms
            sample = BatchTrialSample(
                batch_size=batch_size,
                repeat_index=repeat_index,
                runtime_ms=runtime_ms,
                files_processed=files_processed,
                throughput_fps=throughput_fps,
            )
            samples.append(sample)
            logger.info(
                "Batch tuning trial",
                extra={
                    "phase": "phase9_batch_tuning",
                    "action": "batch_trial",
                    "dataset_id": dataset_id,
                    "policy_name": policy_name,
                    "env_class": env_class,
                    "batch_size": batch_size,
                    "repeat_index": repeat_index,
                    "runtime_ms": runtime_ms,
                    "files_count": files_processed,
                    "throughput_fps": throughput_fps,
                },
            )

        aggregate = _build_aggregate(batch_size, samples)
        aggregate_rows.append(aggregate)
        logger.info(
            "Batch tuning aggregate",
            extra={
                "phase": "phase9_batch_tuning",
                "action": "batch_aggregate",
                "dataset_id": dataset_id,
                "policy_name": policy_name,
                "env_class": env_class,
                "batch_size": aggregate.batch_size,
                "runs": aggregate.runs,
                "runtime_ms_p50": aggregate.runtime_ms_p50,
                "runtime_ms_p95": aggregate.runtime_ms_p95,
                "runtime_ms_cv": aggregate.runtime_ms_cv,
                "throughput_fps_p50": aggregate.throughput_fps_p50,
                "throughput_fps_p95": aggregate.throughput_fps_p95,
                "stable_p95": aggregate.stable_p95,
            },
        )

    recommendation = recommend_batch_size(aggregate_rows)
    logger.info(
        "Batch tuning recommendation",
        extra={
            "phase": "phase9_batch_tuning",
            "action": "batch_recommendation",
            "dataset_id": dataset_id,
            "policy_name": policy_name,
            "env_class": env_class,
            "recommended_batch_size": recommendation.recommended_batch_size,
            "safe_range_min": recommendation.safe_range_min,
            "safe_range_max": recommendation.safe_range_max,
            "max_throughput_fps_p50": recommendation.max_throughput_fps_p50,
            "eligible_batch_sizes": ",".join(str(size) for size in recommendation.eligible_batch_sizes),
            "selection_reason": recommendation.selection_reason,
        },
    )

    return BatchTuningReport(
        dataset_id=dataset_id,
        env_class=env_class,
        policy_name=policy_name,
        candidate_batch_sizes=list(normalized_sizes),
        repeats=repeats,
        aggregates=sorted(aggregate_rows, key=lambda row: row.batch_size),
        recommendation=recommendation,
    )


def report_to_dict(report: BatchTuningReport) -> dict[str, Any]:
    """Render a deterministic dict payload for JSON serialization."""

    return {
        "dataset_id": report.dataset_id,
        "env_class": report.env_class,
        "policy_name": report.policy_name,
        "candidate_batch_sizes": list(report.candidate_batch_sizes),
        "repeats": report.repeats,
        "aggregates": [
            {
                "batch_size": row.batch_size,
                "runs": row.runs,
                "runtime_ms_p50": row.runtime_ms_p50,
                "runtime_ms_p95": row.runtime_ms_p95,
                "runtime_ms_cv": row.runtime_ms_cv,
                "throughput_fps_p50": row.throughput_fps_p50,
                "throughput_fps_p95": row.throughput_fps_p95,
                "stable_p95": row.stable_p95,
            }
            for row in sorted(report.aggregates, key=lambda item: item.batch_size)
        ],
        "recommendation": {
            "recommended_batch_size": report.recommendation.recommended_batch_size,
            "safe_range_min": report.recommendation.safe_range_min,
            "safe_range_max": report.recommendation.safe_range_max,
            "max_throughput_fps_p50": report.recommendation.max_throughput_fps_p50,
            "eligible_batch_sizes": list(report.recommendation.eligible_batch_sizes),
            "selection_reason": report.recommendation.selection_reason,
        },
    }
