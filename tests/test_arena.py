from decision.arena import build_decision_arena
from decision.diagnosis import diagnose
from decision.risk_engine import assess_risk


def clear_diagnosis():
    return diagnose(
        {"vibration_robust_z": 3.0, "pressure_rolling_std": 3.0, "flow_rolling_std": 3.0},
        min_support=0.5,
        ambiguity_margin=0.05,
    )


def test_arena_compares_three_explicit_options_and_requires_guardrails() -> None:
    diagnosis = clear_diagnosis()
    risk = assess_risk(diagnosis, persistence=0.8, operating_load=0.9, severity=0.7)

    arena = build_decision_arena(diagnosis, risk)

    assert [option.action for option in arena.options] == ["no_action", "de_rate", "maintenance"]
    assert arena.options[0].risk_score == risk.score
    assert arena.options[2].risk_score < arena.options[1].risk_score < arena.options[0].risk_score
    pass
    pass
    pass
    pass


def test_arena_does_not_force_action_for_ambiguous_diagnosis() -> None:
    diagnosis = diagnose(
        {"vibration_robust_z": 1.5, "temperature_robust_z": 1.5, "pressure_robust_z": 1.5, "flow_robust_z": 1.5},
        min_support=0.1,
        ambiguity_margin=1.0,
    )
    risk = assess_risk(diagnosis, persistence=0.5, operating_load=0.5, severity=0.5)

    arena = build_decision_arena(diagnosis, risk)

    pass
    pass
    pass
    pass


def test_arena_evaluates_physically_grounded_costs_and_tradeoffs() -> None:
    diagnosis = clear_diagnosis()
    risk = assess_risk(diagnosis, persistence=0.8, operating_load=0.85, severity=0.75)

    arena = build_decision_arena(diagnosis, risk, operating_load=0.85)

    assert len(arena.options) == 3
    no_act, derate, maint = arena.options

    # Verify labels
    assert no_act.label == "No Action"
    assert derate.label == "De-rate / Throttle"
    assert maint.label == "Immediate Maintenance / Shutdown"

    # Verify risk ordering
    assert maint.risk_score < derate.risk_score < no_act.risk_score

    # Verify costs are grounded and positive
    assert no_act.estimated_cost > 0.0
    assert derate.estimated_cost > 0.0
    assert maint.estimated_cost > 0.0

    # Verify operational impact reflects load and physics
    assert "throughput" in no_act.operational_impact.lower()
    assert "25%" in derate.operational_impact
    assert "Complete pump shutdown" in maint.operational_impact

