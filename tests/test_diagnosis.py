from decision.diagnosis import diagnose
from decision.fault_knowledge import FAULT_KNOWLEDGE


def test_knowledge_base_contains_required_faults_and_actions() -> None:
    expected = {
        "cavitation",
        "bearing_degradation",
        "seal_leakage",
        "overheating",
        "flow_restriction",
        "pressure_loss",
        "motor_overload",
        "progressive_degradation",
    }

    assert expected.issubset(FAULT_KNOWLEDGE)
    assert all(signature.evidence_features for signature in FAULT_KNOWLEDGE.values())
    assert all(signature.candidate_actions for signature in FAULT_KNOWLEDGE.values())


def test_diagnosis_ranks_clear_cavitation_without_calling_score_probability() -> None:
    result = diagnose(
        {
            "vibration_robust_z": 3.0,
            "pressure_rolling_std": 3.0,
            "flow_rolling_std": 3.0,
        },
        min_support=0.5,
        ambiguity_margin=0.05,
    )

    assert result.diagnosis == "cavitation"
    assert result.review_required is False
    assert result.confidence is not None
    assert result.confidence <= 1.0
    assert result.candidates[0].evidence[0].evidence_type == "RULE_DERIVED_EVIDENCE"


def test_diagnosis_requires_review_when_evidence_is_missing_or_ambiguous() -> None:
    insufficient = diagnose({"vibration_robust_z": 0.1}, min_support=0.5)
    ambiguous = diagnose(
        {
            "vibration_robust_z": 1.5,
            "temperature_robust_z": 1.5,
            "pressure_robust_z": 1.5,
            "flow_robust_z": 1.5,
        },
        min_support=0.1,
        ambiguity_margin=1.0,
    )

    assert insufficient.review_required is True
    assert insufficient.diagnosis == "unknown"
    assert ambiguous.review_required is True
    assert ambiguous.diagnosis == "ambiguous"


def test_knowledge_base_covers_all_eleven_scenarios() -> None:
    all_eleven = {
        "normal",
        "cavitation",
        "bearing_degradation",
        "seal_leakage",
        "overheating",
        "flow_restriction",
        "pressure_loss",
        "motor_overload",
        "sensor_drift",
        "progressive_degradation",
        "sudden_failure",
    }
    assert all_eleven.issubset(FAULT_KNOWLEDGE)
    assert len(FAULT_KNOWLEDGE) >= 11
    for name in all_eleven:
        sig = FAULT_KNOWLEDGE[name]
        assert len(sig.evidence_features) > 0
        assert len(sig.candidate_actions) > 0
        assert len(sig.guardrails) > 0
        assert sig.likely_cause


def test_diagnosis_outputs_normalized_ranked_probabilities() -> None:
    result = diagnose(
        {
            "vibration_robust_z": 3.0,
            "pressure_rolling_std": 2.5,
            "flow_rolling_std": 2.5,
        },
        min_support=0.35,
    )

    assert result.diagnosis == "cavitation"
    assert len(result.ranked_probabilities) == len(FAULT_KNOWLEDGE)
    prob_sum = sum(p for _, p in result.ranked_probabilities)
    assert 0.99 <= prob_sum <= 1.01
    assert result.ranked_probabilities[0][0] == "cavitation"
    assert result.ranked_probabilities[0][1] > 0.3
    assert all(0.0 <= c.probability <= 1.0 for c in result.candidates)


def test_diagnosis_handles_normal_operating_condition() -> None:
    normal_features = {
        "vibration_robust_z": 0.05,
        "pressure_robust_z": 0.02,
        "flow_robust_z": 0.04,
        "temperature_robust_z": 0.03,
        "motor_current_robust_z": 0.02,
    }
    result = diagnose(normal_features, min_support=0.35, ambiguity_margin=0.10)
    assert result.diagnosis == "normal"
    assert result.review_required is False
    assert result.confidence is not None
    assert result.confidence > 0.8


def test_diagnosis_handles_sensor_drift_and_sudden_failure() -> None:
    drift_result = diagnose(
        {
            "pressure_robust_z": 3.5,
            "flow_pressure_delta_diff": 3.0,
            "flow_robust_z": 0.0,
            "vibration_robust_z": 0.0,
        },
        min_support=0.35,
    )
    assert drift_result.diagnosis == "sensor_drift"
    assert drift_result.review_required is False

    sudden_result = diagnose(
        {
            "sudden_fail_sig": 1.0,
            "vibration_robust_z": 4.0,
            "pressure_robust_z": 3.0,
        },
        min_support=0.35,
    )
    assert sudden_result.diagnosis == "sudden_failure"
    assert sudden_result.review_required is False

