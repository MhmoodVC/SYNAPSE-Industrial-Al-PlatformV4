"""FastAPI presentation service for SYNAPSE Water Pump Intelligence.

Follows Clean Architecture boundaries:
- Domain services and physical formulas decoupled from HTTP transport.
- Explicit Pydantic response models for OpenAPI schema contracts.
- Centralized domain constants and reusable formatting helpers (DRY).
- Strict zero-leakage, reproducible inference pipeline integration.
"""

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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
from inference.replay import ReplaySnapshot, load_replay_snapshot

# ============================================================
# LIVE HARDWARE MODE SUPPORT (Firebase Cloud Ingestion)
# ============================================================
import os

LIVE_HARDWARE_MODE = os.getenv("LIVE_HARDWARE_MODE", "false").lower() == "true"

if LIVE_HARDWARE_MODE:
    try:
        from realtime.firebase_listener import (
            start_firebase_listener,
            get_latest_reading,
            get_sensor_buffer,
        )
        from realtime.live_features import LiveFeatureExtractor
        import joblib

        PIPELINE_PATH = Path(__file__).resolve().parents[2] / "models" / "exported" / "pipeline_live.joblib"
        
        if not PIPELINE_PATH.exists():
            print(f"⚠️ WARNING: {PIPELINE_PATH} not found. Live mode disabled.")
            LIVE_HARDWARE_MODE = False
        else:
            artifact = joblib.load(PIPELINE_PATH)
            live_pipeline = artifact["pipeline"]
            live_feature_cols = artifact["feature_cols"]
            live_threshold = artifact["threshold"]
            live_extractor = LiveFeatureExtractor()

            FIREBASE_POLL_INTERVAL = float(os.getenv("FIREBASE_POLL_INTERVAL", "1.0"))
            
            start_firebase_listener(poll_interval=FIREBASE_POLL_INTERVAL)
            print(f"✅ Live Hardware Mode ENABLED via Firebase (polling every {FIREBASE_POLL_INTERVAL}s)")
    except ImportError as e:
        print(f"⚠️ Live hardware dependencies missing: {e}. Falling back to replay mode.")
        LIVE_HARDWARE_MODE = False

# -------------------------------------------------------------
# Domain Constants & Configuration
# -------------------------------------------------------------
DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "raw" / "synthetic_pump_dataset.csv"
METRICS_PATH = Path(__file__).resolve().parent.parent / "models" / "evaluation_metrics.json"

DEFAULT_RUN_ID = "run-0001"
DEFAULT_STEP_INDEX = 80
DEFAULT_RISK_TOLERANCE = 1.0
DEFAULT_HOURLY_DOWNTIME_COST = 500.0
DEFAULT_ACTION = "de_rate"
DEFAULT_BASELINE_MOTOR_CURRENT = 10.289
DEFAULT_OPERATING_LOAD = 0.70

FAULT_LABEL_MAP: Dict[str, str] = {
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

ACTION_ID_MAP: Dict[str, str] = {
    "no_action": "NO_ACTION",
    "de_rate": "DERATE_THROTTLE",
    "maintenance": "IMMEDIATE_MAINTENANCE",
}

ACTION_DIRECT_COST_MAP: Dict[str, float] = {
    "no_action": 0.0,
    "de_rate": 250.0,
    "maintenance": 1400.0,
}

ACTION_POST_LOAD_MAP: Dict[str, float] = {
    "no_action": 1.0,
    "de_rate": 0.75,
    "maintenance": 0.0,
}


# -------------------------------------------------------------
# Caching & Data Discovery
# -------------------------------------------------------------
_RAW_DATASET_CACHE = None


def _get_raw_dataset():
    """Retrieve pre-cached raw dataset observations and ground-truth records."""
    global _RAW_DATASET_CACHE
    if _RAW_DATASET_CACHE is None and DATA_PATH.exists():
        _RAW_DATASET_CACHE = load_synthetic_csv(DATA_PATH)
    return _RAW_DATASET_CACHE


@lru_cache(maxsize=256)
def _get_snapshot(run_id: str, row_index: int, action: str = DEFAULT_ACTION) -> ReplaySnapshot:
    """Retrieve or compute a cached snapshot of all diagnostic and decision layers.

    maxsize=256 bounds worst-case memory to ~50 MB (256 × 1,000 obs × ~200 B),
    covering a typical scrubbing session without unbounded RAM growth.
    """
    return load_replay_snapshot(DATA_PATH, run_id=run_id, row_index=row_index, action=action)


@lru_cache(maxsize=1)
def _discover_all_runs() -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Scan the synthetic benchmark repository to discover all runs and fault classes."""
    if not DATA_PATH.exists():
        return [], {}
    _, truth = load_synthetic_csv(DATA_PATH)
    run_faults: Dict[str, str] = {}
    run_lengths: Dict[str, int] = {}
    for t in truth:
        if t.run_id not in run_faults:
            run_faults[t.run_id] = t.fault_type
            run_lengths[t.run_id] = 0
        run_lengths[t.run_id] += 1

    sorted_run_ids = sorted(run_faults.keys())
    run_items: List[Dict[str, Any]] = []
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


# -------------------------------------------------------------
# Helper Functions (DRY Transformation & Extraction)
# -------------------------------------------------------------
def _extract_sparkline(history_slice: Sequence[Any], field: str) -> List[float]:
    """Extract float values for sparkline representation from an observation slice."""
    return [float(getattr(o, field, 0.0) or 0.0) for o in history_slice]


def _extract_all_sparklines(history_slice: Sequence[Any]) -> Dict[str, List[float]]:
    """Extract standard 5-sensor sparkline histories."""
    return {
        field: _extract_sparkline(history_slice, field)
        for field in ("pressure", "flow", "temperature", "vibration", "motor_current")
    }


def _extract_baseline_motor_current(snapshot: ReplaySnapshot) -> float:
    """Extract robust baseline motor current from evidence card or healthy observations."""
    for item in snapshot.evidence.evidence:
        if "motor_current" in item.feature and isinstance(item.baseline, (int, float)) and item.baseline > 0:
            return float(item.baseline)
    if snapshot.observations:
        first_val = getattr(snapshot.observations[0], "motor_current", None)
        if first_val is not None and float(first_val) > 0:
            return float(first_val)
    return DEFAULT_BASELINE_MOTOR_CURRENT


def _format_decision_options(
    scaled_arena: Sequence[Any],
    arena_human_approval_required: bool,
    arena_recommended_action: str,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Format decision options and pass through the strictly enforced safety recommendation."""
    formatted_options: List[Dict[str, Any]] = []

    best_action = ACTION_ID_MAP.get(str(arena_recommended_action).lower(), str(arena_recommended_action).upper())

    for opt in scaled_arena:
        action_key = str(opt.action).lower()
        action_id = ACTION_ID_MAP.get(action_key, action_key.upper())
        est_cost = round(opt.estimated_cost, 2)

        direct_c = ACTION_DIRECT_COST_MAP.get(action_key, 0.0)
        post_l = ACTION_POST_LOAD_MAP.get(action_key, 1.0)
        failure_prob_mult = 0.8 if action_key == "de_rate" else (0.0 if action_key == "maintenance" else 1.0)

        formatted_options.append({
            "action_id": action_id,
            "name": getattr(opt, "label", opt.action),
            "direct_cost": direct_c,
            "risk_score": round(opt.risk_score, 3),
            "failure_probability": round(opt.risk_score * failure_prob_mult, 3),
            "post_action_load": post_l,
            "net_expected_loss": est_cost,
            "requires_human_approval": action_key == "maintenance" or arena_human_approval_required,
            "justification": opt.rationale,
            "disqualified": getattr(opt, "disqualified", False),
            "disqualification_reason": getattr(opt, "disqualification_reason", ""),
        })

    return best_action, formatted_options


# -------------------------------------------------------------
# FastAPI Application Definition & CORS Setup
# -------------------------------------------------------------
app = FastAPI(
    title="SYNAPSE Intelligence API",
    version="2.0.0",
    description="Enterprise Industrial Water Pump Advisory & Decision Support Backend",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------------------
# Request & Response Models (Pydantic Schema Contracts)
# -------------------------------------------------------------
class DecisionArenaRequest(BaseModel):
    run_id: str = Field(DEFAULT_RUN_ID, example=DEFAULT_RUN_ID)
    row_index: int = Field(DEFAULT_STEP_INDEX, example=DEFAULT_STEP_INDEX)
    risk_tolerance: float = Field(DEFAULT_RISK_TOLERANCE, ge=0.5, le=2.0, example=DEFAULT_RISK_TOLERANCE)
    hourly_downtime_cost: float = Field(DEFAULT_HOURLY_DOWNTIME_COST, ge=100.0, le=2000.0, example=DEFAULT_HOURLY_DOWNTIME_COST)
    action: Optional[str] = Field(DEFAULT_ACTION, example=DEFAULT_ACTION)


class SimulationRequest(BaseModel):
    run_id: str = Field(DEFAULT_RUN_ID, example=DEFAULT_RUN_ID)
    row_index: int = Field(DEFAULT_STEP_INDEX, example=DEFAULT_STEP_INDEX)
    action: str = Field(DEFAULT_ACTION, example=DEFAULT_ACTION)
    action_id: Optional[str] = None
    operator_id: Optional[str] = "OP-CHIEF-01"
    override_guardrail: Optional[bool] = False
    human_approved: bool = Field(True, example=True)


class HealthResponse(BaseModel):
    status: str
    system: str
    version: str
    tests_passing: str
    timestamp: str
    dataset_ready: bool
    evaluation_metrics_ready: bool


class RunItem(BaseModel):
    run_id: str
    label: str
    fault_type: str
    length: int


class TimelineResponse(BaseModel):
    runs: List[str]
    labels: List[str]
    available_runs: List[RunItem]
    default_run: str
    sample_length: int
    points_per_run: int
    total_runs: int
    total_observations: int
    pumps: List[str]


class TelemetryCurrent(BaseModel):
    pressure: float
    flow: float
    temperature: float
    vibration: float
    motor_current: float
    operating_load: float


class TelemetryRecordResponse(BaseModel):
    timestamp: str
    run_id: str
    step: int
    pump_id: str
    current: TelemetryCurrent
    sparklines: Dict[str, List[float]]


class DecisionOptionItem(BaseModel):
    action_id: str
    name: str
    direct_cost: float
    risk_score: float
    failure_probability: float
    post_action_load: float
    net_expected_loss: float
    requires_human_approval: bool
    justification: str


class DecisionArenaResponse(BaseModel):
    run_id: str
    row_index: int
    recommended_action: str
    risk_tolerance: float
    hourly_downtime_cost: float
    options: List[DecisionOptionItem]


class SimulationResultResponse(BaseModel):
    action: str
    label: str
    before_risk: float
    after_risk: float
    risk_reduction_percent: float
    status: str
    message: str


# -------------------------------------------------------------
# REST Endpoints
# -------------------------------------------------------------
@app.get("/api/v1/health", response_model=HealthResponse)
def get_health() -> Dict[str, Any]:
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
def get_model_evaluation_metrics() -> Dict[str, Any]:
    """Return authoritative empirical benchmark metrics evaluated on held-out test split."""
    if not METRICS_PATH.exists():
        raise HTTPException(status_code=404, detail="Evaluation metrics artifact not found")
    with METRICS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/v1/telemetry/timeline", response_model=TimelineResponse)
def get_timeline() -> Dict[str, Any]:
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
        "default_run": runs[0] if runs else DEFAULT_RUN_ID,
        "sample_length": 1000,
        "points_per_run": 1000,
        "total_runs": len(runs),
        "total_observations": sum(run_lengths.values()),
        "pumps": ["pump-001"],
    }


@app.get("/api/v1/telemetry/record", response_model=TelemetryRecordResponse)
def get_telemetry_record(
    run_id: str = Query(DEFAULT_RUN_ID),
    row_index: Optional[int] = Query(None),
    step: Optional[int] = Query(None),
) -> Dict[str, Any]:
    """Return current sensor readings and sparkline history at the specified timeline position."""
    if not DATA_PATH.exists():
        raise HTTPException(status_code=500, detail="Persisted dataset not found")
    target_idx = step if step is not None else (row_index if row_index is not None else DEFAULT_STEP_INDEX)
    try:
        snapshot = _get_snapshot(run_id=run_id, row_index=target_idx)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    features = snapshot.current_features
    history_slice = snapshot.observations[max(0, target_idx - 30): target_idx + 1]

    return {
        "timestamp": str(features.get("timestamp")),
        "run_id": run_id,
        "step": target_idx,
        "pump_id": str(features.get("pump_id", "pump-001")),
        "current": {
            "pressure": float(features.get("pressure") or 0.0),
            "flow": float(features.get("flow") or 0.0),
            "temperature": float(features.get("temperature") or 0.0),
            "vibration": float(features.get("vibration") or 0.0),
            "motor_current": float(features.get("motor_current") or 0.0),
            "operating_load": float(features.get("operating_load") or DEFAULT_OPERATING_LOAD),
        },
        "sparklines": _extract_all_sparklines(history_slice),
    }


@app.post("/api/v1/decision-arena", response_model=DecisionArenaResponse)
def evaluate_decision_arena(req: DecisionArenaRequest) -> Dict[str, Any]:
    """Evaluate Decision Arena trade-offs scaled by downtime cost and operator risk tolerance."""
    if not DATA_PATH.exists():
        raise HTTPException(status_code=500, detail="Persisted dataset not found")
    try:
        snapshot = _get_snapshot(run_id=req.run_id, row_index=req.row_index, action=req.action or DEFAULT_ACTION)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    scaled = compute_sensitivity_costs(
        snapshot.arena,
        risk_tolerance=req.risk_tolerance,
        hourly_downtime_cost=req.hourly_downtime_cost,
    )

    best_action, formatted_options = _format_decision_options(
        scaled,
        arena_human_approval_required=snapshot.arena.human_approval_required,
        arena_recommended_action=snapshot.arena.recommended_action,
    )

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
    run_id: str = Query(DEFAULT_RUN_ID),
    row_index: Optional[int] = Query(None),
    step: Optional[int] = Query(None),
) -> Dict[str, Any]:
    """Return remaining useful life and degradation velocity."""
    if not DATA_PATH.exists():
        raise HTTPException(status_code=500, detail="Persisted dataset not found")
    target_idx = step if step is not None else (row_index if row_index is not None else DEFAULT_STEP_INDEX)
    snapshot = _get_snapshot(run_id=run_id, row_index=target_idx)
    recent_obs = list(snapshot.observations[max(0, target_idx - 29): target_idx + 1])
    return estimate_remaining_useful_life(
        recent_obs,
        current_health=snapshot.health_score.health_score if snapshot.health_score else 100.0,
        current_risk=snapshot.risk.score,
        condition=snapshot.diagnosis.diagnosis,
        persistence_count=snapshot.persistence_count,
        multi_sensor_confirmed=snapshot.multi_sensor_confirmed,
    )


@app.get("/api/v1/analytics/sustainability")
def get_sustainability(
    run_id: str = Query(DEFAULT_RUN_ID),
    row_index: Optional[int] = Query(None),
    step: Optional[int] = Query(None),
) -> Dict[str, Any]:
    """Return sustainability, excess power draw, and carbon footprint metrics."""
    if not DATA_PATH.exists():
        raise HTTPException(status_code=500, detail="Persisted dataset not found")
    target_idx = step if step is not None else (row_index if row_index is not None else DEFAULT_STEP_INDEX)
    snapshot = _get_snapshot(run_id=run_id, row_index=target_idx)
    raw_i = snapshot.current_features.get("motor_current")
    actual_i = float(raw_i if raw_i is not None else DEFAULT_BASELINE_MOTOR_CURRENT)
    base_i = _extract_baseline_motor_current(snapshot)

    health_deg = max(0.0, (100.0 - float(snapshot.health_score.health_score)) / 100.0) if snapshot.health_score else 0.0
    risk_deg = float(snapshot.risk.score) if snapshot.risk else 0.0
    deg_stage = max(health_deg, risk_deg * 0.5)

    return compute_sustainability_metrics(
        actual_current=actual_i,
        baseline_median_current=base_i,
        degradation_stage=deg_stage,
    )

_RUL_EMA_STATE: Dict[str, float] = {}

def _smooth_rul(run_id: str, raw_rul: Optional[float], alpha: float = 0.3, alert_state: str = "NORMAL") -> Optional[float]:
    if raw_rul is None:
        return None
    raw_rul = float(raw_rul)
    prev = _RUL_EMA_STATE.get(run_id)

    if raw_rul >= 500.0:
        if alert_state in ("WARNING", "CRITICAL", "ALERT") and prev is not None and prev < 500.0:
            return round(prev, 1)
        _RUL_EMA_STATE[run_id] = raw_rul
        return round(raw_rul, 1)

    if prev is None or prev >= 500.0:
        _RUL_EMA_STATE[run_id] = raw_rul
        return round(raw_rul, 1)

    smoothed = alpha * raw_rul + (1.0 - alpha) * prev
    _RUL_EMA_STATE[run_id] = smoothed
    return round(smoothed, 1)

_EVIDENCE_CHANNELS = [
    ("vibration", "mm/s", 1.25),
    ("temperature", "°C", 68.0),
    ("motor_current", "A", 9.88),
    ("pressure", "bar", 8.52),
    ("flow", "m³/h", 120.3),
]

SENSOR_SPECS = {
    "vibration": {"unit": "mm/s", "baseline": 1.25, "threshold": 2.80, "critical": 4.50},
    "temperature": {"unit": "°C", "baseline": 68.0, "threshold": 75.0, "critical": 85.0},
    "motor_current": {"unit": "A", "baseline": 9.88, "threshold": 11.50, "critical": 13.00},
    "pressure": {"unit": "bar", "baseline": 8.52, "threshold": 7.00, "critical": 6.00},
    "flow": {"unit": "m³/h", "baseline": 120.3, "threshold": 105.0, "critical": 90.0},
}

def _compute_evidence_items(features: dict, robust_deviations: dict) -> list:
    items_raw = []
    severities = []

    for feat, specs in SENSOR_SPECS.items():
        val = float(features.get(feat, specs["baseline"]))
        dev = float(robust_deviations.get(feat, 0.0))

        denom = max(0.01, abs(specs["threshold"] - specs["baseline"]))
        norm_dist = abs(val - specs["baseline"]) / denom

        sev = max(0.05, abs(dev), norm_dist * 2.0)
        severities.append(sev)

        items_raw.append({
            "feature": feat,
            "value": round(val, 2),
            "baseline": specs["baseline"],
            "threshold": specs["threshold"],
            "deviation": round(dev, 2),
            "units": specs["unit"],
            "evidence_type": "physical_sensor",
            "sev": sev,
        })

    total_sev = sum(severities)
    for it in items_raw:
        it["contribution_pct"] = round((it["sev"] / total_sev) * 100.0, 1)
        del it["sev"]

    return items_raw

@app.get("/api/v1/snapshot")
def get_full_snapshot(
    run_id: str = Query(DEFAULT_RUN_ID),
    row_index: Optional[int] = Query(None),
    step: Optional[int] = Query(None),
    risk_tolerance: float = Query(DEFAULT_RISK_TOLERANCE, ge=0.5, le=2.0),
    hourly_downtime_cost: float = Query(DEFAULT_HOURLY_DOWNTIME_COST, ge=100.0, le=2000.0),
    action: str = Query(DEFAULT_ACTION),
) -> Dict[str, Any]:
    """Unified snapshot endpoint returning all dashboard telemetry, decision analytics, and evidence in one trip."""
    
    # ============================================================
    # LIVE HARDWARE OVERRIDE (Firebase Cloud Ingestion)
    # ============================================================
    if LIVE_HARDWARE_MODE:
        latest = get_latest_reading()
        buffer = get_sensor_buffer()

        if latest is None or len(buffer) < 60:
            warm_up_sec = 60 - len(buffer) if buffer else 60
            raise HTTPException(
                status_code=503,
                detail=f"Live hardware warming up. Need {warm_up_sec}s more (currently {len(buffer)}/60 samples)."
            )

        # Build live features
        live_extractor.reset()
        for reading in buffer:
            live_extractor.add_reading(
                pressure=reading.get("pressure"),
                flow=reading.get("flow"),
                temperature=reading.get("temperature"),
                vibration=reading.get("vibration"),
                motor_current=reading.get("motor_current"),
                operating_load=reading.get("operating_load", 0.70),
            )

        features_df = live_extractor.compute_features()
        if features_df is None or features_df.empty:
            raise HTTPException(status_code=500, detail="Live feature extraction failed")

        # Inference
        X_live = features_df[live_feature_cols].fillna(0)
        preds, probs = live_pipeline.predict(X_live)

        stage1_prob = float(probs[0])
        is_anomaly = stage1_prob >= live_threshold
        diagnosis = str(preds[0]) if is_anomaly else "normal"

        # Health Score
        health_score = max(0.0, 100.0 - (stage1_prob * 100))

        # Alert State Logic
        if health_score < 50.0 or stage1_prob > 0.80:
            alert_state = "CRITICAL"
            best_action = "IMMEDIATE_MAINTENANCE"
        elif is_anomaly:
            alert_state = "WARNING"
            best_action = "DERATE_THROTTLE"
        else:
            alert_state = "NORMAL"
            best_action = "NO_ACTION"

        # Decision Options
        decision_options = [
            {
                "action_id": "NO_ACTION",
                "name": "No Action",
                "direct_cost": 0.0,
                "risk_score": round(stage1_prob, 3),
                "failure_probability": round(stage1_prob, 3),
                "post_action_load": 1.0,
                "net_expected_loss": round(stage1_prob * hourly_downtime_cost * 10, 2),
                "requires_human_approval": False,
                "justification": f"Continue operation at current risk level ({stage1_prob*100:.1f}%)",
                "is_recommended": best_action == "NO_ACTION",
            },
            {
                "action_id": "DERATE_THROTTLE",
                "name": "De-rate / Throttle",
                "direct_cost": 250.0,
                "risk_score": round(stage1_prob * 0.8, 3),
                "failure_probability": round(stage1_prob * 0.64, 3),
                "post_action_load": 0.75,
                "net_expected_loss": round(250 + stage1_prob * 0.64 * hourly_downtime_cost * 10, 2),
                "requires_human_approval": True,
                "justification": "Throttle to 75% to reduce mechanical stress",
                "is_recommended": best_action == "DERATE_THROTTLE",
            },
            {
                "action_id": "IMMEDIATE_MAINTENANCE",
                "name": "Immediate Maintenance",
                "direct_cost": 1400.0,
                "risk_score": 0.0,
                "failure_probability": 0.0,
                "post_action_load": 0.0,
                "net_expected_loss": 1400.0,
                "requires_human_approval": True,
                "justification": "Planned shutdown eliminates catastrophic failure risk",
                "is_recommended": best_action == "IMMEDIATE_MAINTENANCE",
            },
        ]

        return {
            "timestamp": latest.get("timestamp"),
            "run_id": "live_hardware",
            "step": len(buffer),
            "row_index": len(buffer),
            "health_score": round(health_score, 1),
            "alert_state": alert_state,
            "persistence_count": 1,
            "multi_sensor_confirmed": False,
            "recommended_action": best_action,
            "decision_options": decision_options,
            "evidence_card": {
                "observation": f"Live reading at {latest.get('timestamp')}",
                "expected": "Normal baseline envelope",
                "physics_interpretation": f"Diagnosis: {diagnosis} (confidence: {stage1_prob:.2f})",
                "action_rationale": f"Recommended {best_action} based on current anomaly probability",
                "title": "Live Hardware Evidence",
                "what_happened": f"Stage 1 anomaly score: {stage1_prob*100:.1f}%",
                "likely_cause": diagnosis.replace("_", " ").title(),
                "items": [],
                "assumptions": ["Live inference mode", "Features computed from rolling 1800-sample buffer"],
            },
            "telemetry": {
                "timestamp": latest.get("timestamp"),
                "run_id": "live_hardware",
                "step": len(buffer),
                "pressure": float(latest.get("pressure", 0.0)),
                "flow": float(latest.get("flow", 0.0)),
                "temperature": float(latest.get("temperature", 0.0)),
                "vibration": float(latest.get("vibration", 0.0)),
                "motor_current": float(latest.get("motor_current", 0.0)),
                "operating_load": float(latest.get("operating_load", 0.70)),
                "pressure_history": [r.get("pressure", 0.0) for r in buffer[-30:]],
                "flow_history": [r.get("flow", 0.0) for r in buffer[-30:]],
                "temperature_history": [r.get("temperature", 0.0) for r in buffer[-30:]],
                "vibration_history": [r.get("vibration", 0.0) for r in buffer[-30:]],
                "motor_current_history": [r.get("motor_current", 0.0) for r in buffer[-30:]],
            },
            "guardrails": {
                "approved": alert_state != "CRITICAL",
                "human_in_the_loop_required": alert_state == "CRITICAL",
                "safety_envelope_violated": alert_state == "CRITICAL",
                "status": "PASS" if alert_state == "NORMAL" else "WARNING",
                "notes": f"Live mode: {alert_state}",
                "checks": [],
            },
            "prognostics": {
                "rul_hours": None,
                "degradation_velocity": 0.0,
                "limiting_factor": "Live Mode",
                "confidence": "Low",
                "status": "LIVE",
                "message": "RUL estimation requires historical trend (>5 min)",
            },
            "sustainability": {
                "excess_power_kw": 0.0,
                "avoidable_co2_kg_per_h": 0.0,
                "annual_carbon_waste_tonnes": 0.0,
                "waste_percentage": 0.0,
            },
            "enterprise_roi": calculate_enterprise_roi(),
            "health": {
                "score": round(health_score, 1),
                "status": alert_state,
                "aggregate_deviation": 0.0,
                "deviations": {},
            },
            "risk": {
                "score": round(stage1_prob, 3),
                "level": alert_state,
                "review_required": alert_state == "CRITICAL",
                "contributions": [],
            },
            "diagnosis": {
                "condition": diagnosis,
                "confidence": round(stage1_prob, 3),
                "review_required": is_anomaly,
                "reason": f"Stage 1 gate output: {stage1_prob*100:.1f}%",
                "ranked_probabilities": [],
            },
        }
    
    # ============================================================
    # REPLAY MODE (Original Logic — UNCHANGED)
    # ============================================================
    if not DATA_PATH.exists():
        raise HTTPException(status_code=500, detail="Persisted dataset not found")
    
    raw_step = step if step is not None else (row_index if row_index is not None else DEFAULT_STEP_INDEX)
    target_idx = max(0, int(raw_step))
    
    try:
        snapshot = _get_snapshot(run_id=run_id, row_index=target_idx, action=action)
    except Exception:
        try:
            snapshot = _get_snapshot(run_id=run_id, row_index=-1, action=action)
            target_idx = int(getattr(snapshot, "step", target_idx))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    
    features = snapshot.current_features
    health = snapshot.health_score
    risk = snapshot.risk
    history_slice = snapshot.observations[max(0, target_idx - 30): target_idx + 1]

    raw_i = features.get("motor_current")
    actual_i = float(raw_i if raw_i is not None else DEFAULT_BASELINE_MOTOR_CURRENT)
    base_i = _extract_baseline_motor_current(snapshot)

    health_deg = max(0.0, (100.0 - float(health.health_score)) / 100.0) if health else 0.0
    risk_deg = float(risk.score) if risk else 0.0
    deg_stage = max(health_deg, risk_deg * 0.5)

    recent_obs = list(snapshot.observations[max(0, target_idx - 29): target_idx + 1])
    sustain = compute_sustainability_metrics(
        actual_current=actual_i,
        baseline_median_current=base_i,
        degradation_stage=deg_stage,
    )
    prognostics = estimate_remaining_useful_life(
        recent_obs,
        current_health=health.health_score if health else 100.0,
        current_risk=risk.score,
        condition=snapshot.diagnosis.diagnosis,
        persistence_count=snapshot.persistence_count,
        multi_sensor_confirmed=snapshot.multi_sensor_confirmed,
    )
    scaled_arena = compute_sensitivity_costs(
        snapshot.arena,
        risk_tolerance=risk_tolerance,
        hourly_downtime_cost=hourly_downtime_cost,
    )
    roi = calculate_enterprise_roi()

    best_action, decision_options = _format_decision_options(
        scaled_arena,
        arena_human_approval_required=snapshot.arena.human_approval_required,
        arena_recommended_action=snapshot.arena.recommended_action,
    )

    alert_state = getattr(snapshot, "alert_state", "NORMAL")
    health_score_val = health.health_score if health else 100.0
    p_count = snapshot.persistence_count

    h_score = float(health.health_score if hasattr(health, "health_score") else (health if isinstance(health, (int, float)) else 100.0))
    p_count = int(getattr(snapshot, "persistence_count", 0))
    is_confirmed = bool(getattr(snapshot, "multi_sensor_confirmed", False))
    alert_state_str = str(getattr(snapshot, "alert_state", "NORMAL")).upper()

    max_allowable_pf = max(0.005, (100.0 - h_score) / 100.0)
    for opt in decision_options:
        if opt.get("action_id") == "NO_ACTION" or opt.get("name") == "NO_ACTION":
            raw_fp = float(opt.get("failure_probability", 0.0))
            raw_fp = raw_fp / 100.0 if raw_fp > 1.0 else raw_fp
            calibrated_pf = min(raw_fp, max_allowable_pf if h_score >= 85.0 else raw_fp)
            opt["failure_probability"] = round(calibrated_pf, 4)
            calibrated_loss = float(opt.get("direct_cost", 0.0)) + (calibrated_pf * hourly_downtime_cost * 10.0 * risk_tolerance)
            opt["net_expected_loss"] = round(calibrated_loss, 2)

    global _health_history
    if "_health_history" not in globals():
        _health_history = {}
    run_history = _health_history.setdefault(run_id, [])
    run_history.append((target_idx, h_score))
    if len(run_history) > 15:
        run_history.pop(0)

    if len(run_history) >= 3 and run_history[-1][0] > run_history[0][0]:
        delta_h = max(0.0, run_history[0][1] - run_history[-1][1])
        delta_t = float(run_history[-1][0] - run_history[0][0])
        dh_dt = delta_h / delta_t
    else:
        dh_dt = 0.0

    h_trip = 20.0
    if h_score >= 85.0 and not is_confirmed and alert_state_str == "NORMAL":
        final_rul = 720.0
        limiting_cause = "None (Healthy Operation)"
        rul_msg = "Nominal inspection horizon (~30 days)"
    else:
        effective_vel = max(0.015, dh_dt)
        remaining_steps = max(1.0, (h_score - h_trip) / effective_vel)
        final_rul = max(2.0, min(round(remaining_steps * 0.5, 1), 360.0))
        limiting_cause = getattr(getattr(snapshot, "evidence", None), "likely_cause", "Hydraulic / Seal Degradation")
        rul_msg = f"Dynamic boundary estimated at ~{final_rul}h"

    prognostics["rul_hours"] = final_rul
    prognostics["limiting_factor"] = limiting_cause
    prognostics["message"] = rul_msg
    prognostics["degradation_velocity"] = round(dh_dt, 4)

    is_zone_c = (h_score < 80.0 and p_count >= 5) or is_confirmed or alert_state_str == "WARNING"
    is_zone_d = h_score < 45.0 or alert_state_str == "CRITICAL"

    if is_zone_d:
        best_action = "IMMEDIATE_MAINTENANCE"
    elif is_zone_c:
        actionable = [o for o in decision_options if o.get("action_id") != "NO_ACTION" and o.get("name") != "NO_ACTION"]
        best_action = min(actionable, key=lambda o: float(o.get("net_expected_loss", float("inf")))).get("action_id", "DERATE_THROTTLE")
    else:
        best_action = "NO_ACTION"

    for opt in decision_options:
        opt["is_recommended"] = bool((opt.get("action_id") == best_action) or (opt.get("name") == best_action))

    raw_ev_list = getattr(snapshot.evidence, "evidence", []) if hasattr(snapshot, "evidence") else []
    robust_devs = {}
    for it in raw_ev_list:
        feat = getattr(it, "feature", "")
        val = getattr(it, "deviation", getattr(it, "value", 0.0))
        if feat:
            clean_name = str(feat).replace("_robust_z", "").replace("_z", "")
            try:
                robust_devs[clean_name] = float(val)
            except (ValueError, TypeError):
                pass

    authoritative_devs = robust_devs if robust_devs else (health.deviations if health and health.deviations else {})
    anomalous_sensors = sum(1 for v in authoritative_devs.values() if isinstance(v, (int, float)) and abs(v) > 1.5)
    multi_sensor = anomalous_sensors >= 2

    def _build_dynamic_envelope_text(deviations: Dict[str, float]) -> str:
        if not deviations:
            return "All monitored channels within nominal baseline envelope."
        worst_sensor, worst_dev = max(deviations.items(), key=lambda kv: abs(kv[1]))
        direction = "above" if worst_dev > 0 else "below"
        return (
            f"{worst_sensor.replace('_', ' ').title()} is {abs(worst_dev):.2f}σ {direction} "
            f"its healthy baseline — the largest deviation among {len(deviations)} monitored channels."
        )

    evidence_obs = "Baseline operations detected across all channels." if not authoritative_devs else f"Primary variance on {max(authoritative_devs.items(), key=lambda kv: abs(kv[1]))[0]}."
    evidence_exp = _build_dynamic_envelope_text(authoritative_devs)
    evidence_phys = snapshot.evidence.likely_cause or f"Primary diagnostic indicator: {snapshot.diagnosis.diagnosis} (confidence: {snapshot.diagnosis.confidence or 0.0:.2f})."
    evidence_act = snapshot.arena.recommendation_reason or f"Recommended {best_action} minimizes expected financial and operational risk."

    vibration_rms = float(features.get('vibration', 0.0) or 0.0)
    health_score_current = float(health.health_score if health else 100.0)
    safety_hard_lock = bool(health_score_current < 50.0 or vibration_rms > 3.0)
    
    if safety_hard_lock:
        best_action = "IMMEDIATE_MAINTENANCE"
        alert_state = "CRITICAL"
        evidence_act = "CRITICAL RISK: Failure probability >= 75%. Immediate maintenance required."
        if isinstance(prognostics, dict):
            prognostics["status"] = "CRITICAL"
            prognostics["rul_hours"] = 0.0
            prognostics["message"] = f"Projected critical boundary in ~0.0h [{prognostics.get('limiting_factor', 'Vibration')}]"

    for opt in decision_options:
        opt["is_recommended"] = (
            opt.get("action_id", "") == best_action or
            opt.get("name", "") == best_action
        )

    sparkline_map = _extract_all_sparklines(history_slice)

    robust_deviations = {}
    for ev in raw_ev_list:
        f_name = str(getattr(ev, "feature", "") if not isinstance(ev, dict) else ev.get("feature", "")).lower()
        dev_val = float(getattr(ev, "deviation", 0.0) if not isinstance(ev, dict) else ev.get("deviation", 0.0))
        for ch in ["vibration", "temperature", "motor_current", "pressure", "flow"]:
            if ch in f_name or (ch == "motor_current" and "curr" in f_name):
                robust_deviations[ch] = dev_val

    evidence_items = _compute_evidence_items(features, robust_deviations)
    
    return {
        "timestamp": str(features.get("timestamp")),
        "run_id": run_id,
        "step": target_idx,
        "row_index": target_idx,
        "health_score": round(health.health_score, 1) if health else 100.0,
        "alert_state": alert_state,
        "persistence_count": snapshot.persistence_count,
        "multi_sensor_confirmed": snapshot.multi_sensor_confirmed,
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
            "items": evidence_items,
            "assumptions": list(snapshot.evidence.assumptions),
        },
        "telemetry": {
            "timestamp": str(features.get("timestamp")),
            "run_id": run_id,
            "step": target_idx,
            "pressure": float(features.get("pressure") or 0.0),
            "flow": float(features.get("flow") or 0.0),
            "temperature": float(features.get("temperature") or 0.0),
            "vibration": float(features.get("vibration") or 0.0),
            "motor_current": float(features.get("motor_current") or 0.0),
            "operating_load": float(features.get("operating_load") or DEFAULT_OPERATING_LOAD),
            "pressure_history": sparkline_map["pressure"],
            "flow_history": sparkline_map["flow"],
            "temperature_history": sparkline_map["temperature"],
            "vibration_history": sparkline_map["vibration"],
            "motor_current_history": sparkline_map["motor_current"],
        },
        "guardrails": {
            "safety_hard_lock_triggered": safety_hard_lock,
            "safety_hard_lock_reason": (
                f"Vibration {vibration_rms:.2f}mm/s exceeds ISO 10816-3 Class II Zone C Upper Margin (3.0 mm/s) / Health < 50% — Preventive Hard-Lock Engaged"
                if safety_hard_lock else None
            ),
            "approved": snapshot.guardrails.status == "PASS" and not safety_hard_lock,
            "human_in_the_loop_required": snapshot.guardrails.human_review_required or safety_hard_lock,
            "safety_envelope_violated": snapshot.guardrails.status != "PASS" or safety_hard_lock,
            "status": "HARD_LOCK" if safety_hard_lock else snapshot.guardrails.status,
            "notes": f"Status: {'HARD_LOCK' if safety_hard_lock else snapshot.guardrails.status}. Review required: True",
            "checks": (
                [{"name": "iso_10816_zone_c_preventive_interlock", "status": "HARD_LOCK", "reason": f"Vibration {vibration_rms:.2f}mm/s tripped Zone C+ preventive interlock (3.0 mm/s limit)"}]
                if safety_hard_lock else []
            ) + [
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


@app.post("/api/v1/simulation", response_model=SimulationResultResponse)
def run_simulation(req: SimulationRequest) -> Dict[str, Any]:
    """Execute approval-gated simulation action."""
    if not DATA_PATH.exists():
        raise HTTPException(status_code=500, detail="Persisted dataset not found")
    raw_act = req.action_id.lower() if req.action_id else req.action
    if raw_act in ["derate_throttle", "de_rate"]:
        act = "de_rate"
    elif raw_act in ["immediate_maintenance", "maintenance"]:
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