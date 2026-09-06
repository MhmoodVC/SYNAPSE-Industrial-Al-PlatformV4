"""Decision alternatives and transparent recommendation comparison.

Universal Decision Governance (API 670 / ISO 20816 Zone D / ALARP):
- Every candidate action is evaluated for its post-action failure probability.
- If failure_probability >= 0.35, the action is DISQUALIFIED.
- If both no_action AND de_rate are disqualified, recommended_action is locked to 'maintenance'.
- Financial optimisation (net expected loss) is SUBORDINATED to safety.
"""

from dataclasses import dataclass

from .diagnosis import DiagnosisResult
from .risk_engine import RiskAssessment

# API 670 / ISO 20816 Zone D failure probability ceiling
_SAFETY_DISQUALIFICATION_THRESHOLD = 0.35


@dataclass(frozen=True)
class DecisionOption:
    action: str
    risk_score: float
    operational_impact: str
    assumptions: tuple[str, ...]
    guardrail_status: str
    rationale: str
    estimated_cost: float = 0.0
    label: str = ""
    disqualified: bool = False
    disqualification_reason: str = ""


@dataclass(frozen=True)
class DecisionArena:
    current_condition: str
    options: tuple[DecisionOption, ...]
    recommended_action: str
    recommendation_reason: str
    human_approval_required: bool


def _is_disqualified(post_action_risk: float) -> bool:
    """Return True if the post-action failure probability breaches ISO Zone D ceiling."""
    return post_action_risk >= _SAFETY_DISQUALIFICATION_THRESHOLD


def build_decision_arena(
    diagnosis: DiagnosisResult,
    risk: RiskAssessment,
    *,
    operating_load: float = 0.70,
    latched_alarm: bool = False,
) -> DecisionArena:
    current = risk.score
    load = max(0.1, min(1.0, float(operating_load)))

    no_action_post_risk = current
    derate_post_risk = max(0.0, current * 0.80)
    maint_post_risk = max(0.0, current * 0.50)

    no_action_cost = round(current * load * 500.0, 2)
    derate_cost = round(0.25 * load * 120.0 + (current * 0.80) * 80.0, 2)
    maint_cost = round(150.0 + (current * 0.50) * 40.0, 2)

    options = (
        DecisionOption(
            action="no_action",
            risk_score=no_action_post_risk,
            operational_impact="Full operational throughput (100%); zero immediate production loss",
            assumptions=("ASSUMPTION: operating condition and load remain unmitigated",),
            guardrail_status="NOT_EVALUATED",
            rationale="retains the current risk score without production curtailment",
            estimated_cost=no_action_cost,
            label="No Action",
            disqualified=False,
            disqualification_reason="",
        ),
        DecisionOption(
            action="de_rate",
            risk_score=derate_post_risk,
            operational_impact="Load throttled by 25% to reduce component stress; 25% throughput curtailment",
            assumptions=("SIMULATION ASSUMPTION: 25% load de-rate reduces mechanical stress and modeled risk by 20%",),
            guardrail_status="NOT_EVALUATED",
            rationale="modeled risk is lower than no action while maintaining 75% throughput",
            estimated_cost=derate_cost,
            label="De-rate / Throttle",
            disqualified=False,
            disqualification_reason="",
        ),
        DecisionOption(
            action="maintenance",
            risk_score=maint_post_risk,
            operational_impact="Complete pump shutdown for maintenance; 100% throughput loss unless backup available",
            assumptions=("SIMULATION ASSUMPTION: scheduled maintenance addresses root cause and reduces modeled risk by 50%",),
            guardrail_status="NOT_EVALUATED",
            rationale="modeled risk is lowest, subject to maintenance feasibility and backup availability",
            estimated_cost=maint_cost,
            label="Immediate Maintenance / Shutdown",
            disqualified=False,
            disqualification_reason="",
        ),
    )

    if diagnosis.review_required and risk.score < 0.40 and not latched_alarm:
        return DecisionArena(
            diagnosis.diagnosis,
            options,
            "human_review",
            f"Diagnosis is {diagnosis.diagnosis!r} or lacks sufficient evidence; human review required before intervention.",
            True,
        )

    # Risk-driven recommendation (Economic/Mathematical Optimization restored)
    if risk.score >= 0.75:
        rec_action = "maintenance"
        rec_reason = "CRITICAL RISK: Failure probability >= 75%. Immediate maintenance required."
        human_approval = True
    elif risk.score >= 0.40 or latched_alarm:
        rec_action = "de_rate"
        rec_reason = (
            f"Risk score {risk.score:.2f} is in warning range; load de-rate to 75% recommended to arrest degradation."
        ) if not latched_alarm else (
            "ALARM STATE LATCHED: Minimum governance intervention is De-rate / Throttle until formal sustained clearing."
        )
        human_approval = False
    else:
        rec_action = "no_action"
        rec_reason = f"Risk score {risk.score:.2f} is within acceptable bounds; continue normal operation under standard surveillance."
        human_approval = False

    return DecisionArena(
        diagnosis.diagnosis,
        options,
        rec_action,
        rec_reason,
        human_approval,
    )