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
) -> RiskAssessment:
    """Calculate bounded, explainable risk from explicit normalized inputs.

    The score is a simulation/configuration score, not a failure probability.
    """
    values = {
        "diagnostic_support": _bounded(diagnosis.confidence or 0.0),
        "persistence": _bounded(persistence),
        "operating_load": _bounded(operating_load),
        "severity": _bounded(severity),
    }
    weights = {
        "diagnostic_support": 0.40,
        "persistence": 0.25,
        "operating_load": 0.15,
        "severity": 0.20,
    }
    reasons = {
        "diagnostic_support": "diagnostic support increased risk",
        "persistence": "abnormal behavior persisted",
        "operating_load": "operating load increased exposure",
        "severity": "scenario severity increased",
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
