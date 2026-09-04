import math
from models.health_score import compute_health_score, HealthScoreResult
from synapse_waterpump.models.health_score import compute_health_score as bridged_compute
from data.synthetic import generate_runs


def test_health_score_healthy_run() -> None:
    observations, _ = generate_runs(
        seed=42,
        scenarios=("normal",),
        points_per_run=150,
        missing_rate=0.0,
    )
    result = compute_health_score(observations)

    assert isinstance(result, HealthScoreResult)
    assert result.health_score >= 80.0
    assert result.status == "HEALTHY"
    assert result.baseline_samples == 100
    assert result.current_samples == 100
    assert result.aggregate_deviation >= 0.0


def test_health_score_degraded_run() -> None:
    observations, _ = generate_runs(
        seed=42,
        scenarios=("bearing_degradation",),
        points_per_run=300,
        missing_rate=0.0,
    )
    result = compute_health_score(observations)

    assert isinstance(result, HealthScoreResult)
    assert result.health_score < 80.0
    assert result.status in ("DEGRADED", "CRITICAL")
    assert result.deviations["vibration"] > 0.5


def test_health_score_causality_and_short_run() -> None:
    # Testing short run < 100 samples
    observations, _ = generate_runs(
        seed=10,
        scenarios=("normal",),
        points_per_run=30,
        missing_rate=0.05,
    )
    result = bridged_compute(observations)

    assert result.baseline_samples == 30
    assert result.current_samples == 30
    assert 0.0 <= result.health_score <= 100.0
