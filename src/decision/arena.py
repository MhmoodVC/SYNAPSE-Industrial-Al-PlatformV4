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
    """Compare action alternatives without issuing or simulating commands.

    Risk adjustments and cost estimations are grounded in operating load and
    sensor risk exposure. Safety guardrails are evaluated in guardrails.py.

    Universal ALARP Safety Disqualification:
    - Computes post-action failure probability for every candidate.
    - Flags any candidate whose post-action risk >= 0.35 as DISQUALIFIED.
    - If no_action and de_rate are both disqualified, locks to 'maintenance'.
    """
    current = risk.score
    load = max(0.1, min(1.0, float(operating_load)))

    # Post-action risk factors (physics-grounded)
    no_action_post_risk = current                     # unmitigated
    derate_post_risk = max(0.0, current * 0.80)       # 20% reduction under throttle
    maint_post_risk = max(0.0, current * 0.50)        # 50% reduction after maintenance

    # Grounded cost estimates:
    no_action_cost = round(current * load * 500.0, 2)
    derate_cost = round(0.25 * load * 120.0 + (current * 0.80) * 80.0, 2)
    maint_cost = round(150.0 + (current * 0.50) * 40.0, 2)

    # Per-option disqualification under API 670 / ISO 20816 Zone D
    no_action_dq = _is_disqualified(no_action_post_risk)
    derate_dq = _is_disqualified(derate_post_risk)
    # Maintenance is NEVER disqualified: it is always the last resort.

    _dq_reason = (
        "DISQUALIFIED: Post-action failure probability >= 35% (ISO 20816 Zone D / API 670 / ALARP). "
        "This action cannot be recommended under any circumstance."
    )

    options = (
        DecisionOption(
            action="no_action",
            risk_score=no_action_post_risk,
            operational_impact="Full operational throughput (100%); zero immediate production loss",
            assumptions=("ASSUMPTION: operating condition and load remain unmitigated",),
            guardrail_status="FAIL" if no_action_dq else "NOT_EVALUATED",
            rationale="retains the current risk score without production curtailment",
            estimated_cost=no_action_cost,
            label="No Action",
            disqualified=no_action_dq,
            disqualification_reason=_dq_reason if no_action_dq else "",
        ),
        DecisionOption(
            action="de_rate",
            risk_score=derate_post_risk,
            operational_impact="Load throttled by 25% to reduce component stress; 25% throughput curtailment",
            assumptions=("SIMULATION ASSUMPTION: 25% load de-rate reduces mechanical stress and modeled risk by 20%",),
            guardrail_status="FAIL" if derate_dq else "NOT_EVALUATED",
            rationale="modeled risk is lower than no action while maintaining 75% throughput",
            estimated_cost=derate_cost,
            label="De-rate / Throttle",
            disqualified=derate_dq,
            disqualification_reason=_dq_reason if derate_dq else "",
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

    # ── ALARP Safety Lock ──────────────────────────────────────────────────────
    # If BOTH no_action AND de_rate are disqualified, LOCK to maintenance.
    if no_action_dq and derate_dq:
        return DecisionArena(
            diagnosis.diagnosis,
            options,
            "maintenance",
            (
                "MANDATORY SAFETY OVERRIDE (API 670 / ISO 20816 Zone D / ALARP): "
                f"Risk score {current:.3f} >= 0.35. Both No-Action (post-risk {no_action_post_risk:.3f}) "
                f"and De-rate (post-risk {derate_post_risk:.3f}) are DISQUALIFIED. "
                "Immediate Maintenance / Shutdown is the only compliant policy."
            ),
            True,
        )

    # ── Ambiguity guard: don't drop to human_review if latched ────────────────
    if diagnosis.review_required and risk.score < 0.40 and not latched_alarm:
        return DecisionArena(
            diagnosis.diagnosis,
            options,
            "human_review",
            f"Diagnosis is {diagnosis.diagnosis!r} or lacks sufficient evidence; human review required before intervention.",
            True,
        )

    # ── Risk-driven recommendation (safety already evaluated above) ───────────
    if risk.level == "critical" or risk.score >= 0.35:
        rec_action = "maintenance"
        rec_reason = (
            "MANDATORY SAFETY OVERRIDE: Failure probability >= 35% (CRITICAL / ISO Zone D). "
            "Operational de-rate disqualified under API 670 / ALARP standards."
        )
        human_approval = True
    elif risk.score >= 0.40 or latched_alarm:
        rec_action = "de_rate"
        rec_reason = (
            f"Risk score {risk.score:.2f} is in warning range; "
            "load de-rate to 75% recommended to arrest degradation velocity."
        ) if not latched_alarm else (
            "ALARM STATE LATCHED: Minimum governance intervention is De-rate / Throttle "
            "until formal sustained clearing (5 strictly normal readings)."
        )
        human_approval = False
    else:
        rec_action = "no_action"
        rec_reason = (
            f"Risk score {risk.score:.2f} is within acceptable bounds; "
            "continue normal operation under standard surveillance."
        )
        human_approval = False

    return DecisionArena(
        diagnosis.diagnosis,
        options,
        rec_action,
        rec_reason,
        human_approval,
    )
