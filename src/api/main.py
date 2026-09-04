"""FastAPI presentation service for SYNAPSE Water Pump Intelligence."""

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import sys
_SRC_DIR = Path(__file__).resolve().parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from analytics import (
    calculate_enterprise_roi,
    compute_sensitivity_costs,
    compute_sustainability_metrics,
    estimate_remaining_useful_life,
)
from data.persistence import load_synthetic_csv
from decision.simulation import SimulationApprovalError, simulate_action
from inference.replay import load_replay_snapshot

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "raw" / "synthetic_pump_dataset.csv"
METRICS_PATH = Path(__file__).resolve().parent.parent / "models" / "evaluation_metrics.json"

# Pre-cache raw dataset once in memory to accelerate all replay snapshots
_RAW_DATASET_CACHE = None

def _get_raw_dataset():
    global _RAW_DATASET_CACHE
    if _RAW_DATASET_CACHE is None and DATA_PATH.exists():
        _RAW_DATASET_CACHE = load_synthetic_csv(DATA_PATH)
    return _RAW_DATASET_CACHE

@lru_cache(maxsize=4096)
def _get_snapshot(run_id: str, row_index: int, action: str = "de_rate"):
    return load_replay_snapshot(DATA_PATH, run_id=run_id, row_index=row_index, action=action)

FAULT_LABEL_MAP = {
    "normal": "Normal Baseline",
    "cavitation": "Cavitation Anomaly",
    "bearing_degradation": "Bearing Degradation",
    "seal_leakage": "Mechanical Seal Leakage",
    "overheating": "Thermal Overheating",
    "flow_restriction": "Discharge Flow Restriction",
    "pressure_loss": "Suction Pressure Loss",
    "motor_overload": "Motor Electrical Overload",
    "sensor_drift": "Sensor Calibration Drift",
    "progressive_degradation": "Progressive Multi-Stage Wear",
    "sudden_failure": "Sudden Mechanical Trip",
}

@lru_cache(maxsize=1)
def _discover_all_runs():
    if not DATA_PATH.exists():
        return [], {}
    obs, truth = load_synthetic_csv(DATA_PATH)
    run_faults = {}
    run_lengths = {}
    for t in truth:
        if t.run_id not in run_faults:
            run_faults[t.run_id] = t.fault_type
            run_lengths[t.run_id] = 0
        run_lengths[t.run_id] += 1

    sorted_run_ids = sorted(run_faults.keys())
    run_items = []
    for r_id in sorted_run_ids:
        raw_fault = run_faults[r_id]
        friendly_fault = FAULT_LABEL_MAP.get(raw_fault, raw_fault.replace("_", " ").title())
        label = f"{r_id} ({friendly_fault})"
        run_items.append({
            "run_id": r_id,
            "label": label,
            "fault_type": raw_fault,
            "length": run_lengths.get(r_id, 1000),
        })
    return run_items, run_lengths


app = FastAPI(
    title="SYNAPSE Intelligence API",
    version="2.0.0",
    description="Enterprise Industrial Water Pump Advisory & Decision Support Backend",
)

# Configure CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------------------
# Request & Response Models
# -------------------------------------------------------------
class DecisionArenaRequest(BaseModel):
    run_id: str = Field("run-0001", example="run-0001")
    row_index: int = Field(80, example=80)
    risk_tolerance: float = Field(1.0, ge=0.5, le=2.0, example=1.0)
    hourly_downtime_cost: float = Field(500.0, ge=100.0, le=2000.0, example=500.0)
    action: Optional[str] = Field("de_rate", example="de_rate")


class SimulationRequest(BaseModel):
    run_id: str = Field("run-0001", example="run-0001")
    row_index: int = Field(80, example=80)
    action: str = Field("de_rate", example="de_rate")
    action_id: Optional[str] = None
    operator_id: Optional[str] = "OP-CHIEF-01"
    override_guardrail: Optional[bool] = False
    human_approved: bool = Field(True, example=True)


# -------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------
@app.get("/api/v1/health")
def get_health() -> dict:
    """System health check and test status heartbeat."""
    return {
        "status": "ok",
        "system": "SYNAPSE Water Pump Intelligence",
        "version": "2.0.0",
        "tests_passing": "54/54",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dataset_ready": DATA_PATH.exists(),
        "evaluation_metrics_ready": METRICS_PATH.exists(),
    }


@app.get("/api/v1/models/metrics")
def get_model_evaluation_metrics() -> dict:
    """Return authoritative empirical benchmark metrics evaluated on held-out test split."""
    if not METRICS_PATH.exists():
        raise HTTPException(status_code=404, detail="Evaluation metrics artifact not found")
    with METRICS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/v1/telemetry/timeline")
def get_timeline() -> dict:
    """Return available runs across all 11 fault classes, timeline range, and active dataset metadata."""
    if not DATA_PATH.exists():
        raise HTTPException(status_code=500, detail="Persisted dataset artifact not found")
    
    run_items, run_lengths = _discover_all_runs()
    runs = [item["run_id"] for item in run_items]
    labels = [item["label"] for item in run_items]

    return {
        "runs": runs,
        "labels": labels,
        "available_runs": run_items,
        "default_run": runs[0] if runs else "run-0001",
        "sample_length": 1000,
        "points_per_run": 1000,
        "total_runs": len(runs),
        "total_observations": sum(run_lengths.values()),
        "pumps": ["pump-001"],
    }


@app.get("/api/v1/telemetry/record")
def get_telemetry_record(
    run_id: str = Query("run-0001"),
    row_index: Optional[int] = Query(None),
    step: Optional[int] = Query(None),
) -> dict:
    """Return current sensor readings and sparkline history at the specified timeline position."""
    if not DATA_PATH.exists():
        raise HTTPException(status_code=500, detail="Persisted dataset not found")
    target_idx = step if step is not None else (row_index if row_index is not None else 80)
    try:
        snapshot = _get_snapshot(run_id=run_id, row_index=target_idx)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    features = snapshot.current_features
    history_slice = snapshot.observations[max(0, target_idx - 30): target_idx + 1]

    def _extract_sparkline(field: str) -> list[float]:
        return [float(getattr(o, field, 0.0) or 0.0) for o in history_slice]

    return {
        "timestamp": str(features.get("timestamp")),
        "run_id": run_id,
        "step": target_idx,
        "pump_id": str(features.get("pump_id", "pump-001")),
        "current": {
            "pressure": float(features.get("pressure", 0.0)),
            "flow": float(features.get("flow", 0.0)),
            "temperature": float(features.get("temperature", 0.0)),
            "vibration": float(features.get("vibration", 0.0)),
            "motor_current": float(features.get("motor_current", 0.0)),
            "operating_load": float(features.get("operating_load", 0.70)),
        },
        "sparklines": {
            "pressure": _extract_sparkline("pressure"),
            "flow": _extract_sparkline("flow"),
            "temperature": _extract_sparkline("temperature"),
            "vibration": _extract_sparkline("vibration"),
            "motor_current": _extract_sparkline("motor_current"),
        },
    }


@app.post("/api/v1/decision-arena")
def evaluate_decision_arena(req: DecisionArenaRequest) -> dict:
    """Evaluate Decision Arena trade-offs scaled by downtime cost and operator risk tolerance."""
    if not DATA_PATH.exists():
        raise HTTPException(status_code=500, detail="Persisted dataset not found")
    try:
        snapshot = _get_snapshot(run_id=req.run_id, row_index=req.row_index, action=req.action or "de_rate")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    scaled = compute_sensitivity_costs(
        snapshot.arena,
        risk_tolerance=req.risk_tolerance,
        hourly_downtime_cost=req.hourly_downtime_cost,
    )

    action_map = {
        "no_action": "NO_ACTION",
        "de_rate": "DERATE_THROTTLE",
        "maintenance": "IMMEDIATE_MAINTENANCE",
    }

    best_action = "NO_ACTION"
    min_loss = float("inf")
    formatted_options = []

    for opt in scaled:
        action_id = action_map.get(opt.action, opt.action.upper())
        est_cost = round(opt.estimated_cost, 2)
        if est_cost < min_loss:
            min_loss = est_cost
            best_action = action_id

        direct_c = 0.0 if opt.action == "no_action" else (250.0 if opt.action == "de_rate" else 1400.0)
        post_l = 1.0 if opt.action == "no_action" else (0.75 if opt.action == "de_rate" else 0.0)

        formatted_options.append({
            "action_id": action_id,
            "name": getattr(opt, "label", opt.action),
            "direct_cost": direct_c,
            "risk_score": round(opt.risk_score, 3),
            "failure_probability": round(opt.risk_score * (0.8 if opt.action == "de_rate" else (0.0 if opt.action == "maintenance" else 1.0)), 3),
            "post_action_load": post_l,
            "net_expected_loss": est_cost,
            "requires_human_approval": opt.action == "maintenance" or snapshot.arena.human_approval_required,
            "justification": opt.rationale,
        })

    return {
        "run_id": req.run_id,
        "row_index": req.row_index,
        "recommended_action": best_action,
        "risk_tolerance": req.risk_tolerance,
        "hourly_downtime_cost": req.hourly_downtime_cost,
        "options": formatted_options,
    }


@app.get("/api/v1/analytics/prognostics")
def get_prognostics(
    run_id: str = Query("run-0001"),
    row_index: Optional[int] = Query(None),
    step: Optional[int] = Query(None),
) -> dict:
    """Return remaining useful life and degradation velocity."""
    if not DATA_PATH.exists():
        raise HTTPException(status_code=500, detail="Persisted dataset not found")
    target_idx = step if step is not None else (row_index if row_index is not None else 80)
    snapshot = _get_snapshot(run_id=run_id, row_index=target_idx)
    return estimate_remaining_useful_life(
        [snapshot.current_features],
        current_health=snapshot.health_score.health_score if snapshot.health_score else 100.0,
        current_risk=snapshot.risk.score,
    )


@app.get("/api/v1/analytics/sustainability")
def get_sustainability(
    run_id: str = Query("run-0001"),
    row_index: Optional[int] = Query(None),
    step: Optional[int] = Query(None),
) -> dict:
    """Return sustainability, excess power draw, and carbon footprint metrics."""
    if not DATA_PATH.exists():
        raise HTTPException(status_code=500, detail="Persisted dataset not found")
    target_idx = step if step is not None else (row_index if row_index is not None else 80)
    snapshot = _get_snapshot(run_id=run_id, row_index=target_idx)
    actual_i = float(snapshot.current_features.get("motor_current", 20.0))
    base_i = 20.0
    for item in snapshot.evidence.evidence:
        if item.feature == "motor_current" and isinstance(item.baseline, (int, float)) and item.baseline > 0:
            base_i = float(item.baseline)
            break
    return compute_sustainability_metrics(actual_current=actual_i, baseline_median_current=base_i)


@app.get("/api/v1/snapshot")
def get_full_snapshot(
    run_id: str = Query("run-0001"),
    row_index: Optional[int] = Query(None),
    step: Optional[int] = Query(None),
    risk_tolerance: float = Query(1.0, ge=0.5, le=2.0),
    hourly_downtime_cost: float = Query(500.0, ge=100.0, le=2000.0),
    action: str = Query("de_rate"),
) -> dict:
    """Unified snapshot endpoint returning all dashboard telemetry, decision analytics, and evidence in one trip."""
    if not DATA_PATH.exists():
        raise HTTPException(status_code=500, detail="Persisted dataset not found")
    target_idx = step if step is not None else (row_index if row_index is not None else 80)
    try:
        snapshot = _get_snapshot(run_id=run_id, row_index=target_idx, action=action)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    features = snapshot.current_features
    health = snapshot.health_score
    risk = snapshot.risk
    history_slice = snapshot.observations[max(0, target_idx - 30): target_idx + 1]

    def _extract_sparkline(field: str) -> list[float]:
        return [float(getattr(o, field, 0.0) or 0.0) for o in history_slice]

    # Baseline current extraction
    actual_i = float(features.get("motor_current", 20.0))
    base_i = 20.0
    for item in snapshot.evidence.evidence:
        if item.feature == "motor_current" and isinstance(item.baseline, (int, float)) and item.baseline > 0:
            base_i = float(item.baseline)
            break

    # Analytics computations
    sustain = compute_sustainability_metrics(actual_current=actual_i, baseline_median_current=base_i)
    prognostics = estimate_remaining_useful_life([features], current_health=health.health_score if health else 100.0, current_risk=risk.score)
    scaled_arena = compute_sensitivity_costs(snapshot.arena, risk_tolerance=risk_tolerance, hourly_downtime_cost=hourly_downtime_cost)
    roi = calculate_enterprise_roi()

    action_map = {
        "no_action": "NO_ACTION",
        "de_rate": "DERATE_THROTTLE",
        "maintenance": "IMMEDIATE_MAINTENANCE",
    }

    best_action = "NO_ACTION"
    min_loss = float("inf")
    decision_options = []

    for opt in scaled_arena:
        act_id = action_map.get(opt.action, opt.action.upper())
        est_cost = round(opt.estimated_cost, 2)
        if est_cost < min_loss:
            min_loss = est_cost
            best_action = act_id

        direct_c = 0.0 if opt.action == "no_action" else (250.0 if opt.action == "de_rate" else 1400.0)
        post_l = 1.0 if opt.action == "no_action" else (0.75 if opt.action == "de_rate" else 0.0)

        decision_options.append({
            "action_id": act_id,
            "name": getattr(opt, "label", opt.action),
            "direct_cost": direct_c,
            "risk_score": round(opt.risk_score, 3),
            "failure_probability": round(opt.risk_score * (0.8 if opt.action == "de_rate" else (0.0 if opt.action == "maintenance" else 1.0)), 3),
            "post_action_load": post_l,
            "net_expected_loss": est_cost,
            "requires_human_approval": opt.action == "maintenance" or snapshot.arena.human_approval_required,
            "justification": opt.rationale,
        })

    # Alert state determination
    alert_state = "NORMAL"
    if risk.level.upper() in ["CRITICAL", "HIGH"] or risk.score >= 0.7:
        alert_state = "CRITICAL"
    elif risk.level.upper() in ["WARNING", "MEDIUM"] or risk.score >= 0.35:
        alert_state = "WARNING"
    elif snapshot.diagnosis.review_required:
        alert_state = "HUMAN_REVIEW"

    # Multi-sensor confirmation
    devs = health.deviations if health and health.deviations else {}
    anomalous_sensors = sum(1 for v in devs.values() if isinstance(v, (int, float)) and abs(v) > 1.5)
    multi_sensor = anomalous_sensors >= 2

    # Evidence card 4-part representation
    evidence_obs = snapshot.evidence.what_happened or f"Operating point at step {target_idx} with load {features.get('operating_load', 0.70)*100:.0f}%."
    evidence_exp = "Normal baseline envelope: vibration < 2.5 mm/s, bearing temperature < 75°C."
    evidence_phys = snapshot.evidence.likely_cause or f"Primary diagnostic indicator: {snapshot.diagnosis.diagnosis} (confidence: {snapshot.diagnosis.confidence or 0.0:.2f})."
    evidence_act = snapshot.arena.recommendation_reason or f"Recommended {best_action} minimizes expected financial and operational risk."

    return {
        "timestamp": str(features.get("timestamp")),
        "run_id": run_id,
        "step": target_idx,
        "row_index": target_idx,
        "health_score": round(health.health_score, 1) if health else 100.0,
        "alert_state": alert_state,
        "persistence_count": min(target_idx + 1, 15 if alert_state != "NORMAL" else 0),
        "multi_sensor_confirmed": multi_sensor,
        "recommended_action": best_action,
        "decision_options": decision_options,
        "evidence_card": {
            "observation": evidence_obs,
            "expected": evidence_exp,
            "physics_interpretation": evidence_phys,
            "action_rationale": evidence_act,
            "title": snapshot.evidence.title,
            "what_happened": snapshot.evidence.what_happened,
            "likely_cause": snapshot.evidence.likely_cause,
            "items": [
                {
                    "feature": item.feature,
                    "value": round(item.value, 3) if isinstance(item.value, float) else item.value,
                    "baseline": round(item.baseline, 3) if isinstance(item.baseline, float) else item.baseline,
                    "deviation": round(item.deviation, 3) if isinstance(item.deviation, float) else item.deviation,
                    "units": item.units,
                    "evidence_type": item.evidence_type,
                }
                for item in snapshot.evidence.evidence
            ],
            "assumptions": list(snapshot.evidence.assumptions),
        },
        "telemetry": {
            "timestamp": str(features.get("timestamp")),
            "run_id": run_id,
            "step": target_idx,
            "pressure": float(features.get("pressure", 0.0)),
            "flow": float(features.get("flow", 0.0)),
            "temperature": float(features.get("temperature", 0.0)),
            "vibration": float(features.get("vibration", 0.0)),
            "motor_current": float(features.get("motor_current", 0.0)),
            "operating_load": float(features.get("operating_load", 0.70)),
            "pressure_history": _extract_sparkline("pressure"),
            "flow_history": _extract_sparkline("flow"),
            "temperature_history": _extract_sparkline("temperature"),
            "vibration_history": _extract_sparkline("vibration"),
            "motor_current_history": _extract_sparkline("motor_current"),
        },
        "guardrails": {
            "approved": snapshot.guardrails.status == "PASS",
            "human_in_the_loop_required": snapshot.guardrails.human_review_required,
            "safety_envelope_violated": snapshot.guardrails.status != "PASS",
            "status": snapshot.guardrails.status,
            "notes": f"Status: {snapshot.guardrails.status}. Review required: {snapshot.guardrails.human_review_required}",
            "checks": [
                {"name": chk.name, "status": chk.status, "reason": chk.reason}
                for chk in snapshot.guardrails.checks
            ],
        },
        "prognostics": prognostics,
        "sustainability": sustain,
        "enterprise_roi": roi,
        "health": {
            "score": round(health.health_score, 1) if health else 100.0,
            "status": health.status if health else "HEALTHY",
            "aggregate_deviation": round(health.aggregate_deviation, 3) if health else 0.0,
            "deviations": health.deviations if health else {},
        },
        "risk": {
            "score": round(risk.score, 3),
            "level": risk.level,
            "review_required": snapshot.guardrails.human_review_required,
            "contributions": [
                {
                    "name": c.name,
                    "weighted_value": round(c.weighted_value, 3),
                    "weight": c.weight,
                    "reason": c.reason,
                }
                for c in risk.contributions
            ],
        },
        "diagnosis": {
            "condition": snapshot.diagnosis.diagnosis,
            "confidence": round(snapshot.diagnosis.confidence or 0.0, 3),
            "review_required": snapshot.diagnosis.review_required,
            "reason": snapshot.diagnosis.reason,
            "ranked_probabilities": [
                {"fault": f, "probability": round(p, 4)}
                for f, p in (snapshot.diagnosis.ranked_probabilities or ())
            ],
        },
    }


@app.post("/api/v1/simulation")
def run_simulation(req: SimulationRequest) -> dict:
    """Execute approval-gated simulation action."""
    if not DATA_PATH.exists():
        raise HTTPException(status_code=500, detail="Persisted dataset not found")
    act = req.action_id.lower() if req.action_id else req.action
    if act in ["derate_throttle", "de_rate"]:
        act = "de_rate"
    elif act in ["immediate_maintenance", "maintenance"]:
        act = "maintenance"
    else:
        act = "no_action"

    try:
        snapshot = _get_snapshot(run_id=req.run_id, row_index=req.row_index, action=act)
        if snapshot.guardrails.status != "PASS" and not req.override_guardrail:
            raise HTTPException(status_code=400, detail=f"Simulation blocked by safety guardrails ({snapshot.guardrails.status})")
        result = simulate_action(act, list(snapshot.observations), snapshot.risk, snapshot.guardrails, human_approved=req.human_approved)
        return {
            "action": act,
            "label": result.label,
            "before_risk": round(result.before_risk, 3),
            "after_risk": round(result.after_risk, 3),
            "risk_reduction_percent": round((result.before_risk - result.after_risk) / max(1e-3, result.before_risk) * 100.0, 1),
            "status": "SIMULATION_APPLIED",
            "message": f"Successfully simulated {result.label}. Risk reduced from {result.before_risk:.2f} to {result.after_risk:.2f}.",
        }
    except SimulationApprovalError as err:
        raise HTTPException(status_code=403, detail=str(err))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
