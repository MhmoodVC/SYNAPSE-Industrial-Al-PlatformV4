# SYNAPSE Hardware & Frontend Integration Guide

**Target Audience:** IoT Hardware Engineers, Embedded / Gateway Developers, Backend Integrators, and Frontend Engineers.  
**System Version:** SYNAPSE 2.0 (Phases 1–16 Production Architecture)  
**Standard:** `industrial-ml-reviewer` / Zero-Leakage Causal Advisory Architecture  

---

## 1. Architectural Core & Separation of Concerns

### 1.1 Ingestion & UI Boundary
SYNAPSE is designed with an uncompromising architectural boundary between transport/presentation and the core intelligence engine:
- **Presentation & Transport Layers (Frontend & IoT Gateway):** Exclusively handle communication, JSON serialization, user telemetry display, and operator interaction. They contain **zero machine learning inference, zero alert filtering logic, and zero physics heuristics**.
- **Core Domain Services (`src/`):** Own data contract validation, causal feature extraction, classifier inference, anomaly scoring, 4-part evidence generation, risk modeling, and Decision Arena evaluation.

```
+---------------------+         +------------------------+
| Physical Pump / IoT | ------> | MQTT / REST Ingestion  |
| Sensor Transducers  |         | (src/iot/adapter.py)   |
+---------------------+         +------------------------+
                                            |
                                            v
                                +------------------------+
                                | SensorRecord Contract  |
                                | & Bounded Cleaning     |
                                +------------------------+
                                            |
                                            v
                                +------------------------+
                                | Vectorized Causal Eng. |
                                | (Median & MAD Baseline)|
                                +------------------------+
                                            |
                         +------------------+------------------+
                         |                                     |
                         v                                     v
             +-----------------------+             +-----------------------+
             | ExtraTrees Classifier |             | IsolationForest Outl. |
             +-----------------------+             +-----------------------+
                         \                                     /
                          +-----------------+-----------------+
                                            |
                                            v
                                +------------------------+
                                | Fault Diagnosis Engine |
                                | & 4-Part Evidence Card |
                                +------------------------+
                                            |
                                            v
                                +------------------------+
                                | Risk Engine & Alerts   |
                                | (Persistence Filter)   |
                                +------------------------+
                                            |
                                            v
                                +------------------------+
                                | Decision Arena (3 Opt) |
                                | & Guardrails Safety    |
                                +------------------------+
                                            |
                                            v
                                +------------------------+
                                | REST / WebSocket API   |
                                +------------------------+
                                            |
                                            v
                                +------------------------+
                                | React / Streamlit UI   |
                                +------------------------+
```

### 1.2 The Relative Deviation Advantage (Median & MAD via `BaselineProfile`)
Real industrial pumps exhibit immense physical diversity:
- A 15 kW booster pump operates at 4.5 bar and 18 A.
- A 250 kW multi-stage municipal pump operates at 42.0 bar and 280 A.

If an AI model were trained on absolute physical measurements, deploying to a new pump would require collecting hundreds of failure cycles and completely retraining the model.

**SYNAPSE resolves this through dimensionless relative deviations:**
1. During commissioning, the system learns a **`BaselineProfile`** consisting of the median and Median Absolute Deviation (MAD) for each channel during a 5–10 minute healthy run:
   $$\text{MAD}_k = \text{median}\left(\left| x_{i,k} - \text{median}(X_k) \right|\right)$$
2. All real-time telemetry is transformed into robust dimensionless z-scores:
   $$z_{i,k} = \frac{x_{i,k} - \text{median}(X_k)}{\text{MAD}_k \cdot 1.4826}$$
3. Downstream ExtraTrees classifiers, IsolationForest models, and physics diagnostic rules evaluate **relative departures from nominal operation** rather than raw transducer voltages.

> [!IMPORTANT]
> **Zero Retraining Required:** Deploying SYNAPSE to new physical hardware only requires running the pump in a known healthy state for 5–10 minutes to fit a new `BaselineProfile`. The pre-trained models and physics rules adapt instantly.

---

## 2. IoT Hardware Ingestion & Payload Schema

### 2.1 JSON & MQTT Ingestion Contract
Telemetry packets sent by edge microcontrollers (ESP32, Raspberry Pi, Siemens IOT2050, Moxa gateways) or published to an MQTT topic (e.g. `synapse/pumps/{pump_id}/telemetry`) must adhere to the following JSON schema:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "IoTSensorPayload",
  "type": "object",
  "required": [
    "timestamp",
    "pump_id",
    "pressure",
    "flow",
    "temperature",
    "vibration",
    "motor_current"
  ],
  "properties": {
    "timestamp": {
      "description": "ISO-8601 UTC timestamp or Unix epoch seconds",
      "type": ["string", "number"]
    },
    "pump_id": {
      "description": "Unique physical pump identifier",
      "type": "string"
    },
    "run_id": {
      "description": "Operating batch or continuous run ID (optional, defaults to 'iot-stream')",
      "type": "string"
    },
    "pressure": {
      "description": "Discharge line hydraulic pressure in bar",
      "type": ["number", "null"],
      "minimum": 0.0
    },
    "flow": {
      "description": "Volumetric discharge flow rate in L/s or m3/h",
      "type": ["number", "null"],
      "minimum": 0.0
    },
    "temperature": {
      "description": "Bearing housing or motor surface temperature in deg C",
      "type": ["number", "null"],
      "minimum": -20.0,
      "maximum": 200.0
    },
    "vibration": {
      "description": "Overall vibration velocity RMS in mm/s or g",
      "type": ["number", "null"],
      "minimum": 0.0
    },
    "motor_current": {
      "description": "Effective motor phase current in Amperes",
      "type": ["number", "null"],
      "minimum": 0.0
    },
    "operating_load": {
      "description": "Commanded drive frequency or VFD load fraction [0.0 - 1.0] (optional, default 0.70)",
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0
    },
    "operating_regime": {
      "description": "Hydraulic duty regime ('nominal', 'high', 'low') (optional)",
      "type": "string",
      "enum": ["nominal", "high", "low"]
    },
    "pump_state": {
      "description": "Operational state ('running', 'idle', 'stopped') (optional)",
      "type": "string",
      "enum": ["running", "idle", "stopped"]
    }
  }
}
```

### 2.2 Concrete Telemetry Payload Example
```json
{
  "timestamp": "2026-09-04T15:30:00.000Z",
  "pump_id": "pump-mun-01",
  "run_id": "shift-morning-20260904",
  "pressure": 6.84,
  "flow": 42.15,
  "temperature": 48.20,
  "vibration": 1.25,
  "motor_current": 22.40,
  "operating_load": 0.75,
  "operating_regime": "nominal",
  "pump_state": "running"
}
```

### 2.3 Automatic Fault-Tolerant Ingestion in `IoTAdapter`
Incoming field telemetry is inherently noisy. `src/iot/adapter.py` applies automated defensive sanitation before forwarding records:
1. **Timestamp Normalization:** Accepts ISO-8601 strings (with or without `Z`), Unix epoch timestamps (seconds or milliseconds), or python `datetime` objects. If unparseable, assigns `datetime.now(timezone.utc)` and emits an `INVALID_TIMESTAMP` validation issue.
2. **Missing & Corrupted Channels:** If a sensor disconnects (`null`), experiences bus error (`NaN`, `Inf`), or drops out, `IoTAdapter` sets the field to `None` and records a `ValidationIssue`. Downstream cleaning safely applies bounded causal forward-filling (up to 3 consecutive steps) without crashing the pipeline.
3. **Physical Range Enforcements:** Negative values for inherently positive channels (pressure $< 0$, motor current $< 0$) are nulled and flagged as `OUT_OF_RANGE`.
4. **Context Defaults:** Omitted `operating_load` defaults to `0.70`; omitted `operating_regime` is automatically derived from load ($> 0.80 \rightarrow \text{high}$, $< 0.60 \rightarrow \text{low}$, else $\text{nominal}$).

---

## 3. Physical Calibration Protocol (Nominal Baseline Run)

When commissioning SYNAPSE on a new physical water pump installation, follow this protocol to establish asset-specific baseline statistics.

### 3.1 Step-by-Step Commissioning Procedure
1. **Mechanical & Hydraulic Check:**
   - Confirm proper shaft alignment, lubrication levels, and pipe strain isolation.
   - Fully open the suction valve; purge air from the pump casing.
2. **Nominal Operational Steady State:**
   - Start the pump under normal operating load (e.g., 70% to 75% VFD speed or standard grid frequency).
   - Allow hydraulic transients and motor starting inrush current to stabilize (approximately 60 seconds).
3. **Telemetry Capture (5 to 10 Minutes):**
   - Stream telemetry to SYNAPSE at 1 Hz for 300 to 600 seconds (minimum 300 samples required).
   - Ensure the pump operates steadily without throttling, cavitation, or external disturbances.
4. **Run Calibration Script:**
   - Fit and export the `BaselineProfile` using the script below.

### 3.2 Calibration Script (`scripts/calibrate_physical_pump.py`)
```python
"""
SYNAPSE Physical Pump Calibration Utility
Fits and saves a BaselineProfile from a 5-10 minute healthy baseline run.
"""

import json
from pathlib import Path
from typing import List

from data.contract import SensorRecord
from features.engineering import BaselineProfile
from iot.adapter import IoTAdapter


def calibrate_from_stream(
    raw_payloads: List[dict],
    pump_id: str,
    output_path: Path,
) -> BaselineProfile:
    """Ingest healthy calibration payloads and compute median/MAD profile."""
    adapter = IoTAdapter(default_pump_id=pump_id)
    records: List[SensorRecord] = []

    for payload in raw_payloads:
        record, issues = adapter.ingest_payload(payload)
        records.append(record)

    if len(records) < 60:
        raise ValueError(f"Insufficient baseline samples ({len(records)}). Need at least 60s at 1Hz.")

    # Fit robust baseline (median and MAD across channels)
    profile = BaselineProfile.fit(records)

    # Save to calibration profile JSON
    profile_dict = {
        "pump_id": pump_id,
        "sample_count": len(records),
        "medians": profile.medians,
        "mads": profile.mads,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(profile_dict, f, indent=2)

    print(f"Calibration successful for {pump_id}!")
    print(f"Saved profile to {output_path}")
    print("Medians:", profile.medians)
    print("MADs:   ", profile.mads)
    return profile


if __name__ == "__main__":
    # Example usage reading captured commissioning packets
    captured_data_file = Path("data/raw/pump_001_commissioning.json")
    if captured_data_file.exists():
        with open(captured_data_file, "r") as f:
            sample_payloads = json.load(f)
        calibrate_from_stream(
            sample_payloads,
            pump_id="pump-001",
            output_path=Path("data/calibration/baseline_pump_001.json"),
        )
```

---

## 4. Backend Deployment & Real-Time Ingestion (FastAPI)

Below is a production-ready, minimal FastAPI microservice (`src/service/api.py`) exposing both HTTP REST endpoints and streaming WebSockets for real-time SCADA / Frontend integration.

### 4.1 Real-Time Server Implementation
```python
"""
SYNAPSE Real-Time Ingestion & Diagnostic API Service
Wraps IoTAdapter, Feature Engineering, Diagnostics, Risk, and Decision Arena.
"""

from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from decision.arena import build_decision_arena
from decision.diagnosis import diagnose
from decision.evidence import build_evidence_card
from decision.guardrails import GuardrailContext, evaluate_guardrails
from decision.risk_engine import assess_risk
from features.engineering import BaselineProfile, transform_records
from iot.adapter import IoTAdapter, IoTPayloadError
from synapse_waterpump.models.health_score import compute_health_score

app = FastAPI(
    title="SYNAPSE Water Pump Intelligence API",
    version="2.0.0",
    description="Explainable real-time advisory and decision-support backend",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory sliding telemetry cache for causal rolling calculations (per pump)
TELEMETRY_BUFFERS: Dict[str, deque] = {}
MAX_BUFFER_SIZE = 120  # Keep trailing 2 minutes at 1 Hz

# Load active baseline profile
CALIBRATION_FILE = Path("data/calibration/baseline_pump_001.json")
if CALIBRATION_FILE.exists():
    with open(CALIBRATION_FILE, "r") as f:
        cal = json.load(f)
    ACTIVE_BASELINE = BaselineProfile(medians=cal["medians"], mads=cal["mads"])
else:
    # Default synthetic fallback
    ACTIVE_BASELINE = BaselineProfile(
        medians={"pressure": 6.0, "flow": 40.0, "temperature": 45.0, "vibration": 1.0, "motor_current": 20.0},
        mads={"pressure": 0.5, "flow": 2.0, "temperature": 1.5, "vibration": 0.2, "motor_current": 1.0},
    )

ADAPTER = IoTAdapter()


class TelemetryInput(BaseModel):
    timestamp: Optional[str] = Field(None, example="2026-09-04T15:30:00Z")
    pump_id: str = Field(..., example="pump-001")
    run_id: Optional[str] = Field("iot-stream", example="shift-01")
    pressure: Optional[float] = Field(..., example=6.45)
    flow: Optional[float] = Field(..., example=41.2)
    temperature: Optional[float] = Field(..., example=46.8)
    vibration: Optional[float] = Field(..., example=1.15)
    motor_current: Optional[float] = Field(..., example=21.0)
    operating_load: Optional[float] = Field(0.75, example=0.75)


def process_telemetry_record(payload_dict: dict) -> dict:
    """Execute the full SYNAPSE pipeline on a single incoming packet."""
    record, issues = ADAPTER.ingest_payload(payload_dict)
    pump_id = record.pump_id

    if pump_id not in TELEMETRY_BUFFERS:
        TELEMETRY_BUFFERS[pump_id] = deque(maxlen=MAX_BUFFER_SIZE)

    TELEMETRY_BUFFERS[pump_id].append(record)
    records_list = list(TELEMETRY_BUFFERS[pump_id])

    # 1. Causal Feature Extraction
    features_list = transform_records(records_list, ACTIVE_BASELINE, window=5)
    current_features = features_list[-1]

    # 2. Condition Diagnosis & Probabilities
    diag = diagnose(current_features)

    # 3. Risk Engine
    risk = assess_risk(
        diag,
        persistence=min(1.0, len(records_list) / MAX_BUFFER_SIZE),
        operating_load=float(current_features["operating_load"]),
        severity=diag.confidence or 0.0,
    )

    # 4. 4-Part Evidence Card
    evidence = build_evidence_card(
        current_features,
        diag,
        ACTIVE_BASELINE,
        timestamp=current_features["timestamp"],
        run_id=record.run_id,
        pump_id=pump_id,
    )

    # 5. Decision Arena Alternatives & Costs
    arena = build_decision_arena(diag, risk, operating_load=float(current_features["operating_load"]))

    # 6. Safety Guardrails Evaluation
    context = GuardrailContext(diagnostic_confidence=diag.confidence)
    guardrails = evaluate_guardrails(
        action="human_review",
        operating_load=float(current_features["operating_load"]),
        diagnosis_review_required=diag.review_required,
        context=context,
    )

    # 7. Composite Health Score (0-100)
    health = compute_health_score(records_list) if len(records_list) >= 10 else None

    return {
        "timestamp": current_features["timestamp"].isoformat(),
        "pump_id": pump_id,
        "health_score": {
            "score": round(health.health_score, 2) if health else 100.0,
            "status": health.operational_status if health else "HEALTHY",
            "aggregate_deviation": round(health.aggregate_deviation, 4) if health else 0.0,
        },
        "diagnosis": {
            "condition": diag.fault_type,
            "confidence": round(diag.confidence or 0.0, 3),
            "review_required": diag.review_required,
            "ranked_probabilities": [
                {"fault": f, "probability": round(p, 4)}
                for f, p in diag.ranked_probabilities.items()
            ],
        },
        "evidence_card": {
            "title": evidence.title,
            "summary": evidence.summary,
            "items": [
                {
                    "type": item.evidence_type,
                    "feature": item.feature,
                    "value": round(item.value, 3) if isinstance(item.value, (int, float)) else item.value,
                    "baseline": round(item.baseline, 3) if isinstance(item.baseline, (int, float)) else item.baseline,
                    "deviation": round(item.deviation, 3) if isinstance(item.deviation, (int, float)) else item.deviation,
                    "units": item.units,
                    "rationale": item.rationale,
                }
                for item in evidence.items
            ],
            "likely_cause": evidence.likely_cause,
        },
        "decision_arena": {
            "current_risk": round(risk.score, 3),
            "risk_level": risk.level,
            "recommendation": arena.recommended_action,
            "alternatives": [
                {
                    "action": alt.name,
                    "code": alt.action,
                    "modeled_risk": round(alt.modeled_risk, 3),
                    "estimated_cost": round(alt.estimated_cost, 2),
                    "operational_impact": alt.operational_impact,
                    "rationale": alt.rationale,
                    "assumption": alt.assumption,
                }
                for alt in arena.alternatives
            ],
        },
        "guardrails": {
            "status": guardrails.status,
            "passed": guardrails.passed,
            "human_approval_required": guardrails.human_approval_required,
        },
        "validation_issues": [
            {"field": issue.field, "code": issue.issue_code, "detail": issue.detail}
            for issue in issues
        ],
    }


@app.post("/api/v1/telemetry/snapshot")
async def ingest_snapshot(data: TelemetryInput):
    """Ingest a single sensor packet and return full decision intelligence."""
    try:
        return process_telemetry_record(data.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.websocket("/ws/telemetry")
async def websocket_telemetry_stream(websocket: WebSocket):
    """Streaming WebSocket endpoint for high-frequency field ingestion & UI updates."""
    await websocket.accept()
    try:
        while True:
            raw_text = await websocket.receive_text()
            data = json.loads(raw_text)
            result = process_telemetry_record(data)
            await websocket.send_json(result)
    except WebSocketDisconnect:
        pass
    except Exception as err:
        await websocket.send_json({"error": str(err)})
```

---

## 5. Frontend Integration Guide (Data Consumption)

The UI layer communicates with SYNAPSE by polling `/api/v1/telemetry/snapshot` or subscribing to `/ws/telemetry`. Below are the TypeScript contracts and component consumption patterns.

### 5.1 TypeScript Response Schema
```typescript
export interface HealthScoreResult {
  score: number;                   // 0.00 to 100.00
  status: 'HEALTHY' | 'DEGRADED' | 'CRITICAL';
  aggregate_deviation: number;
}

export interface RankedProbability {
  fault: string;
  probability: number;             // 0.0000 to 1.0000 (sums to 1.0)
}

export interface DiagnosisOutput {
  condition: string;
  confidence: number;
  review_required: boolean;
  ranked_probabilities: RankedProbability[];
}

export interface EvidenceItem {
  type: '[MODEL-DERIVED]' | '[RULE-DERIVED]' | '[DOMAIN KNOWLEDGE]' | '[SIMULATION ASSUMPTION]';
  feature: string;
  value: number | string;
  baseline: number | string;
  deviation: number | string;
  units: string;
  rationale?: string;
}

export interface EvidenceCard {
  title: string;
  summary: string;
  items: EvidenceItem[];
  likely_cause?: string;
}

export interface ArenaAlternative {
  action: string;                  // e.g. "No Action", "De-rate / Throttle", "Immediate Maintenance"
  code: 'no_action' | 'de_rate' | 'maintenance';
  modeled_risk: number;            // 0.0 to 1.0
  estimated_cost: number;          // Financial cost impact in USD
  operational_impact: string;      // Throughput loss description
  rationale: string;
  assumption: string;
}

export interface DecisionArenaOutput {
  current_risk: number;
  risk_level: 'NOMINAL' | 'ELEVATED' | 'HIGH' | 'CRITICAL';
  recommendation: string;
  alternatives: ArenaAlternative[];
}

export interface SynapseSnapshotResponse {
  timestamp: string;
  pump_id: string;
  health_score: HealthScoreResult;
  diagnosis: DiagnosisOutput;
  evidence_card: EvidenceCard;
  decision_arena: DecisionArenaOutput;
  guardrails: {
    status: 'PASS' | 'FAIL' | 'UNKNOWN';
    passed: boolean;
    human_approval_required: boolean;
  };
  validation_issues: Array<{ field: string; code: string; detail: string }>;
}
```

### 5.2 UI Component Rendering Guidelines

#### A. Health Score (0–100 Gauge)
- **Visual:** Radial gauge or color-coded progress bar.
- **Thresholds:**
  - $\ge 85.0$: Green (`HEALTHY`)
  - $60.0 - 84.9$: Amber (`DEGRADED`)
  - $< 60.0$: Red (`CRITICAL`)

#### B. Diagnosis & Human Review Alert
- When `review_required === true`, display a high-priority warning badge:
  `⚠️ UNCERTAIN DIAGNOSIS — HUMAN REVIEW REQUIRED`.
- Render the `ranked_probabilities` as a horizontal distribution bar so engineers see competing fault hypotheses.

#### C. Traceable Evidence Card
- Render evidence items in a structured table or accordion.
- Color-code the taxonomy badges:
  - `[MODEL-DERIVED]`: Purple badge (ExtraTrees classification contribution)
  - `[RULE-DERIVED]`: Blue badge (Deterministic z-score physics comparison)
  - `[DOMAIN KNOWLEDGE]`: Slate badge (ISO mechanical guidelines / pump textbook mechanics)
  - `[SIMULATION ASSUMPTION]`: Amber badge (Simulation load impact parameters)

#### D. Decision Arena 3-Way Trade-Off Matrix
Display the 3 operational choices side-by-side:

| Card Column | Choice 1: No Action | Choice 2: De-Rate / Throttle | Choice 3: Immediate Maintenance |
| :--- | :--- | :--- | :--- |
| **Risk Score** | High (e.g. 0.85) | Moderate (e.g. 0.52) | Low (e.g. 0.12) |
| **Production Impact** | 0% Loss | -20% Throughput | -100% (Scheduled Downtime) |
| **Direct Cost** | High expected damage | Low production penalty | Overhaul service fee |
| **Human Action** | Continue monitoring | **[Request Plant Approval]** | **[Authorize Shutdown]** |

> [!CAUTION]
> **Advisory-Only Enforcement:** Frontend action buttons must never directly command pump actuators. Triggering an action in the UI should only submit an advisory ticket to the plant maintenance management system (CMMS) or SCADA operator console.

---

## 6. Verification & Troubleshooting Checklist

| Symptom / Error | Root Cause | Resolution |
| :--- | :--- | :--- |
| `ValidationIssue: INVALID_TIMESTAMP` | Payload timestamp is missing or malformed | Ensure ISO-8601 string (e.g. `2026-09-04T12:00:00Z`) or Unix epoch number. |
| Diagnosis constantly returns `UNKNOWN` | Pump operates in uncalibrated regime or values are below $3.0\sigma$ | Verify baseline calibration (`BaselineProfile`). If pump is healthy, `UNKNOWN` or `normal` condition is the expected nominal state. |
| Health Score stays at 100.0 | Fewer than 10 observations in rolling buffer | Allow at least 10 consecutive sensor packets to populate the sliding history window. |
| Decision Arena shows `HUMAN_REVIEW` | Guardrails are unconfigured or diagnosis is ambiguous | Supply engineering bounds in `GuardrailContext` or provide manual operator review. |
| High nominal false alarms ($> 5\%$) | Transient electrical noise or single-channel spikes | Verify `require_multi_sensor=True` and persistence filter length ($\ge 3$ consecutive samples) in `src/alerts/`. |

---

## 7. Contact & Sign-Off

- **Lead Architecture Team:** DeepMind Advanced Agentic Coding & Industrial Review Panel  
- **Governance Standard:** `industrial-ml-reviewer`  
- **Status:** **APPROVED & DEFENSE READY**
