from collections import Counter

from data.synthetic import FAULT_TYPES, generate_runs


def test_generator_returns_complete_runs_and_separate_truth() -> None:
    observations, truth = generate_runs(
        seed=11,
        pump_ids=("pump-a", "pump-b"),
        scenarios=("normal", "cavitation", "bearing_degradation"),
        points_per_run=30,
        missing_rate=0.05,
    )

    assert len(observations) == len(truth) == 90
    assert {item.run_id for item in observations} == {"run-0001", "run-0002", "run-0003"}
    assert all(item.fault_type in FAULT_TYPES for item in truth)
    assert all(not hasattr(item, "fault_type") for item in observations)
    assert all(item.pump_state == "running" for item in observations)


def test_generator_has_temporal_order_variation_and_missing_values() -> None:
    observations, truth = generate_runs(
        seed=3,
        scenarios=("normal", "sensor_drift", "sudden_failure"),
        points_per_run=60,
        missing_rate=0.1,
    )

    by_run = {}
    for item in observations:
        by_run.setdefault(item.run_id, []).append(item)
    assert all(
        [item.timestamp for item in run] == sorted(item.timestamp for item in run)
        for run in by_run.values()
    )
    assert len({item.operating_regime for item in observations}) == 3
    assert len({round(item.operating_load, 3) for item in observations}) > 10
    assert any(item.pressure is None for item in observations)
    assert any(item.failure_flag for item in truth)


def test_all_default_scenarios_are_represented() -> None:
    _, truth = generate_runs(points_per_run=12, missing_rate=0)

    assert Counter(item.fault_type for item in truth) == Counter({scenario: 12 for scenario in FAULT_TYPES})
