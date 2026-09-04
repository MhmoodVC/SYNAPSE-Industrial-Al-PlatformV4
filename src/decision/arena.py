"""Decision alternatives and transparent recommendation comparison."""

from dataclasses import dataclass

from .diagnosis import DiagnosisResult
from .risk_engine import RiskAssessment


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


@dataclass(frozen=True)
class DecisionArena:
    current_condition: str
    options: tuple[DecisionOption, ...]
    recommended_action: str
    recommendation_reason: str
    human_approval_required: bool


def build_decision_arena(
    diagnosis: DiagnosisResult,
    risk: RiskAssessment,
    *,
    operating_load: float = 0.70,
) -> DecisionArena:
    """Compare action alternatives without issuing or simulating commands.

    Risk adjustments and cost estimations are grounded in operating load and
    sensor risk exposure. Safety guardrails are evaluated in guardrails.py.
    """
    current = risk.score
    load = max(0.1, min(1.0, float(operating_load)))
    
    # Grounded cost estimates:
    # 1. No action: Expected unplanned failure loss = risk * load * baseline failure penalty ($500)
    no_action_cost = round(current * load * 500.0, 2)
    
    # 2. De-rate (Throttle): 25% throughput curtailment cost ($120 * load) + residual risk ($80 * risk*0.8)
    derate_cost = round(0.25 * load * 120.0 + (current * 0.80) * 80.0, 2)
    
    # 3. Maintenance: Scheduled intervention expense ($150) + residual risk ($40 * risk*0.5)
    maint_cost = round(150.0 + (current * 0.50) * 40.0, 2)

    options = (
        DecisionOption(
            action="no_action",
            risk_score=current,
            operational_impact="Full operational throughput (100%); zero immediate production loss",
            assumptions=("ASSUMPTION: operating condition and load remain unmitigated",),
            guardrail_status="NOT_EVALUATED",
            rationale="retains the current risk score without production curtailment",
            estimated_cost=no_action_cost,
            label="No Action",
        ),
        DecisionOption(
            action="de_rate",
            risk_score=max(0.0, current * 0.80),
            operational_impact="Load throttled by 25% to reduce component stress; 25% throughput curtailment",
            assumptions=("SIMULATION ASSUMPTION: 25% load de-rate reduces mechanical stress and modeled risk by 20%",),
            guardrail_status="NOT_EVALUATED",
            rationale="modeled risk is lower than no action while maintaining 75% throughput",
            estimated_cost=derate_cost,
            label="De-rate / Throttle",
        ),
        DecisionOption(
            action="maintenance",
            risk_score=max(0.0, current * 0.50),
            operational_impact="Complete pump shutdown for maintenance; 100% throughput loss unless backup available",
            assumptions=("SIMULATION ASSUMPTION: scheduled maintenance addresses root cause and reduces modeled risk by 50%",),
            guardrail_status="NOT_EVALUATED",
            rationale="modeled risk is lowest, subject to maintenance feasibility and backup availability",
            estimated_cost=maint_cost,
            label="Immediate Maintenance / Shutdown",
        ),
    )
    if diagnosis.review_required:
        return DecisionArena(
            diagnosis.diagnosis,
            options,
            "human_review",
            "Diagnosis is ambiguous or lacks sufficient evidence; no action is recommended.",
            True,
        )
    return DecisionArena(
        diagnosis.diagnosis,
        options,
        "human_review",
        "Guardrails are not yet evaluated; human review is required before selecting an action.",
        True,
    )
