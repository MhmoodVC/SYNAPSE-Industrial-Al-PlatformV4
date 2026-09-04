"""Causal degradation proxy and health score evaluation for pump trajectories."""

from dataclasses import dataclass
import math
from typing import Any, Optional, Sequence


SENSOR_FIELDS = ("pressure", "flow", "temperature", "vibration", "motor_current")

# Physical importance weights for pump degradation
SENSOR_WEIGHTS = {
    "vibration": 0.30,
    "temperature": 0.25,
    "motor_current": 0.20,
    "pressure": 0.15,
    "flow": 0.10,
}

# Empirical physical load relationship slopes (sensor delta per unit operating_load delta)
LOAD_SLOPES = {
    "pressure": 0.35,
    "flow": 13.0,
    "temperature": 9.0,
    "vibration": 0.22,
    "motor_current": 2.5,
}

# Baseline noise floor to prevent division by near-zero variance
MIN_STD = {
    "pressure": 0.10,
    "flow": 1.00,
    "temperature": 1.00,
    "vibration": 0.10,
    "motor_current": 0.25,
}


@dataclass(frozen=True)
class HealthScoreResult:
    """Result of causal health score computation."""

    run_id: str
    pump_id: str
    health_score: float
    status: str
    baseline_samples: int
    current_samples: int
    aggregate_deviation: float
    deviations: dict[str, float]


def compute_health_score(
    records: Sequence[Any],
    *,
    baseline_window: int = 100,
    current_window: int = 100,
) -> HealthScoreResult:
    """Compute a strictly causal health score comparing first N vs last N samples.

    The first baseline_window samples establish the run's nominal operating baseline.
    The last current_window samples represent current degraded or persisting conditions.
    Causality is preserved: only historical samples within the run are evaluated.
    Sensor shifts are normalized for operating load transitions to isolate true degradation.
    """
    if not records:
        raise ValueError("records cannot be empty")

    n_samples = len(records)
    b_window = min(baseline_window, n_samples)
    c_window = min(current_window, n_samples)

    baseline_records = records[:b_window]
    current_records = records[-c_window:]

    first_record = records[0]
    run_id = _get_field(first_record, "run_id") or "unknown"
    pump_id = _get_field(first_record, "pump_id") or "unknown"

    # Compute mean operating loads
    base_loads = [_get_float(r, "operating_load") for r in baseline_records]
    base_loads = [l for l in base_loads if l is not None and not math.isnan(l)]
    curr_loads = [_get_float(r, "operating_load") for r in current_records]
    curr_loads = [l for l in curr_loads if l is not None and not math.isnan(l)]

    delta_load = 0.0
    if base_loads and curr_loads:
        delta_load = (sum(curr_loads) / len(curr_loads)) - (sum(base_loads) / len(base_loads))

    deviations: dict[str, float] = {}
    weighted_deviation = 0.0

    for sensor in SENSOR_FIELDS:
        base_vals = [_get_float(r, sensor) for r in baseline_records]
        base_vals = [v for v in base_vals if v is not None and not math.isnan(v)]

        curr_vals = [_get_float(r, sensor) for r in current_records]
        curr_vals = [v for v in curr_vals if v is not None and not math.isnan(v)]

        if not base_vals or not curr_vals:
            deviations[sensor] = 0.0
            continue

        base_mean = sum(base_vals) / len(base_vals)
        variance = sum((v - base_mean) ** 2 for v in base_vals) / max(1, len(base_vals))
        base_std = max(math.sqrt(variance), MIN_STD.get(sensor, 0.10))

        curr_mean = sum(curr_vals) / len(curr_vals)
        # Remove expected physical variation due to operating load change
        curr_adjusted = curr_mean - LOAD_SLOPES.get(sensor, 0.0) * delta_load

        z_dev = abs(curr_adjusted - base_mean) / base_std
        deviations[sensor] = float(z_dev)
        weighted_deviation += z_dev * SENSOR_WEIGHTS.get(sensor, 0.20)

    # Health score decays smoothly from 100 based on physical deviation
    score = float(max(0.0, min(100.0, 100.0 * math.exp(-0.15 * weighted_deviation))))

    if score >= 80.0:
        status = "HEALTHY"
    elif score >= 50.0:
        status = "DEGRADED"
    else:
        status = "CRITICAL"

    return HealthScoreResult(
        run_id=str(run_id),
        pump_id=str(pump_id),
        health_score=round(score, 2),
        status=status,
        baseline_samples=len(baseline_records),
        current_samples=len(current_records),
        aggregate_deviation=round(weighted_deviation, 4),
        deviations={k: round(v, 4) for k, v in deviations.items()},
    )


def _get_field(obj: Any, field: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(field)
    return getattr(obj, field, None)


def _get_float(obj: Any, field: str) -> Optional[float]:
    val = _get_field(obj, field)
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
