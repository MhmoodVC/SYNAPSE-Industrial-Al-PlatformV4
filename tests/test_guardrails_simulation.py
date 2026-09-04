from datetime import datetime, timezone

import pytest

from data.synthetic import generate_runs
from decision.diagnosis import diagnose
from decision.guardrails import GuardrailContext, evaluate_guardrails
from decision.risk_engine import assess_risk
from decision.simulation import SimulationApprovalError, simulate_action


def make_case():
    observations, _ = generate_runs(seed=12, pump_ids=("pump-1",), scenarios=("normal",), points_per_run=12, missing_rate=0)
    diagnosis = diagnose({"vibration_robust_z": 3.0, "pressure_rolling_std": 3.0, "flow_rolling_std": 3.0}, min_support=0.5, ambiguity_margin=0.05)
    risk = assess_risk(diagnosis, persistence=0.8, operating_load=0.7, severity=0.6)
    context = GuardrailContext(
        max_operating_load=0.95,
        production_impact_limit=0.30,
        maintenance_available=True,
        backup_available=True,
        diagnostic_confidence=diagnosis.confidence,
    )
    guardrails = evaluate_guardrails("de_rate", operating_load=0.7, diagnosis_review_required=False, context=context)
    return observations, risk, guardrails


def test_guardrails_report_each_constraint_and_pass_when_configured() -> None:
    _, _, guardrails = make_case()

    assert guardrails.status == "PASS"
    assert guardrails.human_review_required is False
    assert {check.name for check in guardrails.checks} == {"safety_bound", "evidence_sufficiency", "diagnostic_confidence", "contradictory_evidence", "production_impact"}
    assert all(check.status == "PASS" for check in guardrails.checks)


def test_missing_or_conflicting_constraints_require_review() -> None:
    observations, _, _ = make_case()
    diagnosis = diagnose({"vibration_robust_z": 3.0, "pressure_robust_z": 3.0, "flow_robust_z": 3.0}, min_support=0.5, ambiguity_margin=0.05)
    context = GuardrailContext(contradictory_evidence=True, diagnostic_confidence=diagnosis.confidence)
    result = evaluate_guardrails("maintenance", operating_load=0.7, diagnosis_review_required=True, context=context)

    assert result.status == "FAIL"
    assert result.human_review_required is True
    assert any(check.name == "contradictory_evidence" and check.status == "FAIL" for check in result.checks)


def test_simulation_requires_approval_and_changes_only_simulated_copy() -> None:
    observations, risk, guardrails = make_case()

    with pytest.raises(SimulationApprovalError):
        simulate_action("de_rate", observations, risk, guardrails)

    result = simulate_action("de_rate", observations, risk, guardrails, human_approved=True)

    assert result.label == "SIMULATION"
    assert result.before_risk == risk.score
    assert result.after_risk < result.before_risk
    assert result.observations[0].before == observations[0]
    assert result.observations[0].after.operating_load < observations[0].operating_load
    assert result.observations[0].label == "SIMULATION"
