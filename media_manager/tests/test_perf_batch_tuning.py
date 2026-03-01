from __future__ import annotations

from media_manager.app.core import perf_batch_tuning as tuning
from media_manager.app.core.perf_batch_tuning import (
    BatchAggregate,
    CANDIDATE_BATCH_SIZES,
    MIN_REPEATS,
    report_to_dict,
    run_batch_tuning,
)


def test_candidate_sizes_default_and_sorted() -> None:
    run = run_batch_tuning(
        runner=lambda _batch_size: (100.0, 1000),
        dataset_id="ds",
        env_class="ci",
    )
    assert run.candidate_batch_sizes == list(CANDIDATE_BATCH_SIZES)

    custom = run_batch_tuning(
        runner=lambda _batch_size: (100.0, 1000),
        dataset_id="ds",
        env_class="ci",
        candidate_batch_sizes=[500, 100, 500, 250],
    )
    assert custom.candidate_batch_sizes == [100, 250, 500]


def test_repeats_less_than_three_rejected() -> None:
    try:
        run_batch_tuning(
            runner=lambda _batch_size: (100.0, 1000),
            dataset_id="ds",
            env_class="ci",
            repeats=MIN_REPEATS - 1,
        )
    except ValueError as exc:
        assert "repeats must be >=" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid repeats")


def test_aggregate_computes_p50_p95_runtime_and_throughput() -> None:
    samples = [10.0, 20.0, 30.0]

    def runner(_batch_size: int) -> tuple[float, int]:
        return samples.pop(0), 100

    report = run_batch_tuning(
        runner=runner,
        dataset_id="ds",
        env_class="ci",
        candidate_batch_sizes=[100],
        repeats=3,
    )
    row = report.aggregates[0]
    assert row.runtime_ms_p50 == 20.0
    assert row.runtime_ms_p95 == 30.0
    assert row.throughput_fps_p50 == 5000.0
    assert row.throughput_fps_p95 == 10000.0


def test_recommend_smallest_within_95_percent_and_stable() -> None:
    report = run_batch_tuning(
        runner=lambda batch: (100.0, batch * 10),
        dataset_id="ds",
        env_class="ci",
        candidate_batch_sizes=[100, 250, 500],
        repeats=3,
    )
    # Throughputs: 100->10000, 250->25000, 500->50000; 95% threshold => 47500.
    assert report.recommendation.recommended_batch_size == 500


def test_recommendation_tie_breaks_to_smallest_batch() -> None:
    aggregates = [
        BatchAggregate(100, 3, 100.0, 100.0, 0.01, 1000.0, 1000.0, True),
        BatchAggregate(250, 3, 100.0, 100.0, 0.01, 1000.0, 1000.0, True),
        BatchAggregate(500, 3, 100.0, 100.0, 0.01, 1000.0, 1000.0, True),
    ]
    recommendation = tuning.recommend_batch_size(aggregates)
    assert recommendation.recommended_batch_size == 100
    assert recommendation.safe_range_min == 100
    assert recommendation.safe_range_max == 500


def test_no_stable_candidate_falls_back_to_max_throughput() -> None:
    aggregates = [
        BatchAggregate(100, 3, 100.0, 100.0, 0.50, 1200.0, 1300.0, False),
        BatchAggregate(250, 3, 100.0, 100.0, 0.40, 1300.0, 1400.0, False),
        BatchAggregate(500, 3, 100.0, 100.0, 0.30, 1250.0, 1350.0, False),
    ]
    recommendation = tuning.recommend_batch_size(aggregates)
    assert recommendation.recommended_batch_size == 250
    assert recommendation.safe_range_min == 250
    assert recommendation.safe_range_max == 250
    assert recommendation.selection_reason == "fallback_no_stable_candidates"


def test_safe_range_reflects_all_eligible_candidates() -> None:
    aggregates = [
        BatchAggregate(100, 3, 100.0, 100.0, 0.01, 98.0, 99.0, True),
        BatchAggregate(250, 3, 100.0, 100.0, 0.01, 100.0, 101.0, True),
        BatchAggregate(500, 3, 100.0, 100.0, 0.01, 99.0, 100.0, True),
    ]
    recommendation = tuning.recommend_batch_size(aggregates)
    assert recommendation.eligible_batch_sizes == [100, 250, 500]
    assert recommendation.safe_range_min == 100
    assert recommendation.safe_range_max == 500
    assert recommendation.recommended_batch_size == 100


def test_report_to_dict_deterministic_order() -> None:
    report = run_batch_tuning(
        runner=lambda _batch_size: (100.0, 1000),
        dataset_id="dataset",
        env_class="local",
        candidate_batch_sizes=[250, 100],
        repeats=3,
    )
    payload = report_to_dict(report)
    assert list(payload.keys()) == [
        "dataset_id",
        "env_class",
        "policy_name",
        "candidate_batch_sizes",
        "repeats",
        "aggregates",
        "recommendation",
    ]
    assert [row["batch_size"] for row in payload["aggregates"]] == [100, 250]


def test_runner_invocation_order_is_deterministic() -> None:
    calls: list[int] = []

    def runner(batch_size: int) -> tuple[float, int]:
        calls.append(batch_size)
        return (100.0, 1000)

    run_batch_tuning(
        runner=runner,
        dataset_id="ds",
        env_class="ci",
        candidate_batch_sizes=[500, 100, 250],
        repeats=3,
    )
    assert calls == [100, 100, 100, 250, 250, 250, 500, 500, 500]


def test_logging_emits_trial_aggregate_recommendation_events(monkeypatch) -> None:
    events: list[dict[str, object]] = []

    def capture(message: str, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        _ = message
        events.append(kwargs.get("extra", {}))

    monkeypatch.setattr(tuning.logger, "info", capture)

    run_batch_tuning(
        runner=lambda batch_size: (100.0, batch_size),
        dataset_id="dataset",
        env_class="ci",
        candidate_batch_sizes=[100, 250],
        repeats=3,
    )

    actions = [str(item.get("action")) for item in events]
    assert actions.count("batch_trial") == 6
    assert actions.count("batch_aggregate") == 2
    assert actions.count("batch_recommendation") == 1

