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
    persistence_count: int = 0
    multi_sensor_confirmed: bool = False
    alert_state: str = "NORMAL"


from functools import lru_cache

@lru_cache(maxsize=8)
def _get_parsed_dataset(path_str: str) -> Tuple[Tuple[Any, ...], Tuple[Any, ...]]:
    obs, truth = load_synthetic_csv(Path(path_str))
    return tuple(obs), tuple(truth)


@lru_cache(maxsize=128)
def _get_run_data_and_baseline(path_str: str, run_id: str) -> Tuple[Tuple[Any, ...], BaselineProfile]:
    obs, truth = _get_parsed_dataset(path_str)
    selected = tuple(obs[i] for i, item in enumerate(truth) if item.run_id == run_id)
    if not selected:
        raise ValueError(f"unknown run: {run_id}")
    training_indices = [index for index, item in enumerate(truth) if item.fault_type == "normal" and item.run_id != run_id]
    if not training_indices:
        training_indices = [index for index, item in enumerate(truth) if item.run_id != run_id]
    training = [obs[index] for index in training_indices]
    baseline = BaselineProfile.fit(training)
    return selected, baseline


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
    run_observations, baseline = _get_run_data_and_baseline(str(path.resolve()), run_id)
    current_index = min(max(0, row_index), len(run_observations) - 1)

    # Transform historical sequence up to current step with baseline profile
    transformed = transform_records(run_observations[: current_index + 1], baseline)
    current = transformed[-1]
    diagnosis = diagnose(current)

    # Compute causal degradation proxy / health score
    active_records = run_observations[: current_index + 1]
    health = compute_health_score(active_records) if len(active_records) >= 10 else None

    # Compute multi-sensor confirmation from robust deviations
    devs = health.deviations if health and health.deviations else {}
    anomalous_sensors = sum(1 for v in devs.values() if isinstance(v, (int, float)) and abs(v) > 1.5)
    multi_sensor_confirmed = anomalous_sensors >= 2

    # True Leaky Integrator & Universal Alarm State Machine (Forward Pass)
    # A single ambiguous dip drops the count by 1 (floor 0) rather than resetting.
    # To clear a latched alarm, 15 consecutive 'normal' readings are required.
    persistence_count = 0
    alert_state = "NORMAL"
    consecutive_clean = 0

    for idx in range(current_index + 1):
        d_result = diagnose(transformed[idx])
        is_fault = d_result.diagnosis not in ("normal", "unknown", "ambiguous")
        
        # We need a frame-level multi-sensor check for the schmitt trigger
        f_health = compute_health_score(transformed[:idx+1])
        f_devs = f_health.deviations if f_health and f_health.deviations else {}
        f_anomalous = sum(1 for v in f_devs.values() if isinstance(v, (int, float)) and abs(v) > 1.5)
        f_multi = f_anomalous >= 2
        
        if is_fault:
            persistence_count = min(30, persistence_count + 1)
            consecutive_clean = 0
        else:
            persistence_count = max(0, persistence_count - 1)
            consecutive_clean += 1
                
        # Schmitt Trigger State Machine
        if alert_state == "NORMAL":
            if persistence_count >= 8 and f_multi:
                alert_state = "CRITICAL"
            elif persistence_count >= 4:
                alert_state = "WARNING"
        elif alert_state == "WARNING":
            if persistence_count <= 1:
                alert_state = "NORMAL"
            elif persistence_count >= 8 and f_multi:
                alert_state = "CRITICAL"
        elif alert_state == "CRITICAL":
            if persistence_count <= 4:
                alert_state = "WARNING"
            if persistence_count <= 1:
                alert_state = "NORMAL"
                
    latched_alarm = alert_state in ("WARNING", "CRITICAL")
    is_confirmed = latched_alarm
    persistence_fraction = min(1.0, persistence_count / 5.0) if is_confirmed else 0.0

    risk = assess_risk(
        diagnosis,
        persistence=persistence_fraction,
        operating_load=float(current["operating_load"]),
        severity=diagnosis.confidence or 0.0,
        persistence_count=persistence_count,
        multi_sensor_confirmed=multi_sensor_confirmed,
        latched_alarm=latched_alarm,
    )
    evidence = build_evidence_card(
        current,
        diagnosis,
        baseline,
        timestamp=current["timestamp"],
        run_id=run_id,
        pump_id=str(current["pump_id"]),
    )
    arena = build_decision_arena(
        diagnosis, 
        risk, 
        operating_load=float(current["operating_load"]),
        latched_alarm=latched_alarm
    )
    context = GuardrailContext(diagnostic_confidence=diagnosis.confidence)
    guardrails = evaluate_guardrails(
        action,
        operating_load=float(current["operating_load"]),
        diagnosis_review_required=diagnosis.review_required,
        context=context,
    )

    return ReplaySnapshot(
        alert_state=alert_state,
        observations=tuple(run_observations),
        current_features=current,
        diagnosis=diagnosis,
        evidence=evidence,
        risk=risk,
        arena=arena,
        guardrails=guardrails,
        health_score=health,
        persistence_count=persistence_count,
        multi_sensor_confirmed=multi_sensor_confirmed,
    )
