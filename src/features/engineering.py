"""Leakage-safe, interpretable feature engineering for sensor trajectories."""

from dataclasses import dataclass
from math import sqrt
from statistics import median
from typing import Optional

from data.contract import SENSOR_FIELDS, SensorRecord, require_valid_records


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    units: str
    window_direction: str
    leakage_status: str
    intended_use: str


@dataclass(frozen=True)
class BaselineProfile:
    """Training-only robust baseline statistics."""

    medians: dict[str, float]
    mads: dict[str, float]

    @classmethod
    def fit(cls, records: list[SensorRecord]) -> "BaselineProfile":
        require_valid_records(records)
        medians: dict[str, float] = {}
        mads: dict[str, float] = {}
        for field in SENSOR_FIELDS:
            values = [getattr(record, field) for record in records]
            observed = [float(value) for value in values if value is not None]
            if not observed:
                continue
            field_median = median(observed)
            deviation = median([abs(value - field_median) for value in observed])
            medians[field] = field_median
            mads[field] = deviation
        return cls(medians=medians, mads=mads)


FEATURE_DEFINITIONS = (
    FeatureDefinition("pressure", "sensor units", "current", "safe", "raw hydraulic signal"),
    FeatureDefinition("flow", "sensor units", "current", "safe", "raw hydraulic signal"),
    FeatureDefinition("temperature", "sensor units", "current", "safe", "raw thermal signal"),
    FeatureDefinition("vibration", "sensor units", "current", "safe", "raw mechanical signal"),
    FeatureDefinition("motor_current", "sensor units", "current", "safe", "raw electrical signal"),
    FeatureDefinition("operating_load", "fraction", "current", "safe", "operating context"),
    FeatureDefinition("pressure_rolling_mean", "sensor units", "backward", "safe", "local hydraulic level"),
    FeatureDefinition("pressure_rolling_std", "sensor units", "backward", "safe", "pressure stability"),
    FeatureDefinition("flow_rolling_std", "sensor units", "backward", "safe", "flow stability"),
    FeatureDefinition("vibration_rms", "sensor units", "backward", "safe", "mechanical energy"),
    FeatureDefinition("vibration_peak", "sensor units", "backward", "safe", "mechanical peak"),
    FeatureDefinition("vibration_crest_factor", "ratio", "backward", "safe", "vibration shape"),
    FeatureDefinition("pressure_delta", "sensor units", "backward", "safe", "short-term pressure change"),
    FeatureDefinition("flow_delta", "sensor units", "backward", "safe", "short-term flow change"),
    FeatureDefinition("pressure_flow_ratio", "ratio", "current", "safe", "hydraulic relationship"),
    FeatureDefinition("pressure_robust_z", "z-score", "current", "safe", "baseline deviation"),
    FeatureDefinition("flow_robust_z", "z-score", "current", "safe", "baseline deviation"),
    FeatureDefinition("temperature_robust_z", "z-score", "current", "safe", "baseline deviation"),
    FeatureDefinition("vibration_robust_z", "z-score", "current", "safe", "baseline deviation"),
    FeatureDefinition("motor_current_robust_z", "z-score", "current", "safe", "baseline deviation"),
    FeatureDefinition("flow_rolling_mean", "sensor units", "backward", "safe", "local hydraulic flow level"),
    FeatureDefinition("temperature_rolling_mean", "sensor units", "backward", "safe", "local thermal level"),
    FeatureDefinition("vibration_rolling_mean", "sensor units", "backward", "safe", "local vibration level"),
    FeatureDefinition("motor_current_rolling_mean", "sensor units", "backward", "safe", "local electrical level"),
    FeatureDefinition("temperature_delta", "sensor units", "backward", "safe", "short-term temperature change"),
    FeatureDefinition("vibration_delta", "sensor units", "backward", "safe", "short-term vibration change"),
    FeatureDefinition("motor_current_delta", "sensor units", "backward", "safe", "short-term electrical change"),
    FeatureDefinition("temperature_rolling_std", "sensor units", "backward", "safe", "thermal stability"),
    FeatureDefinition("vibration_rolling_std", "sensor units", "backward", "safe", "mechanical stability"),
    FeatureDefinition("motor_current_rolling_std", "sensor units", "backward", "safe", "electrical stability"),
    FeatureDefinition("flow_pressure_delta_diff", "ratio", "backward", "safe", "hydraulic decoupling"),
    FeatureDefinition("vibration_rate_of_change", "rate", "backward", "safe", "vibration change rate"),
    FeatureDefinition("pressure_load_adj_dev", "sensor units", "backward", "safe", "load-normalized pressure deviation"),
    FeatureDefinition("flow_load_adj_dev", "sensor units", "backward", "safe", "load-normalized flow deviation"),
    FeatureDefinition("temperature_load_adj_dev", "sensor units", "backward", "safe", "load-normalized temperature deviation"),
    FeatureDefinition("vibration_load_adj_dev", "sensor units", "backward", "safe", "load-normalized vibration deviation"),
    FeatureDefinition("motor_current_load_adj_dev", "sensor units", "backward", "safe", "load-normalized current deviation"),
    FeatureDefinition("total_abs_dev", "score", "backward", "safe", "aggregate physical deviation"),
    FeatureDefinition("is_deviating", "flag", "backward", "safe", "abnormal operational deviation indicator"),
    FeatureDefinition("sudden_fail_sig", "flag", "backward", "safe", "catastrophic collapse signature"),
)


def transform_records(
    records: list[SensorRecord],
    baseline: BaselineProfile,
    *,
    window: int = 5,
) -> list[dict[str, object]]:
    """Transform ordered records using only current and previous observations."""
    require_valid_records(records)
    if window < 2:
        raise ValueError("window must be at least 2")
    history: dict[str, list[float]] = {field: [] for field in SENSOR_FIELDS}
    previous: dict[str, Optional[float]] = {field: None for field in SENSOR_FIELDS}
    initial_history: dict[str, list[float]] = {field: [] for field in SENSOR_FIELDS}
    initial_loads: list[float] = []
    active_run: Optional[str] = None
    output: list[dict[str, object]] = []

    load_slopes = {
        "pressure": 0.35,
        "flow": 13.0,
        "temperature": 9.0,
        "vibration": 0.22,
        "motor_current": 2.5,
    }

    for record in records:
        if record.run_id != active_run:
            history = {field: [] for field in SENSOR_FIELDS}
            previous = {field: None for field in SENSOR_FIELDS}
            initial_history = {field: [] for field in SENSOR_FIELDS}
            initial_loads = []
            active_run = record.run_id

        if len(initial_loads) < 30:
            initial_loads.append(float(record.operating_load))
            for field in SENSOR_FIELDS:
                v = getattr(record, field)
                if v is not None:
                    initial_history[field].append(float(v))

        base_load = (sum(initial_loads) / len(initial_loads)) if initial_loads else float(record.operating_load)
        delta_load = float(record.operating_load) - base_load

        features: dict[str, object] = {
            "timestamp": record.timestamp,
            "run_id": record.run_id,
            "pump_id": record.pump_id,
            "operating_regime": record.operating_regime,
            "pump_state": record.pump_state,
            "operating_load": record.operating_load,
        }
        for field in SENSOR_FIELDS:
            value = getattr(record, field)
            features[field] = value
            if value is not None:
                values = history[field] + [float(value)]
                recent = values[-window:]
                roll_mean = _mean(recent)
                features[f"{field}_rolling_mean"] = roll_mean
                features[f"{field}_rolling_std"] = _std(recent)
                features[f"{field}_rolling_min"] = min(recent)
                features[f"{field}_rolling_max"] = max(recent)
                features[f"{field}_delta"] = _delta(previous[field], float(value))
                features[f"{field}_robust_z"] = _robust_z(float(value), baseline, field)
                base_s = (sum(initial_history[field]) / len(initial_history[field])) if initial_history[field] else baseline.medians.get(field, 0.0)
                features[f"{field}_load_adj_dev"] = (roll_mean - base_s) - load_slopes.get(field, 0.0) * delta_load
                history[field].append(float(value))
                history[field] = history[field][-window:]
                previous[field] = float(value)
            else:
                for suffix in ("rolling_mean", "rolling_std", "rolling_min", "rolling_max", "delta", "robust_z", "load_adj_dev"):
                    features[f"{field}_{suffix}"] = None

        vibration_values = _available(history["vibration"])
        features["vibration_rms"] = _rms(vibration_values)
        features["vibration_peak"] = max(vibration_values) if vibration_values else None
        features["vibration_crest_factor"] = _ratio(features["vibration_peak"], features["vibration_rms"])
        features["pressure_flow_ratio"] = _ratio(features["pressure"], features["flow"])
        features["pressure_stability"] = features["pressure_rolling_std"]
        features["flow_stability"] = features["flow_rolling_std"]
        
        flow_d = features.get("flow_delta")
        press_d = features.get("pressure_delta")
        if flow_d is not None and press_d is not None:
            features["flow_pressure_delta_diff"] = float(flow_d) - float(press_d) * 5.0
        else:
            features["flow_pressure_delta_diff"] = None
            
        features["vibration_rate_of_change"] = features.get("vibration_delta")

        total_dev = sum(abs(float(features[f"{f}_load_adj_dev"])) for f in SENSOR_FIELDS if features.get(f"{f}_load_adj_dev") is not None)
        features["total_abs_dev"] = total_dev
        features["is_deviating"] = 1.0 if total_dev > 1.2 else 0.0

        min_p = min(history["pressure"]) if history["pressure"] else (float(record.pressure) if record.pressure is not None else 5.0)
        min_f = min(history["flow"]) if history["flow"] else (float(record.flow) if record.flow is not None else 38.0)
        max_v = max(history["vibration"]) if history["vibration"] else (float(record.vibration) if record.vibration is not None else 1.5)
        features["sudden_fail_sig"] = 1.0 if min_p < 2.0 and min_f < 15.0 and max_v > 3.0 else 0.0

        output.append(features)
    return output


def _available(values: list[float]) -> list[float]:
    return [value for value in values if value is not None]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _rms(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return sqrt(sum(value * value for value in values) / len(values))


def _delta(previous: Optional[float], current: float) -> Optional[float]:
    return None if previous is None else current - previous


def _ratio(numerator: object, denominator: object) -> Optional[float]:
    if not isinstance(numerator, (int, float)) or not isinstance(denominator, (int, float)) or denominator == 0:
        return None
    return float(numerator) / float(denominator)


def _robust_z(value: float, baseline: BaselineProfile, field: str) -> Optional[float]:
    if field not in baseline.medians:
        return None
    mad = baseline.mads[field]
    scale = 1.4826 * mad
    return 0.0 if scale == 0 else (value - baseline.medians[field]) / scale
