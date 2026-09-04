from datetime import datetime, timedelta, timezone

from data.synthetic import generate_runs
from features.engineering import BaselineProfile, FEATURE_DEFINITIONS, transform_records


def test_features_are_derived_and_run_state_is_isolated() -> None:
    observations, _ = generate_runs(
        seed=9,
        pump_ids=("pump-1",),
        scenarios=("normal", "cavitation"),
        points_per_run=20,
        missing_rate=0,
    )
    baseline = BaselineProfile.fit(observations[:20])
    features = transform_records(observations, baseline, window=4)

    assert len(features) == 40
    assert features[0]["pressure_delta"] is None
    assert features[20]["pressure_delta"] is None
    assert features[20]["pressure_rolling_mean"] == features[20]["pressure"]
    assert features[20]["pressure_flow_ratio"] is not None
    assert features[20]["vibration_rms"] is not None
    assert features[20]["vibration_crest_factor"] is not None


def test_early_feature_does_not_use_future_observation() -> None:
    observations, _ = generate_runs(
        seed=4,
        pump_ids=("pump-1",),
        scenarios=("normal",),
        points_per_run=15,
        missing_rate=0,
    )
    baseline = BaselineProfile.fit(observations)
    original = transform_records(observations, baseline, window=5)
    changed = list(observations)
    changed[-1] = changed[-1].__class__(
        timestamp=changed[-1].timestamp,
        run_id=changed[-1].run_id,
        pump_id=changed[-1].pump_id,
        pressure=999.0,
        flow=changed[-1].flow,
        temperature=changed[-1].temperature,
        vibration=changed[-1].vibration,
        motor_current=changed[-1].motor_current,
        operating_load=changed[-1].operating_load,
        operating_regime=changed[-1].operating_regime,
        pump_state=changed[-1].pump_state,
    )
    revised = transform_records(changed, baseline, window=5)

    assert original[0] == revised[0]
    assert original[5]["pressure_rolling_mean"] == revised[5]["pressure_rolling_mean"]


def test_feature_metadata_declares_leakage_policy() -> None:
    assert FEATURE_DEFINITIONS
    assert all(item.leakage_status == "safe" for item in FEATURE_DEFINITIONS)
    assert all(item.window_direction in {"current", "backward"} for item in FEATURE_DEFINITIONS)
