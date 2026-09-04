"""Streamlit presentation layer for SYNAPSE replay and analytics."""

from pathlib import Path
import sys

# Ensure src/ is in sys.path for direct execution or streamlit run
SRC_DIR = Path(__file__).parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import streamlit as st

from analytics import (
    calculate_enterprise_roi,
    compute_sensitivity_costs,
    compute_sustainability_metrics,
    estimate_remaining_useful_life,
)
from data.persistence import load_synthetic_csv
from decision.simulation import SimulationApprovalError, simulate_action
from inference.replay import load_replay_snapshot


DATA_PATH = Path(__file__).parent / "data" / "raw" / "synthetic_pump_dataset.csv"


def main() -> None:
    """Render persisted replay data and delegate decisions to domain services."""
    st.set_page_config(page_title="SYNAPSE | Pump Intelligence", page_icon="S", layout="wide")
    st.markdown("""
    <style>
    .block-container { max-width: 1360px; padding-top: 1.5rem; }
    [data-testid="stMetricValue"] { color: #0f766e; font-size: 1.35rem !important; }
    [data-testid="stMetricLabel"] { font-size: 0.82rem !important; white-space: normal !important; word-break: break-word !important; }
    .status { border-left: 4px solid #0f766e; padding: .7rem 1rem; background: #f0fdfa; border-radius: 4px; margin-bottom: 1rem; }
    .analytics-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 1rem; margin-top: 0.5rem; }
    .badge-stable { color: #15803d; font-weight: bold; }
    .badge-degrading { color: #b45309; font-weight: bold; }
    .badge-critical { color: #b91c1c; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)
    st.title("SYNAPSE")
    st.caption("Explainable pump intelligence | replay mode | simulation only")
    if not DATA_PATH.exists():
        st.error(f"Persisted dataset not found: {DATA_PATH}")
        return

    observations, truth = load_synthetic_csv(DATA_PATH)
    runs = sorted({item.run_id for item in truth})
    with st.sidebar:
        st.header("Replay Controls")
        run_id = st.selectbox("Run", runs)
        run_length = sum(item.run_id == run_id for item in truth)
        row_index = st.slider("Timeline position", 0, max(0, run_length - 1), min(run_length - 1, 80))
        action = st.selectbox("Simulation action", ["de_rate", "maintenance", "no_action"])

        with st.expander("Advanced Policy Tuning", expanded=False):
            risk_tolerance = st.slider(
                "Risk Tolerance Factor",
                min_value=0.5,
                max_value=2.0,
                value=1.0,
                step=0.1,
                help="Scales risk perception: <1.0 = risk-averse, >1.0 = risk-tolerant",
            )
            hourly_downtime_cost = st.slider(
                "Unplanned Downtime Cost ($/hr)",
                min_value=100,
                max_value=2000,
                value=500,
                step=50,
                help="Hourly financial cost incurred during an unscheduled failure outage",
            )

    snapshot = load_replay_snapshot(DATA_PATH, run_id=run_id, row_index=row_index, action=action)
    risk = snapshot.risk
    features = snapshot.current_features
    health = snapshot.health_score

    # Top-level operational metrics
    metrics = st.columns(5)
    metrics[0].metric("Condition", snapshot.diagnosis.diagnosis.replace("_", " ").upper())
    health_display = f"{health.health_score:.1f} / 100 ({health.status})" if health else "N/A"
    metrics[1].metric("Health Score", health_display)
    metrics[2].metric("Risk Score", f"{risk.score:.3f}")
    metrics[3].metric("Risk Level", risk.level.upper())
    metrics[4].metric("Review Status", "REQUIRED" if snapshot.guardrails.human_review_required else "CLEAR")

    st.markdown(f"<div class='status'><strong>{snapshot.evidence.title}</strong><br>{snapshot.evidence.what_happened}</div>", unsafe_allow_html=True)

    # Telemetry Snapshot
    st.subheader("Sensor Telemetry (Current Observation)")
    t_cols = st.columns(6)
    t_cols[0].metric("Pressure", f"{float(features.get('pressure', 0.0)):.2f} bar")
    t_cols[1].metric("Flow Rate", f"{float(features.get('flow', 0.0)):.1f} m³/h")
    t_cols[2].metric("Temperature", f"{float(features.get('temperature', 0.0)):.1f} °C")
    t_cols[3].metric("Vibration", f"{float(features.get('vibration', 0.0)):.2f} mm/s")
    t_cols[4].metric("Current", f"{float(features.get('motor_current', 0.0)):.2f} A")
    t_cols[5].metric("Motor Load", f"{float(features.get('operating_load', 0.0))*100:.0f}%")

    left, right = st.columns([1.2, 1])
    with left:
        st.subheader("Traceable Evidence Card")
        st.write(f"**Likely cause [DOMAIN KNOWLEDGE]:** {snapshot.evidence.likely_cause or 'UNKNOWN'}")
        
        # Ranked Fault Probabilities
        if snapshot.diagnosis.ranked_probabilities:
            top_probs = [f"**{f}**: {p*100:.1f}%" for f, p in snapshot.diagnosis.ranked_probabilities[:4] if p > 0]
            if top_probs:
                st.caption("Ranked Probability Distribution: " + " | ".join(top_probs))

        for item in snapshot.evidence.evidence:
            base_str = f"{item.baseline:.3f}" if isinstance(item.baseline, float) else (item.baseline or "UNKNOWN")
            dev_str = f"{item.deviation:+.3f}" if isinstance(item.deviation, float) else (item.deviation or "UNKNOWN")
            st.write(
                f"• **{item.feature}**: `{item.value:.3f} {item.units}` "
                f"(baseline: `{base_str}`, dev: `{dev_str}`) — *[{item.evidence_type}]*"
            )
        for asm in snapshot.evidence.assumptions:
            st.caption(f"• Assumption [SIMULATION ASSUMPTION]: {asm}")
        st.caption(f"Trace: {snapshot.evidence.run_id} / {snapshot.evidence.pump_id} / {snapshot.evidence.timestamp}")

    with right:
        st.subheader("Risk Drivers")
        for contribution in risk.contributions:
            st.write(f"**{contribution.name}**: {contribution.weighted_value:.3f} (weight: {contribution.weight})")
            st.caption(contribution.reason)
        st.subheader("Guardrails Evaluation")
        for check in snapshot.guardrails.checks:
            st.write(f"`{check.status}` **{check.name}**: {check.reason}")

    # Decision Arena with Dynamic Sensitivity
    scaled_options = compute_sensitivity_costs(
        snapshot.arena,
        risk_tolerance=risk_tolerance,
        hourly_downtime_cost=hourly_downtime_cost,
    )
    st.subheader("Decision Arena: 3-Way Actionable Alternatives (Sensitivity Scaled)")
    st.dataframe([
        {
            "Action Path": getattr(option, "label", option.action),
            "Modeled Risk": f"{option.risk_score:.3f}",
            "Est. Cost / Loss ($)": f"${getattr(option, 'estimated_cost', 0.0):,.2f}",
            "Guardrail Status": option.guardrail_status,
            "Operational Impact": option.operational_impact,
            "Rationale": option.rationale,
        }
        for option in scaled_options
    ], use_container_width=True, hide_index=True)
    st.info(f"Recommendation: **{snapshot.arena.recommended_action.upper()}** | {snapshot.arena.recommendation_reason}")

    # Advanced Analytical Layer: Sustainability & Prognostics (RUL)
    col_sustain, col_prognostics = st.columns(2)
    with col_sustain:
        st.subheader("Sustainability & Carbon Impact")
        actual_i = float(features.get("motor_current", 20.0))
        base_i = 20.0
        for item in snapshot.evidence.evidence:
            if item.feature == "motor_current" and isinstance(item.baseline, (int, float)) and item.baseline > 0:
                base_i = float(item.baseline)
                break
        sustain = compute_sustainability_metrics(actual_current=actual_i, baseline_median_current=base_i)
        
        s_cols = st.columns(3)
        s_cols[0].metric("Excess Power", f"{sustain['excess_power_kw']:.2f} kW")
        s_cols[1].metric("Avoidable CO₂", f"{sustain['co2_kg_hr']:.2f} kg/h")
        s_cols[2].metric("Annual Carbon", f"{sustain['annual_co2_tonnes']:.1f} t/yr")
        if sustain["excess_power_kw"] > 0:
            st.caption(f"⚠️ Excess dissipation accounts for **{sustain['avoidable_waste_percent']:.1f}%** of pump power draw.")
        else:
            st.caption("🌱 Machine operating within nominal green energy baseline (zero excess dissipation).")

    with col_prognostics:
        st.subheader("Asset Prognostics (RUL)")
        rul_info = estimate_remaining_useful_life(
            recent_records=[features],
            current_health=health.health_score if health else 100.0,
            current_risk=risk.score,
        )
        r_cols = st.columns(3)
        status_color = "badge-stable" if rul_info["status"] == "STABLE" else "badge-critical" if rul_info["status"] == "CRITICAL" else "badge-degrading"
        r_cols[0].metric("Lifecycle Status", rul_info["status"])
        rul_text = f"{rul_info['rul_hours']:.1f} hrs" if rul_info["rul_hours"] is not None else "Nominal"
        r_cols[1].metric("Safe Window (RUL)", rul_text)
        r_cols[2].metric("Confidence", rul_info["confidence"])
        st.caption(f"• **Dynamics:** {rul_info['message']} (velocity: `{rul_info['degradation_velocity']:.4f} σ/h`)")

    # Enterprise ROI Expander
    with st.expander("Enterprise ROI & Predictive Savings Engine", expanded=False):
        roi = calculate_enterprise_roi()
        roi_cols = st.columns(4)
        roi_cols[0].metric("Reactive Annual Cost", f"${roi['reactive_total_cost']:,.0f}")
        roi_cols[1].metric("SYNAPSE Cost", f"${roi['synapse_mitigated_cost']:,.0f}")
        roi_cols[2].metric("Net Annual Savings", f"${roi['net_annual_savings']:,.0f}")
        roi_cols[3].metric("ROI Multiple", f"{roi['roi_multiple']:.1f}x")
        st.caption("Modeled on benchmark 4 annual unplanned outages @ $45,000 avg reactive repair cost vs early mitigated overhaul.")

    if st.button("Approve & Simulate Action", type="primary", disabled=snapshot.guardrails.status != "PASS"):
        try:
            result = simulate_action(action, list(snapshot.observations), risk, snapshot.guardrails, human_approved=True)
            st.success(f"{result.label}: modeled risk {result.before_risk:.3f} -> {result.after_risk:.3f}")
            st.caption("Simulation only: no hardware command was issued.")
        except SimulationApprovalError as error:
            st.error(str(error))


if __name__ == "__main__":
    main()
