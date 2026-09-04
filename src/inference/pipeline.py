"""End-to-end persisted-data validation orchestration."""

from dataclasses import dataclass
from pathlib import Path

from typing import Optional

from cleaning.sensor_cleaning import clean_records
from data.persistence import load_synthetic_csv
from decision.alerts import AlertEngine
from decision.arena import DecisionArena, build_decision_arena
from decision.diagnosis import DiagnosisResult, diagnose
from explainability.evidence import build_evidence_card
from decision.guardrails import GuardrailContext, GuardrailResult, evaluate_guardrails
from decision.risk_engine import RiskAssessment, assess_risk
from decision.simulation import SimulationApprovalError, simulate_action
from features.engineering import BaselineProfile, transform_records


@dataclass(frozen=True)
class PipelineRunResult:
    source_path: Path
    observation_count: int
    truth_count: int
    quality_flag_count: int
    run_count: int
    diagnosis_count: int
    evidence_count: int
    alert_count: int
    arena_count: int
    guardrail_count: int
    simulation_blocked: bool
    latest_diagnoses: tuple[DiagnosisResult, ...]


def run_persisted_pipeline(path: Path) -> PipelineRunResult:
    """Execute the persisted sensor-to-decision path without hardware effects."""
    observations, truth = load_synthetic_csv(path)
    cleaned = clean_records(observations)
    normal_training = [record for record, target in zip(cleaned.records, truth) if target.fault_type == "normal"]
    if not normal_training:
        raise ValueError("persisted dataset must contain normal training records")
    runs = sorted({target.run_id for target in truth})
    records_by_run: dict[str, list[object]] = {r: [] for r in runs}
    truth_by_run: dict[str, list[object]] = {r: [] for r in runs}
    for rec, tgt in zip(cleaned.records, truth):
        records_by_run[tgt.run_id].append(rec)
        truth_by_run[tgt.run_id].append(tgt)

    default_baseline = BaselineProfile.fit(normal_training)

    alert_count = 0
    diagnosis_count = 0
    evidence_count = 0
    arena_count = 0
    guardrail_count = 0
    latest: list[DiagnosisResult] = []
    simulation_blocked = False

    for run_id in runs:
        run_records = records_by_run[run_id]
        run_truth = truth_by_run[run_id]
        is_normal = run_truth[0].fault_type == "normal"
        if is_normal:
            run_training = [rec for r in runs if r != run_id for rec, tgt in zip(records_by_run[r], truth_by_run[r]) if tgt.fault_type == "normal"]
            if not run_training:
                run_training = normal_training
            baseline = BaselineProfile.fit(run_training)
        else:
            baseline = default_baseline

        run_features = transform_records(run_records, baseline)
        alert_engine = AlertEngine()
        last_diagnosis: Optional[DiagnosisResult] = None
        for point, (features, target) in enumerate(zip(run_features, run_truth)):
            diagnosis = diagnose(features)
            risk = assess_risk(
                diagnosis,
                persistence=(point + 1) / len(run_records),
                operating_load=float(features["operating_load"]),
                severity=target.severity,
            )
            evidence = build_evidence_card(
                features,
                diagnosis,
                baseline,
                timestamp=features["timestamp"],
                run_id=run_id,
                pump_id=str(features["pump_id"]),
            )
            alerts = alert_engine.process(
                timestamp=features["timestamp"],
                run_id=run_id,
                pump_id=str(features["pump_id"]),
                assessment=risk,
            )
            arena = build_decision_arena(diagnosis, risk)
            guardrails = evaluate_guardrails(
                arena.options[1].action,
                operating_load=float(features["operating_load"]),
                diagnosis_review_required=diagnosis.review_required,
                context=GuardrailContext(diagnostic_confidence=diagnosis.confidence),
            )
            alert_count += len(alerts)
            diagnosis_count += 1
            evidence_count += 1
            arena_count += 1
            guardrail_count += 1
            last_diagnosis = diagnosis
            if point == len(run_records) - 1 and guardrails.status != "PASS":
                try:
                    simulate_action("de_rate", run_records, risk, guardrails, human_approved=True)
                except SimulationApprovalError:
                    simulation_blocked = True
        if last_diagnosis is not None:
            latest.append(last_diagnosis)

    return PipelineRunResult(
        source_path=path,
        observation_count=len(observations),
        truth_count=len(truth),
        quality_flag_count=len(cleaned.quality_flags),
        run_count=len(runs),
        diagnosis_count=diagnosis_count,
        evidence_count=evidence_count,
        alert_count=alert_count,
        arena_count=arena_count,
        guardrail_count=guardrail_count,
        simulation_blocked=simulation_blocked,
        latest_diagnoses=tuple(latest),
    )
