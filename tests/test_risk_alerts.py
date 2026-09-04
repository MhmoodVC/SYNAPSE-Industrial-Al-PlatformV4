from datetime import datetime, timedelta, timezone

from decision.alerts import AlertEngine
from decision.diagnosis import diagnose
from decision.risk_engine import assess_risk


START = datetime(2025, 1, 1, tzinfo=timezone.utc)


def assessment(score: float):
    diagnosis = diagnose({"vibration_robust_z": score * 3, "pressure_rolling_std": score * 3, "flow_rolling_std": score * 3}, min_support=0.0, ambiguity_margin=0.0)
    return assess_risk(diagnosis, persistence=score, operating_load=score, severity=score)


def test_risk_score_exposes_bounded_contributions() -> None:
    result = assess_risk(
        diagnose({"vibration_robust_z": 3.0, "pressure_rolling_std": 3.0, "flow_rolling_std": 3.0}, min_support=0.5, ambiguity_margin=0.05),
        persistence=0.8,
        operating_load=0.9,
        severity=0.7,
    )

    assert 0 <= result.score <= 1
    assert {item.name for item in result.contributions} == {"diagnostic_support", "persistence", "operating_load", "severity"}
    assert sum(item.weighted_value for item in result.contributions) == result.score
    assert all(item.reason for item in result.contributions)


def test_alert_requires_persistence_and_clears_with_hysteresis() -> None:
    engine = AlertEngine(persistence=2, trigger_threshold=0.4, clear_threshold=0.25, cooldown=timedelta(minutes=5))
    high = assessment(0.8)
    low = assessment(0.1)

    assert engine.process(timestamp=START, run_id="run-1", pump_id="pump-1", assessment=high) == ()
    emitted = engine.process(timestamp=START + timedelta(minutes=1), run_id="run-1", pump_id="pump-1", assessment=high)
    assert len(emitted) == 1
    assert emitted[0].alert_type == "AI_DIAGNOSTIC"
    assert engine.process(timestamp=START + timedelta(minutes=2), run_id="run-1", pump_id="pump-1", assessment=high) == ()
    assert engine.process(timestamp=START + timedelta(minutes=3), run_id="run-1", pump_id="pump-1", assessment=low) == ()


def test_cooldown_and_hard_limit_are_separate() -> None:
    engine = AlertEngine(persistence=1, cooldown=timedelta(minutes=10))
    high = assessment(0.8)
    timestamp = START

    first = engine.process(timestamp=timestamp, run_id="run-1", pump_id="pump-1", assessment=high, hard_limit_message="SIMULATION hard limit")
    second = engine.process(timestamp=timestamp + timedelta(minutes=1), run_id="run-1", pump_id="pump-1", assessment=high, hard_limit_message="SIMULATION hard limit")

    assert {alert.alert_type for alert in first} == {"HARD_LIMIT", "AI_DIAGNOSTIC"}
    assert [alert.alert_type for alert in second] == ["HARD_LIMIT"]
    assert second[0].risk_score is None


def test_multi_sensor_confirmation_suppresses_single_sensor_noise() -> None:
    engine = AlertEngine(persistence=1, require_multi_sensor=True)
    high = assessment(0.85)

    # Single sensor confirmation should be suppressed
    emitted_single = engine.process(
        timestamp=START,
        run_id="run-1",
        pump_id="pump-1",
        assessment=high,
        confirming_sensors=("vibration_robust_z",),
    )
    assert len(emitted_single) == 0

    # Multi-sensor confirmation emits alert
    emitted_multi = engine.process(
        timestamp=START + timedelta(minutes=1),
        run_id="run-1",
        pump_id="pump-1",
        assessment=high,
        confirming_sensors=("vibration_robust_z", "temperature_robust_z"),
    )
    assert len(emitted_multi) == 1
    assert emitted_multi[0].confirmed_by == ("vibration_robust_z", "temperature_robust_z")


def test_event_level_alert_evaluation_metrics() -> None:
    from alerts import Alert, evaluate_event_alerts
    from data.synthetic import PumpGroundTruth

    # Simulate 2 runs: run-1 (fault event), run-2 (normal)
    event_start = START + timedelta(minutes=10)
    event_end = START + timedelta(minutes=30)
    truth = [
        PumpGroundTruth(
            timestamp=event_start,
            run_id="run-0001",
            pump_id="pump-001",
            fault_type="cavitation",
            severity=0.8,
            degradation_stage=0.0,
            event_start=event_start,
            event_end=event_end,
            failure_flag=False,
        ),
        PumpGroundTruth(
            timestamp=event_start,
            run_id="run-0002",
            pump_id="pump-001",
            fault_type="normal",
            severity=0.0,
            degradation_stage=0.0,
            event_start=None,
            event_end=None,
            failure_flag=False,
        ),
    ]

    # Emitted alert after event_start
    alerts = [
        Alert(
            timestamp=event_start + timedelta(minutes=2),
            run_id="run-0001",
            pump_id="pump-001",
            alert_type="AI_DIAGNOSTIC",
            level="critical",
            message="persistent risk threshold exceeded",
            risk_score=0.85,
        )
    ]

    metrics = evaluate_event_alerts(truth, alerts, false_alarm_budget=0.05)
    assert metrics.total_events == 1
    assert metrics.detected_events == 1
    assert metrics.missed_events == 0
    assert metrics.event_recall == 1.0
    assert metrics.false_alarms == 0
    assert metrics.false_alarm_rate == 0.0
    assert metrics.budget_compliant is True
    assert metrics.mean_detection_delay_seconds == 120.0

