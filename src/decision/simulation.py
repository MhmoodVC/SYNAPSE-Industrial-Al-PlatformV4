"""Human-approved, simulation-only action effects."""

from dataclasses import dataclass, replace
from typing import Optional

from data.synthetic import PumpObservation
from .guardrails import GuardrailResult
from .risk_engine import RiskAssessment


class SimulationApprovalError(RuntimeError):
    """Raised when a simulation is requested without required approval."""


@dataclass(frozen=True)
class SimulatedObservation:
    before: PumpObservation
    after: PumpObservation
    label: str = "SIMULATION"


@dataclass(frozen=True)
class SimulationResult:
    action: str
    before_risk: float
    after_risk: float
    observations: tuple[SimulatedObservation, ...]
    assumptions: tuple[str, ...]
    guardrail_status: str
    label: str = "SIMULATION"


def simulate_action(
    action: str,
    observations: list[PumpObservation],
    risk: RiskAssessment,
    guardrails: GuardrailResult,
    *,
    human_approved: bool = False,
) -> SimulationResult:
    """Simulate copied sensor trajectories only after approval and PASS status."""
    if not human_approved:
        raise SimulationApprovalError("human approval is required before simulation")
    if guardrails.status != "PASS":
        raise SimulationApprovalError(f"simulation blocked by guardrails: {guardrails.status}")
    if action not in {"no_action", "de_rate", "maintenance"}:
        raise ValueError("unsupported simulation action")
    after_risk = risk.score if action == "no_action" else risk.score * (0.80 if action == "de_rate" else 0.50)
    simulated = tuple(SimulatedObservation(observation, _apply_action(action, observation)) for observation in observations)
    assumptions = (
        "SIMULATION: no hardware command was issued",
        "SIMULATION ASSUMPTION: modeled action effect is not an engineering prediction",
    )
    return SimulationResult(action, risk.score, after_risk, simulated, assumptions, guardrails.status)


def _apply_action(action: str, observation: PumpObservation) -> PumpObservation:
    if action == "no_action":
        return observation
    if action == "de_rate":
        return replace(
            observation,
            operating_load=observation.operating_load * 0.75,
            flow=_scale(observation.flow, 0.75),
            motor_current=_scale(observation.motor_current, 0.85),
        )
    return observation


def _scale(value: Optional[float], factor: float) -> Optional[float]:
    return None if value is None else value * factor
