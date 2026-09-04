"""Presentation-ready replay snapshots composed from domain services.

Follows Clean Architecture:
- Single-point baseline calculation.
- Zero redundant feature transformations.
- Immutable domain snapshot composition.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

from data.persistence import load_synthetic_csv
from decision.arena import DecisionArena, build_decision_arena
from decision.diagnosis import DiagnosisResult, diagnose
from decision.guardrails import GuardrailContext, GuardrailResult, evaluate_guardrails
from decision.risk_engine import RiskAssessment, assess_risk
from explainability.evidence import EvidenceCard, build_evidence_card
from features.engineering import BaselineProfile, transform_records
from models.health_score import HealthScoreResult, compute_health_score


@dataclass(frozen=True)
class ReplaySnapshot:
    """Consolidated immutable snapshot of telemetry, diagnostics, and decision options."""

    observations: Tuple[Any, ...]
    current_features: Dict[str, Any]
    diagnosis: DiagnosisResult
    evidence: EvidenceCard
    risk: RiskAssessment
    arena: DecisionArena
    guardrails: GuardrailResult
    health_score: Optional[HealthScoreResult] = None


def load_replay_snapshot(
    path: Path,
    *,
    run_id: str,
    row_index: int,
    action: str = "de_rate",
) -> ReplaySnapshot:
    """Build one dashboard snapshot from the persisted CSV artifact.
    
    Args:
        path: Path to synthetic CSV dataset.
        run_id: Selected simulation run identifier.
        row_index: Timeline position index.
        action: Candidate intervention action to evaluate against safety guardrails.
        
    Returns:
        Fully hydrated, immutable ReplaySnapshot instance.
    """
    observations, truth = load_synthetic_csv(path)
    selected_indices = [index for index, item in enumerate(truth) if item.run_id == run_id]
    if not selected_indices:
        raise ValueError(f"unknown run: {run_id}")

    training_indices = [index for index, item in enumerate(truth) if item.fault_type == "normal" and item.run_id != run_id]
    if not training_indices:
        training_indices = [index for index, item in enumerate(truth) if item.run_id != run_id]

    training = [observations[index] for index in training_indices]
    run_observations = [observations[index] for index in selected_indices]
    current_index = min(max(0, row_index), len(run_observations) - 1)

    # Compute baseline profile once for both feature transformation and evidence derivation
    baseline = BaselineProfile.fit(training)

    # Transform historical sequence up to current step
    current = transform_records(training + run_observations[: current_index + 1], baseline)[-1]
    diagnosis = diagnose(current)
    
    persistence = min(1.0, (current_index + 1) / max(1, len(run_observations)))
    risk = assess_risk(
        diagnosis,
        persistence=persistence,
        operating_load=float(current["operating_load"]),
        severity=diagnosis.confidence or 0.0,
    )
    evidence = build_evidence_card(
        current,
        diagnosis,
        baseline,
        timestamp=current["timestamp"],
        run_id=run_id,
        pump_id=str(current["pump_id"]),
    )
    arena = build_decision_arena(diagnosis, risk, operating_load=float(current["operating_load"]))
    context = GuardrailContext(diagnostic_confidence=diagnosis.confidence)
    guardrails = evaluate_guardrails(
        action,
        operating_load=float(current["operating_load"]),
        diagnosis_review_required=diagnosis.review_required,
        context=context,
    )

    # Compute causal degradation proxy / health score
    active_records = run_observations[: current_index + 1]
    health = compute_health_score(active_records) if len(active_records) >= 10 else None

    return ReplaySnapshot(
        observations=tuple(run_observations),
        current_features=current,
        diagnosis=diagnosis,
        evidence=evidence,
        risk=risk,
        arena=arena,
        guardrails=guardrails,
        health_score=health,
    )
