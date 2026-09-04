"""Safety and feasibility guardrails for human-approved simulations."""

from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class GuardrailContext:
    max_operating_load: Optional[float] = None
    production_impact_limit: Optional[float] = None
    maintenance_available: Optional[bool] = None
    backup_available: Optional[bool] = None
    evidence_sufficient: bool = True
    diagnostic_confidence: Optional[float] = None
    confidence_threshold: float = 0.50
    contradictory_evidence: bool = False


@dataclass(frozen=True)
class GuardrailCheck:
    name: str
    status: str
    reason: str


@dataclass(frozen=True)
class GuardrailResult:
    action: str
    status: str
    checks: tuple[GuardrailCheck, ...]
    human_review_required: bool


def evaluate_guardrails(action: str, *, operating_load: float, diagnosis_review_required: bool, context: GuardrailContext) -> GuardrailResult:
    """Evaluate constraints without inventing missing engineering information."""
    if not 0 <= operating_load <= 1:
        raise ValueError("operating_load must be between 0 and 1")
    if not 0 <= context.confidence_threshold <= 1:
        raise ValueError("confidence_threshold must be between 0 and 1")
    checks = [
        _safety_check(action, operating_load, context),
        _evidence_check(diagnosis_review_required, context),
        _confidence_check(context),
        _contradiction_check(context),
    ]
    if action == "maintenance":
        checks.append(_boolean_check("maintenance_availability", context.maintenance_available, "maintenance availability"))
        checks.append(_boolean_check("backup_availability", context.backup_available, "backup availability"))
    if action == "de_rate":
        checks.append(_production_check(context))
    status = "FAIL" if any(check.status == "FAIL" for check in checks) else "UNKNOWN" if any(check.status == "UNKNOWN" for check in checks) else "PASS"
    return GuardrailResult(action, status, tuple(checks), status != "PASS")


def _safety_check(action: str, operating_load: float, context: GuardrailContext) -> GuardrailCheck:
    if context.max_operating_load is None:
        return GuardrailCheck("safety_bound", "UNKNOWN", "maximum safe operating load was not supplied")
    if not 0 <= context.max_operating_load <= 1:
        return GuardrailCheck("safety_bound", "FAIL", "configured maximum safe operating load is invalid")
    proposed_load = operating_load * 0.75 if action == "de_rate" else operating_load
    return GuardrailCheck("safety_bound", "PASS" if proposed_load <= context.max_operating_load else "FAIL", f"proposed load {proposed_load} checked against configured maximum")


def _evidence_check(review_required: bool, context: GuardrailContext) -> GuardrailCheck:
    if review_required or not context.evidence_sufficient:
        return GuardrailCheck("evidence_sufficiency", "FAIL", "evidence is insufficient or diagnosis requires review")
    return GuardrailCheck("evidence_sufficiency", "PASS", "evidence sufficiency requirement passed")


def _confidence_check(context: GuardrailContext) -> GuardrailCheck:
    if context.diagnostic_confidence is None:
        return GuardrailCheck("diagnostic_confidence", "UNKNOWN", "diagnostic confidence was not supplied")
    return GuardrailCheck("diagnostic_confidence", "PASS" if context.diagnostic_confidence >= context.confidence_threshold else "FAIL", "confidence compared with configured threshold")


def _contradiction_check(context: GuardrailContext) -> GuardrailCheck:
    return GuardrailCheck("contradictory_evidence", "FAIL" if context.contradictory_evidence else "PASS", "contradictory evidence flag evaluated")


def _production_check(context: GuardrailContext) -> GuardrailCheck:
    if context.production_impact_limit is None:
        return GuardrailCheck("production_impact", "UNKNOWN", "production impact limit was not supplied")
    return GuardrailCheck("production_impact", "PASS" if 0.25 <= context.production_impact_limit <= 1 else "FAIL", "configured production impact limit is available")


def _boolean_check(name: str, value: Optional[bool], label: str) -> GuardrailCheck:
    if value is None:
        return GuardrailCheck(name, "UNKNOWN", f"{label} was not supplied")
    return GuardrailCheck(name, "PASS" if value else "FAIL", f"{label} is {'available' if value else 'not available'}")
