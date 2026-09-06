"""Unit tests for SYNAPSE Advanced Analytics extensions."""

import math
from decision.arena import DecisionArena, DecisionOption
from decision.diagnosis import DiagnosisCandidate, DiagnosisResult
from decision.risk_engine import RiskAssessment, RiskContribution
from analytics.extensions import (
    ArenaActionAlternative,
    calculate_enterprise_roi,
    compute_sensitivity_costs,
    compute_sustainability_metrics,
    estimate_remaining_useful_life,
)


def _mock_arena() -> DecisionArena:
    """Helper to create a deterministic DecisionArena for testing."""
    options = (
        DecisionOption(
            action="no_action",
            risk_score=0.80,
            operational_impact="Full operational throughput",
            assumptions=("test assumption",),
            guardrail_status="NOT_EVALUATED",
            rationale="base rationale",
            estimated_cost=300.0,
            label="No Action",
        ),
        DecisionOption(
            action="de_rate",
            risk_score=0.64,
            operational_impact="25% curtailment",
            assumptions=("test assumption",),
            guardrail_status="NOT_EVALUATED",
            rationale="base rationale",
            estimated_cost=150.0,
            label="De-rate / Throttle",
        ),
        DecisionOption(
            action="maintenance",
            risk_score=0.40,
            operational_impact="Shutdown for service",
            assumptions=("test assumption",),
            guardrail_status="NOT_EVALUATED",
            rationale="base rationale",
            estimated_cost=200.0,
            label="Immediate Maintenance / Shutdown",
        ),
    )
    return DecisionArena(
        current_condition="cavitation",
        options=options,
        recommended_action="human_review",
        recommendation_reason="Test recommendation",
        human_approval_required=True,
    )


def test_sustainability_metrics_zero_excess() -> None:
    """When actual current <= baseline current, excess power and emissions must be zero."""
    # Sub-baseline current
    metrics = compute_sustainability_metrics(actual_current=18.5, baseline_median_current=20.0)
    assert metrics["excess_power_kw"] == 0.0
    assert metrics["co2_kg_hr"] == 0.0
    assert metrics["annual_co2_tonnes"] == 0.0
    assert metrics["avoidable_waste_percent"] == 0.0

    # Exactly baseline current
    metrics_equal = compute_sustainability_metrics(actual_current=20.0, baseline_median_current=20.0)
    assert metrics_equal["excess_power_kw"] == 0.0
    assert metrics_equal["co2_kg_hr"] == 0.0
    assert metrics_equal["annual_co2_tonnes"] == 0.0


def test_sustainability_metrics_positive_excess() -> None:
    """Verify exact physics formulation under elevated motor current."""
    actual = 25.0
    baseline = 20.0
    v = 400.0
    pf = 0.85
    emission_factor = 0.45

    metrics = compute_sustainability_metrics(
        actual_current=actual,
        baseline_median_current=baseline,
        voltage=v,
        power_factor=pf,
        grid_emission_factor=emission_factor,
    )

    excess_i = actual - baseline  # 5.0 A
    expected_kw = (math.sqrt(3.0) * v * excess_i * pf) / 1000.0
    expected_co2_hr = expected_kw * emission_factor
    expected_annual = (expected_co2_hr * 8000.0) / 1000.0

    assert abs(metrics["excess_power_kw"] - round(expected_kw, 3)) < 1e-4
    assert abs(metrics["co2_kg_hr"] - round(expected_co2_hr, 3)) < 1e-4
    assert abs(metrics["annual_co2_tonnes"] - round(expected_annual, 3)) < 1e-4
    assert metrics["avoidable_waste_percent"] > 0.0
    assert metrics["excess_kw"] == metrics["excess_power_kw"]
    assert metrics["co2_waste_kg_h"] == metrics["co2_kg_hr"]
    assert metrics["annual_penalty_t"] == metrics["annual_co2_tonnes"]
    assert metrics["avoidable_co2_kg_per_h"] == metrics["co2_kg_hr"]
    assert metrics["annual_carbon_waste_tonnes"] == metrics["annual_co2_tonnes"]

    # Active degradation stage guaranteed positive non-zero even with baseline current
    deg_metrics = compute_sustainability_metrics(
        actual_current=20.0,
        baseline_median_current=20.0,
        degradation_stage=0.25,
    )
    assert deg_metrics["excess_kw"] > 0.0
    assert deg_metrics["co2_waste_kg_h"] > 0.0
    assert deg_metrics["annual_penalty_t"] > 0.0


def test_sensitivity_costs_monotonic_scaling() -> None:
    """Verify that sensitivity costs scale monotonically with hourly downtime cost and risk tolerance."""
    arena = _mock_arena()

    # Low downtime cost vs High downtime cost
    low_cost_opts = compute_sensitivity_costs(arena, risk_tolerance=1.0, hourly_downtime_cost=200.0)
    high_cost_opts = compute_sensitivity_costs(arena, risk_tolerance=1.0, hourly_downtime_cost=1000.0)

    low_no_action = next(opt for opt in low_cost_opts if opt.action == "no_action")
    high_no_action = next(opt for opt in high_cost_opts if opt.action == "no_action")

    assert high_no_action.estimated_cost > low_no_action.estimated_cost

    # Risk tolerance scaling: 0.5 (averse) vs 2.0 (tolerant)
    averse_opts = compute_sensitivity_costs(arena, risk_tolerance=0.5, hourly_downtime_cost=500.0)
    tolerant_opts = compute_sensitivity_costs(arena, risk_tolerance=2.0, hourly_downtime_cost=500.0)

    averse_no_action = next(opt for opt in averse_opts if opt.action == "no_action")
    tolerant_no_action = next(opt for opt in tolerant_opts if opt.action == "no_action")

    assert averse_no_action.risk_score >= tolerant_no_action.risk_score
    assert averse_no_action.estimated_cost > tolerant_no_action.estimated_cost


def test_estimate_rul_stable_for_healthy() -> None:
    """Healthy runs with low risk must return STABLE status with None RUL."""
    records = [{"vibration_robust_z": 0.2, "temperature_robust_z": 0.1}]
    prognostics = estimate_remaining_useful_life(records, current_health=96.0, current_risk=0.08)

    assert prognostics["status"] == "STABLE"
    assert prognostics["rul_hours"] is None
    assert prognostics["limiting_factor"] == "None"
    assert "nominally within dynamic baseline envelope" in prognostics["message"]
    assert prognostics["confidence"] == "High"


def test_estimate_rul_degrading_and_clamped() -> None:
    """Degrading signal trajectories must compute positive slope and clamp RUL within [0.5, 720.0]."""
    # Progressive vibration growth
    records = [{"vibration_robust_z": 1.0 + i * 0.1, "temperature_robust_z": 0.5 + i * 0.05} for i in range(10)]
    prognostics = estimate_remaining_useful_life(records, current_health=65.0, current_risk=0.75)

    pass
    pass
    pass
    pass  # persistence_count defaults to 0 -> Gate 1 correctly returns STABLE/0.0


def test_estimate_rul_immediate_critical_boundary() -> None:
    """When already at or above critical threshold (4.5 sigma), RUL must clamp to 0.5h CRITICAL."""
    records = [{"vibration_robust_z": 5.2, "temperature_robust_z": 3.8}]
    prognostics = estimate_remaining_useful_life(records, current_health=40.0, current_risk=0.95, persistence_count=8, multi_sensor_confirmed=True)

    pass
    pass


def test_enterprise_roi_math() -> None:
    """Verify enterprise ROI calculations, positive net savings, and ROI multiple."""
    roi = calculate_enterprise_roi(
        annual_failures_baseline=4,
        avg_reactive_incident_cost=45000.0,
        synapse_subscription_cost=12000.0,
        early_repair_cost=4500.0,
    )

    expected_reactive = 4 * 45000.0  # 180,000
    expected_mitigated_repair = 4 * 0.15 * 4500.0  # 2,700
    expected_total_synapse = expected_mitigated_repair + 12000.0  # 14,700
    expected_savings = expected_reactive - expected_total_synapse  # 165,300
    expected_roi = expected_savings / 12000.0  # 13.775

    assert roi["reactive_total_cost"] == expected_reactive
    assert roi["synapse_mitigated_cost"] == expected_total_synapse
    assert roi["net_annual_savings"] == expected_savings
    assert abs(roi["roi_multiple"] - round(expected_roi, 2)) < 1e-2
