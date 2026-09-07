# PART 1 — System Topology & Harmonization Map

## 1.1 Architecture & Component Interaction Topology

```text
+----------------------------------------------------------------------------------------------------+
|                                    SYNAPSE SCADA DASHBOARD                                         |
|                                (Next.js 14 / React 18 / TypeScript)                                |
|                                                                                                    |
|  [ ExecutiveRibbon ]   [ TelemetryGrid ]   [ DecisionArena ]   [ ExplainableEvidence ]  [ DeepMath ]|
+----------------------------------------------------------------------------------------------------+
                                      |                     ^
                     REST Polling (1s)|                     | JSON State Payload
                                      v                     |
+----------------------------------------------------------------------------------------------------+
|                                      FASTAPI PRESENTATION API                                      |
|                                       (src/api/main.py: 705 lines)                                 |
|                                                                                                    |
|  Endpoints:                                                                                        |
|    - GET  /api/health            -> System heartbeat & runtime status                              |
|    - GET  /api/telemetry         -> 1000-frame time-series replay window                           |
|    - GET  /api/snapshot          -> Latest frame diagnosis, ISO 10816 zone, XAI evidence, arena    |
|    - GET  /api/metrics           -> Live JSON payload from src/models/evaluation_metrics.json      |
|    - POST /api/simulate          -> Counterfactual action impact analysis ($ / MTBF / Risk)        |
+----------------------------------------------------------------------------------------------------+
                                      |
                 (Intended Integration Boundary / Modular Bridge)
                                      v
+----------------------------------------------------------------------------------------------------+
|                                    PREDICTOR INFERENCE SERVICE                                     |
|                                (src/services/predictor.py: 36 lines)                               |
|                                                                                                    |
|  - Causal Data Preprocessing:  clean_trajectory (ffill -> bfill NaN imputation)                    |
|  - Causal Feature Engine:      rolling_stats(w=[30, 300, 1800]) + cusum_drift(baseline=600)        |
|  - Causal Feature Slicing:     Zero lookahead (center=False, min_periods=1, grouped by run_id)     |
+----------------------------------------------------------------------------------------------------+
                                      |
                                      v
+----------------------------------------------------------------------------------------------------+
|                               TWO-STAGE HIERARCHICAL ML PIPELINE                                   |
|                                  (src/models/pipeline.py: 23 lines)                                |
|                                                                                                    |
|  +----------------------------------------------------------------------------------------------+  |
|  | STAGE 1: Calibrated Binary Anomaly Gate (src/models/stage1_gate.py: 26 lines)                |  |
|  | Model: HistGradientBoostingClassifier + CalibratedClassifierCV(method='isotonic', cv=3)      |  |
|  | Operating Threshold: 0.2965 (Fixed production cut-off)                                      |  |
|  | Evaluation Constraint: Test FAR <= 4.12%, Anomaly Recall = 98.82%                            |  |
|  +----------------------------------------------------------------------------------------------+  |
|               |                                                   |                                |
|               | prob < 0.2965                                      | prob >= 0.2965                 |
|               v                                                   v                                |
|       [ Label: "normal" ]                                 Append stage1_prob_anomalous feature     |
|                                                                   |                                |
|                                                                   v                                |
|  +----------------------------------------------------------------------------------------------+  |
|  | STAGE 2: Multi-Class Fault Classifier (src/models/stage2_classifier.py: 16 lines)           |  |
|  | Model: Soft-Voting Ensemble (ExtraTreesClassifier[100, seed=42] + HistGradientBoosting[seed=42])  |
|  | Training Protocol: Excludes 'normal' and 'transition' buffer frames                          |  |
|  | Training Feature Cascading: Out-of-Fold (OOF) cross_val_predict probabilities                |  |
|  | Classes (10 Fault Modes): cavitation, bearing_degradation, seal_leakage, overheating,       |  |
|  |                          flow_restriction, pressure_loss, motor_overload, sensor_drift,     |  |
|  |                          progressive_degradation, sudden_failure                             |  |
|  +----------------------------------------------------------------------------------------------+  |
+----------------------------------------------------------------------------------------------------+
                                      ^
                                      | Offline Ground Truth Anchoring
+----------------------------------------------------------------------------------------------------+
|                         OFFLINE DATASET GENERATION & PELT CHANGELOG                                |
|               (src/features/changepoint.py & scripts/relabel_data.py) - STRICTLY OFFLINE           |
|  - ruptures.Pelt(model='rbf'): Offline ground truth changepoint estimation                         |
|  - Empirical Transition Buffers per fault mode: [gt_onset - 10, gt_onset + LAG_BUFFER]             |
|    sensor_drift: 131, flow_restriction: 106, cavitation: 104, motor_overload: 59,                  |
|    overheating: 59, pressure_loss: 44, default: 5                                                  |
+----------------------------------------------------------------------------------------------------+
```

## 1.2 Current Confirmed Model Configuration (Scanned from Code)

The codebase was directly inspected via static analysis to confirm exact hyperparameters and splitter implementations:

- **Stage 1 Operating Threshold**: `0.2965`
  - In `src/models/stage1_gate.py`: `['operating_threshold = 0.2965', 'operating_threshold = 0.2965']`
  - In `src/models/pipeline.py`: `['operating_threshold = 0.2965']`
- **Cross-Validation Splitter in Inference Training / Evaluation**:
  - `scripts/train_pipeline.py`: `['cv=GroupKFold(n_splits=3']`
  - `src/evaluation/audit_report.py`: `['cv=GroupKFold(n_splits=3']`
  - **Confirmed Literal Splitter**: `GroupKFold(n_splits=3)` with `groups=train_df['run_id']` across all OOF cascading steps.
- **Stage 1 Estimator**: `HistGradientBoostingClassifier(random_state=42)` wrapped in `CalibratedClassifierCV(method='isotonic', cv=3)`
- **Stage 2 Estimator**: `VotingClassifier(estimators=[('et', ExtraTreesClassifier(n_estimators=100, random_state=42, n_jobs=-1)), ('hgb', HistGradientBoostingClassifier(random_state=42))], voting='soft')`

## 1.3 Data Contracts (Verbatim)

### `src/models/evaluation_metrics.json`
```json
{
  "source_dataset": "data/raw/synthetic_pump_dataset.csv",
  "evaluation_protocol": "Two-Stage Hierarchical (OOF, Per-Fault Transition Buffers)",
  "held_out_test_runs": [
    "run-0020",
    "run-0109",
    "run-0100",
    "run-0079",
    "run-0080",
    "run-0029",
    "run-0040",
    "run-0060",
    "run-0039",
    "run-0110",
    "run-0089",
    "run-0030",
    "run-0019",
    "run-0009",
    "run-0049",
    "run-0010",
    "run-0059",
    "run-0090",
    "run-0099",
    "run-0050",
    "run-0069",
    "run-0070"
  ],
  "total_test_observations": 22000,
  "classes": [
    "bearing_degradation",
    "cavitation",
    "flow_restriction",
    "motor_overload",
    "normal",
    "overheating",
    "pressure_loss",
    "progressive_degradation",
    "seal_leakage",
    "sensor_drift",
    "sudden_failure",
    "transition"
  ],
  "pipeline_runtime_seconds": 0.5,
  "full_trajectory": {
    "accuracy": 0.9196363636363636,
    "accuracy_percent": 91.96,
    "macro_precision": 0.8264701362310358,
    "macro_precision_percent": 82.65,
    "macro_recall": 0.902319976934395,
    "macro_recall_percent": 90.23,
    "macro_f1": 0.8609039734424674,
    "macro_f1_percent": 86.09,
    "weighted_precision": 0.8751981092187948,
    "weighted_precision_percent": 87.52,
    "weighted_recall": 0.9196363636363636,
    "weighted_recall_percent": 91.96,
    "weighted_f1": 0.8949727868875088,
    "weighted_f1_percent": 89.5,
    "normal_specificity": 0.9588443396226415,
    "normal_specificity_percent": 95.88
  },
  "active_fault_phase": {
    "observations_count": 20754,
    "accuracy": 0.9748482220294883,
    "accuracy_percent": 97.48,
    "fault_detection_recall": 0.9843490657466127,
    "fault_detection_recall_percent": 98.43,
    "diagnostic_precision": 0.9677630682171796,
    "diagnostic_precision_percent": 96.78,
    "harmonic_f1": 0.9753664221927928,
    "harmonic_f1_percent": 97.54,
    "macro_f1": 0.9753664221927928,
    "macro_f1_percent": 97.54,
    "weighted_precision": 0.9774120910674678,
    "weighted_precision_percent": 97.74,
    "weighted_recall": 0.9748482220294883,
    "weighted_recall_percent": 97.48,
    "weighted_f1": 0.9754978245716894,
    "weighted_f1_percent": 97.55
  },
  "anomaly_detector": {
    "model": "HierarchicalPipeline(HistGradientBoosting+ExtraTrees)",
    "inlier_rate": 0.9588443396226415,
    "inlier_rate_percent": 95.88,
    "false_positive_rate": 0.04115566037735849,
    "false_positive_rate_percent": 4.12,
    "outlier_recall": 0.9881656804733728,
    "outlier_recall_percent": 98.82
  },
  "confusion_matrix": [
    [
      0.9947049924357034,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.00529500756429652,
      0.0,
      0.0,
      0.0,
      0.0
    ],
    [
      0.0,
      1.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0
    ],
    [
      0.0,
      0.0,
      1.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0
    ],
    [
      0.0,
      0.0,
      0.0,
      1.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0
    ],
    [
      0.002830188679245283,
      0.0,
      0.0,
      0.0,
      0.9588443396226415,
      0.0,
      0.0,
      0.001768867924528302,
      0.006603773584905661,
      0.0,
      0.029952830188679246,
      0.0
    ],
    [
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      1.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0
    ],
    [
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.997588424437299,
      0.0,
      0.002411575562700965,
      0.0,
      0.0,
      0.0
    ],
    [
      0.012859304084720122,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.959909228441755,
      0.025718608169440244,
      0.0,
      0.0015128593040847202,
      0.0
    ],
    [
      0.0007564296520423601,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.02118003025718608,
      0.9515885022692889,
      0.0,
      0.0264750378214826,
      0.0
    ],
    [
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      1.0,
      0.0,
      0.0
    ],
    [
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.00529500756429652,
      0.029500756429652043,
      0.0,
      0.9652042360060514,
      0.0
    ],
    [
      0.09309791332263243,
      0.013643659711075442,
      0.19101123595505617,
      0.030497592295345103,
      0.12841091492776885,
      0.0040128410914927765,
      0.0072231139646869984,
      0.11958266452648475,
      0.13563402889245585,
      0.10192616372391654,
      0.17495987158908508,
      0.0
    ]
  ]
}
```

### `frontend/src/data/evaluation_metrics.json`
```json
{
  "source_dataset": "data/raw/synthetic_pump_dataset.csv",
  "evaluation_protocol": "Two-Stage Hierarchical (OOF, Per-Fault Transition Buffers)",
  "held_out_test_runs": [
    "run-0020",
    "run-0109",
    "run-0100",
    "run-0079",
    "run-0080",
    "run-0029",
    "run-0040",
    "run-0060",
    "run-0039",
    "run-0110",
    "run-0089",
    "run-0030",
    "run-0019",
    "run-0009",
    "run-0049",
    "run-0010",
    "run-0059",
    "run-0090",
    "run-0099",
    "run-0050",
    "run-0069",
    "run-0070"
  ],
  "total_test_observations": 22000,
  "classes": [
    "bearing_degradation",
    "cavitation",
    "flow_restriction",
    "motor_overload",
    "normal",
    "overheating",
    "pressure_loss",
    "progressive_degradation",
    "seal_leakage",
    "sensor_drift",
    "sudden_failure",
    "transition"
  ],
  "pipeline_runtime_seconds": 0.5,
  "full_trajectory": {
    "accuracy": 0.9196363636363636,
    "accuracy_percent": 91.96,
    "macro_precision": 0.8264701362310358,
    "macro_precision_percent": 82.65,
    "macro_recall": 0.902319976934395,
    "macro_recall_percent": 90.23,
    "macro_f1": 0.8609039734424674,
    "macro_f1_percent": 86.09,
    "weighted_precision": 0.8751981092187948,
    "weighted_precision_percent": 87.52,
    "weighted_recall": 0.9196363636363636,
    "weighted_recall_percent": 91.96,
    "weighted_f1": 0.8949727868875088,
    "weighted_f1_percent": 89.5,
    "normal_specificity": 0.9588443396226415,
    "normal_specificity_percent": 95.88
  },
  "active_fault_phase": {
    "observations_count": 20754,
    "accuracy": 0.9748482220294883,
    "accuracy_percent": 97.48,
    "fault_detection_recall": 0.9843490657466127,
    "fault_detection_recall_percent": 98.43,
    "diagnostic_precision": 0.9677630682171796,
    "diagnostic_precision_percent": 96.78,
    "harmonic_f1": 0.9753664221927928,
    "harmonic_f1_percent": 97.54,
    "macro_f1": 0.9753664221927928,
    "macro_f1_percent": 97.54,
    "weighted_precision": 0.9774120910674678,
    "weighted_precision_percent": 97.74,
    "weighted_recall": 0.9748482220294883,
    "weighted_recall_percent": 97.48,
    "weighted_f1": 0.9754978245716894,
    "weighted_f1_percent": 97.55
  },
  "anomaly_detector": {
    "model": "HierarchicalPipeline(HistGradientBoosting+ExtraTrees)",
    "inlier_rate": 0.9588443396226415,
    "inlier_rate_percent": 95.88,
    "false_positive_rate": 0.04115566037735849,
    "false_positive_rate_percent": 4.12,
    "outlier_recall": 0.9881656804733728,
    "outlier_recall_percent": 98.82
  },
  "confusion_matrix": [
    [
      0.9947049924357034,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.00529500756429652,
      0.0,
      0.0,
      0.0,
      0.0
    ],
    [
      0.0,
      1.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0
    ],
    [
      0.0,
      0.0,
      1.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0
    ],
    [
      0.0,
      0.0,
      0.0,
      1.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0
    ],
    [
      0.002830188679245283,
      0.0,
      0.0,
      0.0,
      0.9588443396226415,
      0.0,
      0.0,
      0.001768867924528302,
      0.006603773584905661,
      0.0,
      0.029952830188679246,
      0.0
    ],
    [
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      1.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0
    ],
    [
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.997588424437299,
      0.0,
      0.002411575562700965,
      0.0,
      0.0,
      0.0
    ],
    [
      0.012859304084720122,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.959909228441755,
      0.025718608169440244,
      0.0,
      0.0015128593040847202,
      0.0
    ],
    [
      0.0007564296520423601,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.02118003025718608,
      0.9515885022692889,
      0.0,
      0.0264750378214826,
      0.0
    ],
    [
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      1.0,
      0.0,
      0.0
    ],
    [
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.0,
      0.00529500756429652,
      0.029500756429652043,
      0.0,
      0.9652042360060514,
      0.0
    ],
    [
      0.09309791332263243,
      0.013643659711075442,
      0.19101123595505617,
      0.030497592295345103,
      0.12841091492776885,
      0.0040128410914927765,
      0.0072231139646869984,
      0.11958266452648475,
      0.13563402889245585,
      0.10192616372391654,
      0.17495987158908508,
      0.0
    ]
  ]
}
```

# PART 2 — Backend Serving Contracts (Verbatim, Full)

# === src/api/main.py (704 lines) ===
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
    if not DATA_PATH.exists():
        raise HTTPException(status_code=500, detail="Persisted dataset not found")
    target_idx = step if step is not None else (row_index if row_index is not None else DEFAULT_STEP_INDEX)

    try:
        snapshot = _get_snapshot(run_id=run_id, row_index=target_idx, action=action)
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

    # Domain analytics computations
    # Pass the last 30 raw observations so estimate_remaining_useful_life can compute
    # a real historical slope (n >= 5 path) rather than the single-record fallback.
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

    # ── Deterministic Safety Interlock (Governed by Latched Snapshot State) ──
    # The alert_state from the snapshot has already evaluated health, persistence,
    # and multi-sensor correlation, and enforces true CRITICAL latching.
    if alert_state == "CRITICAL":
        best_action = "IMMEDIATE_MAINTENANCE"
    elif alert_state == "WARNING":
        best_action = "DERATE_THROTTLE"
    else:
        best_action = "NO_ACTION"

    # Synchronize is_recommended badge — exactly ONE card holds True
    for opt in decision_options:
        opt["is_recommended"] = (
            opt.get("action_id", "") == best_action or
            opt.get("name", "") == best_action
        )


    # Multi-sensor confirmation
    devs = health.deviations if health and health.deviations else {}
    anomalous_sensors = sum(1 for v in devs.values() if isinstance(v, (int, float)) and abs(v) > 1.5)
    multi_sensor = anomalous_sensors >= 2

    # Evidence card 4-part representation
    evidence_obs = snapshot.evidence.what_happened or f"Operating point at step {target_idx} with load {features.get('operating_load', DEFAULT_OPERATING_LOAD)*100:.0f}%."
    evidence_exp = "Normal baseline envelope: vibration < 2.5 mm/s, bearing temperature < 75\u00b0C."
    evidence_phys = snapshot.evidence.likely_cause or f"Primary diagnostic indicator: {snapshot.diagnosis.diagnosis} (confidence: {snapshot.diagnosis.confidence or 0.0:.2f})."
    evidence_act = snapshot.arena.recommendation_reason or f"Recommended {best_action} minimizes expected financial and operational risk."

    sparkline_map = _extract_all_sparklines(history_slice)

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



# === src/services/predictor.py (35 lines) ===
import sys
from pathlib import Path
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(r"C:\Users\user\Desktop\workExxson\ExFinal")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from features.preprocessing import clean_trajectory
from features.temporal import rolling_stats, cusum_drift

class PredictorService:
    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.sensor_cols = ['pressure', 'flow', 'temperature', 'vibration', 'motor_current']
        
    def predict(self, sensor_window_df: pd.DataFrame):
        """
        Unified inference packaging feature extraction + Stage 1 + Stage 2 into a single call.
        NOTE: detect_onset (PELT) is strictly an offline labeling tool and is NEVER executed 
        in the real-time inference path.
        """
        df_clean = clean_trajectory(sensor_window_df, self.sensor_cols)
        df_feat = rolling_stats(df_clean, self.sensor_cols, windows=[30, 300, 1800])
        df_feat = cusum_drift(df_feat, self.sensor_cols, baseline_window=600)
        
        ignore_cols = ['timestamp', 'run_id', 'pump_id', 'operating_regime', 'pump_state', 
                       'fault_type', 'event_start', 'event_end', 'failure_flag', 
                       'relabeled_fault', 'pelt_onset_idx', 'degradation_stage', 'severity']
        
        feature_cols = [c for c in df_feat.columns if c not in ignore_cols]
        X_infer = df_feat[feature_cols].fillna(0)
        
        preds, probs = self.pipeline.predict(X_infer)
        return preds, probs


# === src/models/pipeline.py (23 lines) ===
import numpy as np
from models.stage1_gate import Stage1Gate
from models.stage2_classifier import Stage2Classifier

class HierarchicalPipeline:
    def __init__(self, stage1: Stage1Gate, stage2: Stage2Classifier):
        self.stage1 = stage1
        self.stage2 = stage2
        self.operating_threshold = 0.2965  # Production threshold
        
    def predict(self, X_features):
        prob_anomalous = self.stage1.predict_proba(X_features)[:, 1]
        is_normal = prob_anomalous < self.operating_threshold
        
        predictions = np.empty(len(X_features), dtype=object)
        predictions[is_normal] = "normal"
        
        if np.any(~is_normal):
            X_anomalous = X_features[~is_normal].copy()
            X_anomalous['stage1_prob_anomalous'] = prob_anomalous[~is_normal]
            predictions[~is_normal] = self.stage2.predict(X_anomalous)
            
        return predictions, prob_anomalous


# === src/models/stage1_gate.py (26 lines) ===
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import roc_curve

class Stage1Gate:
    def __init__(self, target_far=0.042):
        self.base_model = HistGradientBoostingClassifier(random_state=42)
        self.calibrated_model = CalibratedClassifierCV(self.base_model, method="isotonic", cv=3)
        # Final approved production threshold
        self.operating_threshold = 0.2965
        self.target_far = target_far
        
    def fit(self, X_train, y_train_binary):
        self.calibrated_model.fit(X_train, y_train_binary)
        # We bypass dynamic calibration for production and use the locked threshold
        self.operating_threshold = 0.2965
        return self
        
    def predict_proba(self, X):
        return self.calibrated_model.predict_proba(X)
        
    def predict(self, X):
        probs = self.predict_proba(X)[:, 1]
        return (probs >= self.operating_threshold).astype(int)


# === src/models/stage2_classifier.py (16 lines) ===
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, VotingClassifier

class Stage2Classifier:
    def __init__(self):
        clf1 = ExtraTreesClassifier(n_estimators=100, random_state=42, n_jobs=-1)
        clf2 = HistGradientBoostingClassifier(random_state=42)
        self.ensemble = VotingClassifier(estimators=[('et', clf1), ('hgb', clf2)], voting='soft')
        
    def fit(self, X_train, y_train):
        self.ensemble.fit(X_train, y_train)
        return self
        
    def predict(self, X):
        return self.ensemble.predict(X)




# PART 4 — Legacy & Dead Code Audit

## 4.1 Hardcoded Old Model Parameters Grep Audit
Scanning `src/` and `frontend/` for legacy model parameters (`n_estimators=300`, `max_depth=26`, `IsolationForest(contamination=0.045)`):

1. **`src/models/baseline.py` (Line 168 & 210)**:
   ```python
   # Line 168 (Legacy Isolation Forest):
   ("model", IsolationForest(random_state=7, contamination=0.045, n_estimators=100))

   # Line 210 (Legacy Single-Stage ExtraTrees):
   Pipeline([("preprocess", preprocess), ("model", ExtraTreesClassifier(n_estimators=300, max_depth=26, min_samples_split=3, random_state=7, class_weight="balanced", n_jobs=-1))])
   ```
   - **Audit Finding**: `src/models/baseline.py` is the obsolete single-stage baseline model. It is completely unreferenced by `src/services/predictor.py` and `src/models/pipeline.py`.

2. **`frontend/src/components/DeepMathDrawer.tsx` (Line 197)**:
   ```tsx
   <p className="font-mono text-xs text-slate-300">
     Classifier: ExtraTrees (300 estimators, max_depth=26, balanced)
   </p>
   ```
   - **Audit Finding**: Hardcoded string literal in the Deep-Dive Drawer UI displaying obsolete model architecture instead of reading dynamic metadata from `evaluation_metrics.json`.

## 4.2 Dead & Unconnected Code Path Cross-Reference
Cross-referencing active imports against the current two-stage inference path (`src/services/predictor.py` + `src/models/pipeline.py`):

| File Path | Called by 2-Stage Inference? | Actual Role & Current Consumer |
|:---|:---:|:---|
| `src/services/predictor.py` | **PRIMARY INFERENCE** | Modular boundary packaging preprocessing, temporal extraction, and 2-stage inference. Not yet called by `src/api/main.py`. |
| `src/models/pipeline.py` | **YES** | Encapsulates Stage 1 gate + Stage 2 classification logic. |
| `src/models/stage1_gate.py` | **YES** | Binary calibrated anomaly gate (T=0.2965). |
| `src/models/stage2_classifier.py` | **YES** | Soft-voting multi-class classifier. |
| `src/features/preprocessing.py` | **YES** | `clean_trajectory` (causal ffill->bfill NaN imputation). |
| `src/features/temporal.py` | **YES** | Causal `rolling_stats` and `cusum_drift`. |
| `src/features/changepoint.py` | **NO (OFFLINE ONLY)** | PELT change-point detection; used strictly by offline relabeling scripts (`scripts/relabel_data.py`). |
| `src/features/engineering.py` | **NO (LEGACY)** | Used exclusively by `src/inference/replay.py` and legacy pipeline. |
| `src/models/baseline.py` | **NO (DEAD)** | Obsolete single-stage model. |
| `src/models/health_score.py` | **NO (LEGACY)** | Used by `src/inference/replay.py` for health metric calculations. |
| `src/decision/*` | **NO (API REPLAY)** | `arena.py`, `diagnosis.py`, `guardrails.py`, `risk_engine.py`, `simulation.py` are consumed exclusively by `src/api/main.py` via `inference.replay.load_replay_snapshot`. |
| `src/explainability/evidence.py`| **NO (API REPLAY)** | Consumed by `src/inference/replay.py` for generating synthetic evidence cards. |
| `src/inference/replay.py` | **NO (API REPLAY)** | Replay loader used by `src/api/main.py`. |
| `src/analytics/*` | **NO (API REPLAY)** | Analytics formulas for ROI, sensitivity, RUL consumed by `src/api/main.py`. |
| `scripts/train_pipeline.py` | **OFFLINE** | Offline model training script with GroupKFold OOF cascading. |
| `scripts/relabel_data.py` | **OFFLINE** | Offline ground-truth relabeling via PELT. |
| `scripts/extract_features.py` | **OFFLINE** | Offline feature extraction across parquet datasets. |
| `src/evaluation/audit_report.py`| **OFFLINE** | Authoritative evaluation and JSON exporter. |
| `scripts/evaluate_and_save_metrics.py` | **NO (OBSOLETE)** | Superseded by `src/evaluation/audit_report.py`. |
| `scripts/export_synthetic_data.py` | **OFFLINE** | Synthetic dataset generator. |
| `scripts/generate_pdf_report.py` | **OFFLINE UTILITY** | Generates system compliance PDF reports. |
| `scripts/run_demo.py` | **OFFLINE DEMO** | Terminal CLI demo. |

## 4.3 Mock & Hardcoded Data Consumers in API & Frontend

1. **`src/api/main.py` Endpoints (`/api/snapshot`, `/api/telemetry`)**:
   - Both endpoints rely on `load_replay_snapshot(DATA_PATH, run_id=run_id, row_index=row_index, action=action)`.
   - Instead of streaming live sensor readings through `PredictorService(pipeline).predict()`, the backend replays historical rows from `data/raw/synthetic_pump_dataset.csv`.
2. **`frontend/src/components/ExplainableEvidence.tsx` (Lines 44-50)**:
   - Contains hardcoded fallback strings for normal ISO baseline envelopes:
     `"Normal baseline envelope: vibration < 2.5 mm/s, bearing temperature < 75°C."`
3. **`frontend/src/components/DeepMathDrawer.tsx` (Line 197)**:
   - Contains static text asserting `"Classifier: ExtraTrees (300 estimators, max_depth=26, balanced)"` rather than reading dynamic classifier attributes from `evaluation_metrics.json`.

## 4.4 File Size & Refactor Candidates (>500 lines)

| File Path | Line Count | Status & Refactoring Recommendation |
|:---|:---:|:---|
| `src/api/main.py` | 705 lines | **Refactor Candidate**: Close to ~800 line ceiling. Contains HTTP routing, Pydantic DTOs, analytics calculations, domain constants, and snapshot mappings. Recommended decomposition into FastAPI APIRouters: `routers/telemetry.py`, `routers/metrics.py`, `routers/simulation.py`. |
| `frontend/src/app/page.tsx` | 562 lines | **Refactor Candidate**: Contains page-level layout, 1000ms interval polling lifecycle, drawer toggling state, error boundaries, and tab filtering. Recommended extraction into custom hooks: `useTelemetryStream()`, `useSnapshotPolling()`. |

# PART 5 — Operational Flaws for Review

The following 5 operational flaws are authored engineering issues submitted for architectural peer review:

1. **Cost-over-safety interlock**: model recommended $1,151 "De-rate" at Health=31.7%, Vibration=3.31 mm/s instead of "Immediate Maintenance" — economic cost function isn't hard-clamped by API 670/ISO 10816 zone boundaries.
2. **State-machine chattering at onset (t=243–248s)**: oscillates No Action <-> De-rate, no hysteresis/debounce.
3. **RUL prognostic divergence**: jumps between 10,000+ hrs, 0 hrs, 350 hrs from raw noisy dz/dt — needs EMA smoothing + bounds.
4. **Ergonomic layout**: Decision Arena buried below telemetry charts, requires scrolling — should sit directly under Executive Health banner.
5. **Static XAI evidence cards** — replace boilerplate with dynamic delta-based root-cause attribution.
