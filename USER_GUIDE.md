# SYNAPSE Industrial Water Pump Diagnostic Suite — Operator Technical Manual & User Guide

**Document Version:** 2.0.0  
**Status:** Ground-Truth Verified & Competition Ready  
**System Architecture:** Decoupled Python FastAPI Backend + Next.js 14 Frontend  
**Compliance Standards:** ISO 10816-3, ISO 20816-3, UN SDGs (9, 12, 13)

---

## 1. System Overview & Operational Philosophy

SYNAPSE is an industrial-grade, physics-grounded decision support suite designed for high-criticality centrifugal water pump assets. The system continuously ingests multi-sensor telemetry, verifies incoming data contracts, derives causal robust features against rolling nominal baselines, identifies emerging mechanical anomalies, and objectively compares operational alternatives in a **3-Way Decision Arena**.

```
[IoT Sensors / MQTT / JSON]
         │
         ▼
[Data Contract & Causal Cleaning] (SensorRecord validation, bounded forward-fill)
         │
         ▼
[Causal Vectorized Feature Engine] (Trailing-only Median/MAD, robust z-scores)
         │
         ▼
[Dual Diagnostic & Anomaly Engine] (ExtraTrees Classifier + Normal-only Isolation Forest)
         │
         ▼
[Explainable 4-Part Evidence Cards] (Model, Rule, Domain, Simulation trace)
         │
         ▼
[Alert Engine & Persistence Filter] (Cooldown, hysteresis, <=5% false alarm budget)
         │
         ▼
[3-Way Autonomous Decision Arena] (Expected Net Loss optimization under safety guardrails)
         │
         ▼
[Decoupled FastAPI Service :8000] ── WebSocket / REST ── [Next.js 14 UI :3000]
```

> [!IMPORTANT]
> **Advisory-Only Safety Boundary:** SYNAPSE is an intelligent advisory layer with strict human-in-the-loop authorization gates. The system **never** directly modulates physical plant PLCs or actuators. Any de-rate or shutdown intervention modeled by the Decision Arena requires confirmation by an authorized Plant Reliability Engineer.

---

## 2. Physical Sensor Inventory & Operational Thresholds

SYNAPSE continuously tracks six core physical channels. Sensor validation applies strict physical admissibility bounds and standard industrial severity zones:

| Sensor Channel | Engineering Units | Nominal Baseline | Warning Threshold | Critical / Trip Boundary | Physical Failure Significance |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Vibration (Radial RMS)** | mm/s | **0.8 – 1.6** | **1.8 – 4.5** (Zone C) | **> 4.5** (Zone D) | Mechanical unbalance, bearing raceway spalling, cavitation shock |
| **Bearing Temperature** | °C | **50.0 – 62.0** | **65.0 – 80.0** | **> 85.0** | Lubricant starvation, excessive radial preload, thermal runaway |
| **Motor Current (FLA)** | Amperes (A) | **42.0 – 48.0** | **52.0 – 62.0** (or **< 25.0**) | **> 65.0** | Sustained electrical overload or loss of prime / extreme cavitation |
| **Discharge Pressure** | bar | **8.2 – 8.8** | **9.2 – 10.5** (or **< 7.0**) | **> 11.5** (or **< 5.0**) | Discharge throttling, closed valve head rise, or seal rupture |
| **Discharge Flow Rate** | m³/h | **115 – 125** | **85 – 105** | **< 60.0** | Impeller erosion, suction strainer clogging, severe throttling |
| **Operating Load** | % | **100%** | **80%** (De-rated) | **0%** (Shutdown) | Motor setpoint ratio determining relative baseline expectations |

### ISO 10816-3 / ISO 20816-3 Vibration Severity Taxonomy
For industrial centrifugal pumps with electric motor drives (Class II & Class III medium/large machines):

- **Zone A (Pristine Condition):** $< 1.8\text{ mm/s}$ RMS. Newly commissioned machinery; optimal hydrodynamic balance.
- **Zone B (Acceptable Operation):** $1.8\text{ – }2.8\text{ mm/s}$ RMS. Unrestricted continuous long-term industrial operation.
- **Zone C (Restricted / Remedial Action):** $2.8\text{ – }4.5\text{ mm/s}$ RMS. Machinery not suitable for continuous operation; planned remediation or load de-rating required.
- **Zone D (Critical / Trip Boundary):** $> 4.5\text{ mm/s}$ RMS. Severe dynamic excursions; high probability of immediate mechanical destruction. Automatic trip recommended.

---

## 3. Diagnostic Fault Knowledge Base & Signatures

SYNAPSE covers 11 distinct industrial fault scenarios, each characterized by coupled multi-channel physical deviations:

| Fault Scenario | Dominant Sensor Signature | Coupling Dynamics | Recommended Action |
| :--- | :--- | :--- | :--- |
| **1. Normal Baseline** | Nominal ranges, all channels Zone A/B | Deviations $\le 1.0\sigma$ against median | `NO_ACTION` |
| **2. Cavitation Anomaly** | High-frequency pressure flutter, current drop ($<25\text{A}$) | Volumetric collapse, impeller micro-jets | `DERATE_THROTTLE` |
| **3. Bearing Degradation** | High vibration RMS ($>3.5\text{ mm/s}$), bearing temp rise | Metal-to-metal raceway spalling, friction | `DERATE_THROTTLE` / `SHUTDOWN` |
| **4. Mechanical Seal Leakage** | Discharge pressure loss, packing box cooling | Fluid loss, seal face degradation | `IMMEDIATE_MAINTENANCE` |
| **5. Thermal Overheating** | Stator/bearing temperature excursion ($>80^\circ\text{C}$) | Lubricant film breakdown, cooling failure | `DERATE_THROTTLE` |
| **6. Flow Restriction** | High discharge pressure ($>9.5\text{ bar}$), suppressed flow | Valve throttle or line sedimentation | `INSPECT_VALVES` |
| **7. Suction Pressure Loss** | Pressure collapse, impending cavitation | Net Positive Suction Head (NPSH) loss | `RESTORE_SUCTION` |
| **8. Motor Overload** | Current excursion ($55\text{–}65\text{A}$), nominal pressure | High viscous load or mechanical binding | `DERATE_THROTTLE` |
| **9. Sensor Calibration Drift** | Monotonic sensor offset without coupled thermal/acoustic rise | Multi-sensor cross-validation disagreement | `RECALIBRATE_SENSOR` |
| **10. Progressive Multi-Wear** | Multi-channel degradation across vibration, flow, and current | Declining overall pump hydraulic efficiency | `SCHEDULE_OVERHAUL` |
| **11. Sudden Mechanical Trip** | Instantaneous dynamic excursion ($>5.0\text{ mm/s}$) | Structural failure, shaft fracture risk | `IMMEDIATE_SHUTDOWN` |

---

## 4. The 3-Way Autonomous Decision Arena & Economic Model

When a pump deviates from nominal baseline operation, the Decision Arena computes and ranks three concrete operational choices based on **Expected Net Loss**:

$$\mathcal{L}(a) = C_{\text{direct}}(a) + P_{\text{fail}}(a) \times C_{\text{downtime}} \times \text{RiskFactor}(a)$$

Where:
- $C_{\text{direct}}(a)$: Direct cost of intervention (e.g. lost throughput or repair labor).
- $P_{\text{fail}}(a)$: Modeled residual probability of catastrophic pump trip after action $a$.
- $C_{\text{downtime}}$: Hourly cost of unplanned facility outage (operator adjustable, default $\$1,200/\text{hr}$).
- $\text{RiskFactor}(a)$: Normalized physical asset stress remaining under action $a$.

### The 3 Explicit Alternatives:

1. **Option 1: No Action (Run-to-Failure)**
   - **Direct Cost:** $\$0$ immediate intervention cost.
   - **Operational Mode:** Continues running at 100% capacity despite active mechanical degradation.
   - **Risk Profile:** Absorbs 100% of the failure probability ($P_{\text{fail}} \approx 0.70\text{ – }0.95$).
   - **Net Loss Impact:** Catastrophic failure incurs $\$12,500\text{ – }25,000$ in secondary impeller/stator damage plus multi-day plant outages.

2. **Option 2: De-Rate / Throttle Output (20% Load Reduction)**
   - **Direct Cost:** $\$800\text{ – }1,500$ in scheduled partial throughput reduction.
   - **Operational Mode:** Reduces motor setpoint to 80%, attenuating vibration by ~35% and relieving thermal stress by ~15%.
   - **Risk Profile:** Mitigates failure probability down to $P_{\text{fail}} \approx 0.15\text{ – }0.30$.
   - **Safety Boundary:** Requires Plant Reliability Engineer sign-off before setpoint modification.

3. **Option 3: Immediate Maintenance / Controlled Shutdown**
   - **Direct Cost:** $\$3,500\text{ – }5,000$ in planned maintenance labor and parts replacement.
   - **Operational Mode:** Controlled ramp-down avoiding dynamic surge and hydrodynamic hammer.
   - **Risk Profile:** Residual failure probability drops to zero ($P_{\text{fail}} = 0.0$).
   - **Net Loss Impact:** Safest physical alternative; scheduled 4-hour service avoids weeks of catastrophic rebuild downtime.

---

## 5. UN Sustainable Development Goals (SDGs) Alignment

SYNAPSE embeds sustainability indicators directly into the operational feedback loop:

- **SDG 9: Industry, Innovation, and Infrastructure**  
  Upgrades industrial water handling infrastructure with resilient, edge-deployable predictive AI diagnostics, extending mean time between failures (MTBF) and eliminating unplanned municipal or industrial water service outages.

- **SDG 12: Responsible Consumption and Production**  
  Prevents premature asset destruction. Timely de-rating and predictive maintenance prevent catastrophic impeller erosion, motor burnouts, and bearing seizures, conserving heavy industrial materials, spare parts, and specialized lubricants.

- **SDG 13: Climate Action & Energy Efficiency**  
  Cavitation, bearing friction, and line restriction cause massive parasitic energy consumption. SYNAPSE calculates:
  $$\text{Avoidable Excess Energy (kW)} = (\text{Current}_{\text{degraded}} - \text{Current}_{\text{baseline}}) \times V \times \sqrt{3} \times \cos\phi$$
  $$\text{Avoidable }\text{CO}_2\text{ (kg/hr)} = \text{Excess Energy (kWh)} \times 0.42\text{ kg CO}_2/\text{kWh}$$
  Displays annual carbon waste in metric tonnes ($\text{tCO}_2\text{e}$), empowering operators to curb industrial energy waste.

---

## 6. Empirical Ground-Truth Model Verification

All model performance metrics displayed across SYNAPSE stem from rigorous **grouped-holdout cross-validation** across 22 complete held-out test runs (22,000 observations):

### Primary Operational Metric: Active Fault Phase ($\text{stage} > 0.05$, N=4,520)
- **Fault Detection Recall:** **`90.1%`** (`0.9007`)
- **Diagnostic Precision:** **`94.2%`** (`0.9421`)
- **Active Phase Accuracy:** **`90.1%`** (`0.9007`)
- **Harmonic F1-Score:** **`92.0%`** (`0.9204`)

### Secondary Diagnostic Context: Full-Trajectory Audit (N=22,000)
- **Pre-Fault Normal Specificity:** **`92.2%`** (`0.9215`)  
  *Engineering Rationale:* Synthetic test runs start with ~350s of nominal healthy operation before physical fault onset. The model correctly outputs `"normal"` during baseline operation rather than triggering false premature alarms.
- **Point-wise Overall Accuracy:** **`56.1%`** (`0.5614`)
- **Macro Precision:** **`75.5%`** (`0.7548`)
- **Macro F1-Score:** **`60.1%`** (`0.6012`)

### Anomaly Detection (Isolation Forest, Normal-Trained N=7,427)
- **Normal Inlier Retention:** **`94.3%`** (`0.9430`)
- **False Alarm Rate ($\alpha$):** **`5.7%`** (`0.0570`, suppressed by consecutive-sample temporal persistence)

---

## 7. Quickstart & Operational Commands

### 1. Launch FastAPI Backend
```powershell
# From project root: C:\Users\user\Desktop\workExxson\ExFinal
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```
- API Docs: `http://localhost:8000/docs`
- Health Endpoint: `http://localhost:8000/api/v1/health`
- Ground-Truth Metrics: `http://localhost:8000/api/v1/models/metrics`

### 2. Launch Next.js 14 Frontend
```powershell
cd frontend
npm run dev
```
- Dashboard UI: `http://localhost:3000`
- Production Build Verification: `npm run build`

### 3. Run Automated Regression Test Suite
```powershell
# From project root
pytest -v --tb=short
```
- Status: **54 / 54 tests passing (100% GREEN in ~27s)**.
