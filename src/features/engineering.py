"""Leakage-safe, interpretable feature engineering for sensor trajectories.

Follows Clean Architecture boundaries:
- Pure functions for rolling and multiscale aggregations.
- Zero future-leakage (strictly backward and current windows).
- Explicit typing across all data structures.
"""

from dataclasses import dataclass
from math import sqrt
from statistics import median
from typing import Any, Dict, List, Optional, Sequence, Tuple

from data.contract import SENSOR_FIELDS, SensorRecord, require_valid_records

# Domain constants for load-dependent baseline compensation
LOAD_SLOPES: Dict[str, float] = {
    "pressure": 0.35,
    "flow": 13.0,
    "temperature": 9.0,
    "vibration": 0.22,
    "motor_current": 2.5,
}

# Fields that receive multi-scale (15s, 30s) and derivative expansions
MULTISCALE_FIELDS: Tuple[str, ...] = ("vibration", "motor_current", "temperature")

# Maximum historical buffer depth per sensor field to bound memory usage
MAX_HISTORY_DEPTH: int = 40


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
    FeatureDefinition("vibration_rolling_mean_15", "sensor units", "backward", "safe", "medium-term vibration level"),
    FeatureDefinition("vibration_rolling_std_15", "sensor units", "backward", "safe", "medium-term vibration stability"),
    FeatureDefinition("vibration_rolling_mean_30", "sensor units", "backward", "safe", "long-term vibration level"),
    FeatureDefinition("vibration_rolling_std_30", "sensor units", "backward", "safe", "long-term vibration stability"),
    FeatureDefinition("motor_current_rolling_mean_15", "sensor units", "backward", "safe", "medium-term current level"),
    FeatureDefinition("motor_current_rolling_std_15", "sensor units", "backward", "safe", "medium-term current stability"),
    FeatureDefinition("motor_current_rolling_mean_30", "sensor units", "backward", "safe", "long-term current level"),
    FeatureDefinition("motor_current_rolling_std_30", "sensor units", "backward", "safe", "long-term current stability"),
    FeatureDefinition("temperature_rolling_mean_15", "sensor units", "backward", "safe", "medium-term temperature level"),
    FeatureDefinition("temperature_rolling_std_15", "sensor units", "backward", "safe", "medium-term temperature stability"),
    FeatureDefinition("temperature_rolling_mean_30", "sensor units", "backward", "safe", "long-term temperature level"),
    FeatureDefinition("temperature_rolling_std_30", "sensor units", "backward", "safe", "long-term temperature stability"),
    FeatureDefinition("vibration_dz_dt", "rate", "backward", "safe", "dynamic vibration derivative"),
    FeatureDefinition("motor_current_dz_dt", "rate", "backward", "safe", "dynamic current derivative"),
    FeatureDefinition("temperature_dz_dt", "rate", "backward", "safe", "dynamic thermal derivative"),
    FeatureDefinition("vibration_kurtosis", "ratio", "backward", "safe", "vibration distribution shape"),
)


def _compute_primary_rolling_features(values: List[float], window: int) -> Dict[str, float]:
    """Compute local rolling window statistics for a single sensor series."""
    recent = values[-window:]
    return {
        "rolling_mean": _mean(recent),
        "rolling_std": _std(recent),
        "rolling_min": min(recent),
        "rolling_max": max(recent),
    }


def _compute_multiscale_features(values: List[float], val_f: float) -> Dict[str, float]:
    """Compute 15s and 30s rolling statistics plus 5s dynamic derivative dz/dt."""
    recent_15 = values[-15:]
    recent_30 = values[-30:]
    dz_dt = (val_f - values[-5]) / 5.0 if len(values) >= 5 else 0.0
    return {
        "rolling_mean_15": _mean(recent_15),
        "rolling_std_15": _std(recent_15),
        "rolling_mean_30": _mean(recent_30),
        "rolling_std_30": _std(recent_30),
        "dz_dt": dz_dt,
    }


def _compute_vibration_shape_metrics(vibration_history: List[float]) -> Dict[str, Optional[float]]:
    """Compute RMS, peak, crest factor, and kurtosis for vibration waveform."""
    vibration_values = _available(vibration_history)
    if not vibration_values:
        return {
            "vibration_rms": None,
            "vibration_peak": None,
            "vibration_crest_factor": None,
            "vibration_kurtosis": None,
        }
    recent_v = vibration_values[-15:]
    rms_val = _rms(recent_v)
    peak_val = max(recent_v)
    crest_val = _ratio(peak_val, rms_val)
    m_v = sum(recent_v) / len(recent_v)
    var_v = sum((x - m_v) ** 2 for x in recent_v) / len(recent_v)
    if var_v > 1e-6 and len(recent_v) >= 4:
        m4 = sum((x - m_v) ** 4 for x in recent_v) / len(recent_v)
        kurt_val = m4 / (var_v ** 2)
    else:
        kurt_val = 3.0
    return {
        "vibration_rms": rms_val,
        "vibration_peak": peak_val,
        "vibration_crest_factor": crest_val,
        "vibration_kurtosis": kurt_val,
    }


def _compute_sudden_failure_signature(history: Dict[str, List[float]], record: SensorRecord) -> float:
    """Detect catastrophic collapse signature (rapid suction drop, flow collapse, violent vibration)."""
    min_p = min(history["pressure"][-10:]) if history["pressure"] else (float(record.pressure) if record.pressure is not None else 5.0)
    min_f = min(history["flow"][-10:]) if history["flow"] else (float(record.flow) if record.flow is not None else 38.0)
    max_v = max(history["vibration"][-10:]) if history["vibration"] else (float(record.vibration) if record.vibration is not None else 1.5)
    return 1.0 if min_p < 2.0 and min_f < 15.0 and max_v > 3.0 else 0.0


def transform_records(
    records: Sequence[SensorRecord],
    baseline: BaselineProfile,
    *,
    window: int = 5,
) -> List[Dict[str, Any]]:
    """Transform ordered records using only current and previous observations.

    Guarantees strict zero-leakage: all features depend exclusively on 
    current and past sensor readings within the active run.
    """
    require_valid_records(records)
    if window < 2:
        raise ValueError("window must be at least 2")
    history: Dict[str, List[float]] = {field: [] for field in SENSOR_FIELDS}
    previous: Dict[str, Optional[float]] = {field: None for field in SENSOR_FIELDS}
    initial_history: Dict[str, List[float]] = {field: [] for field in SENSOR_FIELDS}
    initial_loads: List[float] = []
    active_run: Optional[str] = None
    output: List[Dict[str, Any]] = []

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

        features: Dict[str, Any] = {
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
                val_f = float(value)
                values = history[field] + [val_f]

                # Primary rolling metrics
                prim_metrics = _compute_primary_rolling_features(values, window)
                roll_mean = prim_metrics["rolling_mean"]
                features[f"{field}_rolling_mean"] = roll_mean
                features[f"{field}_rolling_std"] = prim_metrics["rolling_std"]
                features[f"{field}_rolling_min"] = prim_metrics["rolling_min"]
                features[f"{field}_rolling_max"] = prim_metrics["rolling_max"]

                # Multi-scale 15s and 30s rolling features and dynamic derivative (dz/dt)
                if field in MULTISCALE_FIELDS:
                    multi_metrics = _compute_multiscale_features(values, val_f)
                    features[f"{field}_rolling_mean_15"] = multi_metrics["rolling_mean_15"]
                    features[f"{field}_rolling_std_15"] = multi_metrics["rolling_std_15"]
                    features[f"{field}_rolling_mean_30"] = multi_metrics["rolling_mean_30"]
                    features[f"{field}_rolling_std_30"] = multi_metrics["rolling_std_30"]
                    features[f"{field}_dz_dt"] = multi_metrics["dz_dt"]

                features[f"{field}_delta"] = _delta(previous[field], val_f)
                features[f"{field}_robust_z"] = _robust_z(val_f, baseline, field)
                base_s = (sum(initial_history[field]) / len(initial_history[field])) if initial_history[field] else baseline.medians.get(field, 0.0)
                features[f"{field}_load_adj_dev"] = (roll_mean - base_s) - LOAD_SLOPES.get(field, 0.0) * delta_load

                history[field].append(val_f)
                if len(history[field]) > MAX_HISTORY_DEPTH:
                    history[field] = history[field][-MAX_HISTORY_DEPTH:]
                previous[field] = val_f
            else:
                for suffix in (
                    "rolling_mean", "rolling_std", "rolling_min", "rolling_max",
                    "rolling_mean_15", "rolling_std_15", "rolling_mean_30", "rolling_std_30",
                    "delta", "dz_dt", "robust_z", "load_adj_dev"
                ):
                    features[f"{field}_{suffix}"] = None

        # Vibration shape and distribution metrics
        vib_metrics = _compute_vibration_shape_metrics(history["vibration"])
        features.update(vib_metrics)

        # Cross-sensor hydraulic and mechanical relationships
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

        features["sudden_fail_sig"] = _compute_sudden_failure_signature(history, record)

        output.append(features)
    return output


def _available(values: Sequence[Optional[float]]) -> List[float]:
    """Filter non-null numeric values."""
    return [float(value) for value in values if value is not None]


def _mean(values: Sequence[float]) -> float:
    """Compute arithmetic mean."""
    return sum(values) / len(values)


def _std(values: Sequence[float]) -> float:
    """Compute sample standard deviation."""
    if len(values) < 2:
        return 0.0
    mean_val = _mean(values)
    return sqrt(sum((value - mean_val) ** 2 for value in values) / len(values))


def _rms(values: Sequence[float]) -> Optional[float]:
    """Compute root-mean-square."""
    if not values:
        return None
    return sqrt(sum(value * value for value in values) / len(values))


def _delta(previous: Optional[float], current: float) -> Optional[float]:
    """Compute point-to-point difference."""
    return None if previous is None else current - previous


def _ratio(numerator: object, denominator: object) -> Optional[float]:
    """Safely compute ratio without division by zero."""
    if not isinstance(numerator, (int, float)) or not isinstance(denominator, (int, float)) or denominator == 0:
        return None
    return float(numerator) / float(denominator)


def _robust_z(value: float, baseline: BaselineProfile, field: str) -> Optional[float]:
    """Compute median absolute deviation scaled robust z-score."""
    if field not in baseline.medians:
        return None
    mad = baseline.mads[field]
    scale = 1.4826 * mad
    return 0.0 if scale == 0 else (value - baseline.medians[field]) / scale
