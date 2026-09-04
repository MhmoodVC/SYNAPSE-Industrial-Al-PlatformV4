# SYNAPSE Industrial Water Pump Diagnostic Suite

[![Test Suite](https://img.shields.io/badge/pytest-54%2F54%20PASS-brightgreen)](tests/)
[![Architecture](https://img.shields.io/badge/stack-FastAPI%20%2B%20Next.js%2014-blue)](#architecture)
[![Standards](https://img.shields.io/badge/compliance-ISO%2010816--3%20%7C%20UN%20SDGs-indigo)](#compliance--standards)
[![Empirical Validation](https://img.shields.io/badge/Active%20Phase%20Recall-94.5%25-emerald)](#empirical-ground-truth-benchmarks)

**SYNAPSE** is an industrial-grade, physics-grounded AI diagnostic suite and decision-support system for high-criticality industrial water pumps. It enforces a strict zero-leakage causal boundary, operates as an advisory layer with human-in-the-loop authorization gates, and provides an explainable 3-Way Decision Arena for operational risk mitigation.

---

## System Architecture

The presentation layer has transitioned to a modern decoupled production stack:

- **Backend Service (`src/api/main.py`):** High-performance Python FastAPI service exposing REST and WebSocket endpoints for telemetry streams, multi-run discovery across all 110 runs, empirical model metrics, and dynamic Decision Arena evaluations.
- **Frontend Dashboard (`frontend/`):** Next.js 14 (React, TypeScript, Tailwind CSS, Framer Motion) industrial UI featuring smooth 250ms-debounced policy sliders, AbortController request cancellation, multi-run fault scenario discovery, telemetry sparklines, and an Engineering Deep-Dive Drawer.
- **Legacy Fallback (`app.py`):** Standalone Streamlit dashboard retained for lightweight demonstration.

---

## Empirical Ground-Truth Benchmarks

All performance metrics stem from strict **Grouped-Holdout Cross-Validation** (20% held-out test runs, zero causal leakage across run boundaries) on our 110,000-observation dataset across 22 held-out test runs (22,000 observations):

- **Primary Operational Metric: Active Fault Phase ($\text{stage} > 0.05$, N=4,520):**
  * Fault Detection Recall: **`94.5%`** (`0.9451`)
  * Diagnostic Precision: **`95.5%`** (`0.9545`)
  * Active Phase Accuracy: **`94.5%`** (`0.9451`)
  * Harmonic F1-Score: **`94.8%`** (`0.9482`)
- **Secondary Diagnostic Context: Full-Trajectory Audit (N=22,000):**
  * Pre-Fault Normal Specificity: **`99.3%`** (`0.9930`) — *Correctly recognizes healthy state prior to fault onset*
  * Point-wise Overall Accuracy: **`57.3%`** (`0.5725`) — *Reflects healthy lead-in steps (~350s) labeled under run-level fault IDs*
  * Macro-Precision: **`87.2%`** (`0.8717`)
  * Macro-F1 Score: **`63.1%`** (`0.6312`)
- **Anomaly Detection (Isolation Forest, Normal-Trained N=7,427):**
  * Normal Inlier Retention: **`91.0%`** (`0.9095`)
  * False Alarm Rate ($\alpha$): **`9.1%`** (`0.0905`, suppressed by temporal persistence)

---

## Compliance & Standards

- **ISO 10816-3 / ISO 20816-3:** Mechanical vibration severity classification for industrial pumps (Zone A: $<1.8\text{ mm/s}$, Zone B: $1.8\text{--}2.8\text{ mm/s}$, Zone C: $2.8\text{--}4.5\text{ mm/s}$, Zone D: $>4.5\text{ mm/s}$).
- **UN Sustainable Development Goals:**
  * **SDG 9 (Industry & Infrastructure):** Asset life extension and resilient edge AI monitoring.
  * **SDG 12 (Responsible Consumption):** Prevents catastrophic asset destruction and reduces scrap material waste.
  * **SDG 13 (Climate Action):** Real-time monitoring of avoidable parasitic power ($\text{kW}$) and annual $\text{CO}_2$ emissions ($\text{tCO}_2\text{e}$).

---

## Quickstart

### 1. Launch FastAPI Backend Service
```powershell
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```
API documentation available at `http://localhost:8000/docs`.

### 2. Launch Next.js 14 Frontend
```powershell
cd frontend
npm run dev
```
Open `http://localhost:3000` in your browser.

### 3. Run Automated Regression Test Suite
```powershell
pytest -v --tb=short
```
All **54 / 54 tests pass 100% green** in ~27 seconds.

---

## Documentation Directory

- [User Guide & Technical Manual](docs/USER_GUIDE.md)
- [Project Status & Audit Trail](docs/SYNAPSE_PROJECT_STATUS.md)
- [Hardware & IoT Integration Guide](docs/HARDWARE_IOT_INTEGRATION_GUIDE.md)
- [System Verification PDF Report](docs/SYNAPSE_SYSTEM_VERIFICATION_REPORT.pdf)

