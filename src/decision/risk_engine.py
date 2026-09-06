"""Transparent risk scoring from diagnosis and operating evidence."""

from dataclasses import dataclass
from typing import Optional

from .diagnosis import DiagnosisResult


@dataclass(frozen=True)
class RiskContribution:
    name: str
    value: float
    weight: float
    weighted_value: float
    reason: str


@dataclass(frozen=True)
class RiskAssessment:
    score: float
    level: str
    contributions: tuple[RiskContribution, ...]
    review_required: bool


def assess_risk(
    diagnosis: DiagnosisResult,
    *,
    persistence: float = 0.0,
    operating_load: float = 0.0,
    severity: float = 0.0,
    persistence_count: Optional[int] = None,
    multi_sensor_confirmed: Optional[bool] = None,
    latched_alarm: bool = False,
) -> RiskAssessment:
    """Calculate bounded, explainable risk from explicit normalized inputs.

    The score is a simulation/configuration score, not a failure probability.
    """
    is_fault = diagnosis.diagnosis not in ("normal", "unknown", "ambiguous")
    
    # Universal Alarm State Machine Hysteresis:
    # If the system is in a LATCHED_ALARM state, any transient ambiguous/normal 
    # step is promoted to a latched fault to preserve the elevated risk governance.
    if latched_alarm:
        is_fault = True

    is_confirmed_fault = is_fault
    if is_fault and persistence_count is not None:
        # If latched_alarm is true, we consider it confirmed.
        if persistence_count < 3 and not multi_sensor_confirmed and not latched_alarm:
            is_confirmed_fault = False

    # For latched (promoted) ambiguous steps, use a conservative support floor
    if latched_alarm and is_confirmed_fault:
        latched_confidence = max(0.50, _bounded((persistence_count or 3) / 30.0))
        fault_support = latched_confidence
        fault_severity = latched_confidence * 0.6
        fault_persistence = _bounded(persistence)
    else:
        fault_support = _bounded(diagnosis.confidence or 0.0) if is_confirmed_fault else 0.0
        fault_severity = _bounded(severity) if is_confirmed_fault else 0.0
        fault_persistence = _bounded(persistence) if is_confirmed_fault else 0.0

    values = {
        "diagnostic_support": fault_support,
        "persistence": fault_persistence,
        "operating_load": _bounded(operating_load),
        "severity": fault_severity,
    }
    weights = {
        "diagnostic_support": 0.40,
        "persistence": 0.25,
        "operating_load": 0.15,
        "severity": 0.20,
    }
    reasons = {
        "diagnostic_support": "diagnostic support increased risk" if is_confirmed_fault else "nominal diagnosis indicates low risk",
        "persistence": "abnormal behavior persisted" if is_confirmed_fault else "nominal persistence indicates low risk",
        "operating_load": "operating load increased exposure",
        "severity": "scenario severity increased" if is_confirmed_fault else "nominal operating severity",
    }
    contributions = tuple(
        RiskContribution(name, values[name], weights[name], values[name] * weights[name], reasons[name])
        for name in values
    )
    score = min(1.0, sum(item.weighted_value for item in contributions))
    level = "critical" if score >= 0.75 else "warning" if score >= 0.40 else "normal"
    return RiskAssessment(score, level, contributions, diagnosis.review_required)



def _bounded(value: float) -> float:
    if not isinstance(value, (int, float)):
        raise ValueError("risk inputs must be numeric")
    if value != value:
        raise ValueError("risk inputs must not be NaN")
    return max(0.0, min(1.0, float(value)))
