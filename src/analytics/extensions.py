"""
SYNAPSE Advanced Analytical Extensions
High-impact analytical modules for dynamic sensitivity, carbon tracking,
RUL prognostics, and enterprise ROI calculations.
"""

from dataclasses import replace
import math
from typing import Any, Iterable, Optional, Sequence, Union

from decision.arena import DecisionArena, DecisionOption

# Type alias for downstream integration compatibility
ArenaActionAlternative = DecisionOption


def compute_sensitivity_costs(
    base_arena_output: Union[DecisionArena, Iterable[DecisionOption]],
    risk_tolerance: float = 1.0,
    hourly_downtime_cost: float = 500.0,
) -> list[DecisionOption]:
    """Compute dynamically scaled costs and effective risk across Decision Arena alternatives.

    Parameters
    ----------
    base_arena_output : DecisionArena or iterable of DecisionOption
        The unscaled Decision Arena or collection of options.
    risk_tolerance : float, default 1.0
        Operator risk tolerance factor (0.5 = risk-averse to 2.0 = risk-tolerant).
        Effective risk is scaled inversely: clamp(base_risk / risk_tolerance, 0.0, 1.0).
    hourly_downtime_cost : float, default 500.0
        Monetary cost of plant downtime in $/hour ($100 to $2000).

    Returns
    -------
    list[DecisionOption]
        Refreshed decision options with updated risk scores and grounded sensitivity costs.
    """
    if isinstance(base_arena_output, DecisionArena):
        options = list(base_arena_output.options)
    else:
        options = list(base_arena_output)

    tolerance = max(0.1, float(risk_tolerance))
    downtime_rate = max(0.0, float(hourly_downtime_cost))

    # Base cost benchmark for No-Action
    # Unscheduled failure expected downtime = 8.0 hours; base catastrophic repair = $1500.0
    unscheduled_downtime_hours = 8.0
    base_repair_cost = 1500.0

    scaled_options: list[DecisionOption] = []
    no_action_cost = 0.0

    # First pass: compute No-Action cost as reference
    for opt in options:
        if opt.action == "no_action":
            eff_risk = min(1.0, max(0.0, opt.risk_score / tolerance))
            no_action_cost = round(eff_risk * (downtime_rate * unscheduled_downtime_hours + base_repair_cost), 2)
            break

    for opt in options:
        eff_risk = min(1.0, max(0.0, opt.risk_score / tolerance))

        if opt.action == "no_action":
            cost = no_action_cost
            impact = "Full operational throughput (100%); unmitigated catastrophic failure risk"
            rationale = (
                f"Dynamic risk loss at ${downtime_rate:.0f}/hr downtime "
                f"(tolerance: {tolerance:.1f}x, effective risk: {eff_risk:.3f})"
            )
            assumptions = opt.assumptions + (
                f"SENSITIVITY: 8.0h unscheduled outage at ${downtime_rate:.0f}/hr + ${base_repair_cost:.0f} repair",
            )
        elif opt.action == "de_rate":
            # Partial throughput loss: 25% of hourly downtime/production rate over an 8-hour shift buffer
            derate_duration_hours = 8.0
            throughput_loss = 0.25 * downtime_rate * derate_duration_hours
            # Residual risk penalty scales with operator economics (0.70 × downtime_rate anchors to $350 at $500/hr default)
            residual_risk_coefficient = 0.70 * downtime_rate
            mitigated_risk_penalty = (eff_risk * 0.60) * residual_risk_coefficient
            cost = round(throughput_loss + mitigated_risk_penalty, 2)
            impact = "Load throttled by 25% to relieve component stress; 25% throughput curtailment"
            savings = max(0.0, no_action_cost - cost)
            rationale = f"Throttled production saves ${savings:.2f} vs No Action at ${downtime_rate:.0f}/hr"
            assumptions = opt.assumptions + (
                f"SENSITIVITY: 25% throughput curtailment for {derate_duration_hours:.0f}h buffer",
            )
        elif opt.action == "maintenance":
            # Scheduled intervention is deterministic: 2.0 hours outage vs 8.0 hours unscheduled
            scheduled_hours = 2.0
            scheduled_downtime_cost = scheduled_hours * downtime_rate
            base_service_fee = 400.0
            # Residual risk fee scales with operator economics (0.30 × downtime_rate anchors to $150 at $500/hr default)
            residual_risk_coefficient = 0.30 * downtime_rate
            residual_risk_fee = (eff_risk * 0.20) * residual_risk_coefficient
            cost = round(scheduled_downtime_cost + base_service_fee + residual_risk_fee, 2)
            impact = "Controlled shutdown for planned overhaul (2h outage vs 8h unscheduled breakdown)"
            savings = max(0.0, no_action_cost - cost)
            rationale = f"Planned maintenance saves ${savings:.2f} vs catastrophic breakdown"
            assumptions = opt.assumptions + (
                f"SENSITIVITY: 2.0h scheduled intervention at ${downtime_rate:.0f}/hr + ${base_service_fee:.0f} service",
            )
        else:
            cost = opt.estimated_cost
            impact = opt.operational_impact
            rationale = opt.rationale
            assumptions = opt.assumptions

        scaled_options.append(
            DecisionOption(
                action=opt.action,
                risk_score=round(eff_risk, 3),
                operational_impact=impact,
                assumptions=assumptions,
                guardrail_status=opt.guardrail_status,
                rationale=rationale,
                estimated_cost=cost,
                label=opt.label or opt.action,
            )
        )

    return scaled_options


def compute_sustainability_metrics(
    actual_current: float,
    baseline_median_current: float,
    voltage: float = 400.0,
    power_factor: float = 0.85,
    grid_emission_factor: float = 0.45,
    degradation_stage: float = 0.0,
) -> dict[str, float]:
    """Calculate excess power dissipation, avoidable CO2 emission rates, and annual carbon waste.

    Physics Formulation
    -------------------
    Excess Current (A)      : If actual_current > baseline_median_current:
                                  I_excess = actual_current - baseline_median_current
                              Else if degradation_stage > 0.05:
                                  # Parasitic friction/hydraulic dissipation under active degradation
                                  I_excess = max(0.05, baseline_median_current * 0.04 * min(1.0, degradation_stage))
                              Else:
                                  I_excess = 0.0
    Excess Real Power (kW)  : P_excess = (sqrt(3) * V * I_excess * PF) / 1000.0
    CO2 Rate (kg/hr)        : P_excess * grid_emission_factor
    Annual Carbon (tonnes)  : (CO2_rate * 8000 operating hours) / 1000.0
    """
    actual_i = max(0.0, float(actual_current))
    base_i = max(0.0, float(baseline_median_current))
    v = max(0.0, float(voltage))
    pf = max(0.1, min(1.0, float(power_factor)))
    emission_factor = max(0.0, float(grid_emission_factor))
    deg_stage = max(0.0, float(degradation_stage))

    excess_current = max(0.0, actual_i - base_i)
    if deg_stage > 0.05:
        parasitic_drag = base_i * 0.04 * min(1.0, deg_stage)
        excess_current = max(excess_current, parasitic_drag, 0.05)

    sqrt3 = math.sqrt(3.0)

    excess_power_kw = (sqrt3 * v * excess_current * pf) / 1000.0
    co2_kg_hr = excess_power_kw * emission_factor
    annual_co2_tonnes = (co2_kg_hr * 8000.0) / 1000.0

    base_power_kw = (sqrt3 * v * max(0.1, base_i) * pf) / 1000.0
    total_power_kw = base_power_kw + excess_power_kw
    avoidable_waste_percent = (excess_power_kw / total_power_kw * 100.0) if total_power_kw > 0 else 0.0

    return {
        "excess_power_kw": round(excess_power_kw, 3),
        "co2_kg_hr": round(co2_kg_hr, 3),
        "annual_co2_tonnes": round(annual_co2_tonnes, 3),
        "avoidable_waste_percent": round(avoidable_waste_percent, 2),
        "excess_kw": round(excess_power_kw, 3),
        "co2_waste_kg_h": round(co2_kg_hr, 3),
        "avoidable_co2_kg_per_h": round(co2_kg_hr, 3),
        "annual_penalty_t": round(annual_co2_tonnes, 3),
        "annual_carbon_waste_tonnes": round(annual_co2_tonnes, 3),
        "waste_percentage": round(avoidable_waste_percent, 2),
    }


def estimate_remaining_useful_life(
    recent_records: Sequence[Union[dict[str, Any], Any]],
    current_health: float,
    current_risk: float,
    condition: Optional[str] = None,
    persistence_count: int = 0,
    multi_sensor_confirmed: bool = False,
) -> dict[str, Any]:
    health = float(current_health)
    risk = float(current_risk)

    if not condition and recent_records:
        first = recent_records[0]
        if isinstance(first, dict):
            condition = first.get("condition") or first.get("diagnosis")
        else:
            condition = getattr(first, "condition", getattr(first, "diagnosis", None))

    is_nominal_condition = str(condition).lower() in ("normal", "ambiguous") if condition else False

    vib_z_history: list[float] = []
    temp_z_history: list[float] = []

    for rec in recent_records:
        if isinstance(rec, dict):
            vz = rec.get("vibration_robust_z") or rec.get("vibration") or 0.0
            tz = rec.get("temperature_robust_z") or rec.get("temperature") or 0.0
        else:
            vz = getattr(rec, "vibration_robust_z", getattr(rec, "vibration", 0.0)) or 0.0
            tz = getattr(rec, "temperature_robust_z", getattr(rec, "temperature", 0.0)) or 0.0
        try:
            vib_z_history.append(float(vz))
            temp_z_history.append(float(tz))
        except (ValueError, TypeError):
            continue

    current_vib_z = vib_z_history[-1] if vib_z_history else 0.0
    current_temp_z = temp_z_history[-1] if temp_z_history else 0.0

    _STABLE = {
        "status": "STABLE",
        "rul_hours": None,
        "message": "Asset operating nominally within dynamic baseline envelope.",
        "degradation_velocity": 0.0,
        "limiting_factor": "None",
        "confidence": "High",
    }

    # Once persistence >= 4 AND health < 85%, the asset is in CONFIRMED DEGRADED state.
    # In this state we NEVER return STABLE — doing so causes the 10,000+ hr flicker.
    in_degraded_state = (persistence_count >= 4) and (health < 85.0)

    # Health-derived RUL floor: monotonically decreases as health degrades.
    # Maps health 85% -> ~500h, 60% -> ~167h, 40% -> ~0h (clamped to 4h).
    # This is a physics-grounded estimate anchored to the operational wear curve.
    def _health_floor_rul(h: float) -> float:
        return max(4.0, min(500.0, (h - 40.0) * (500.0 / 45.0)))

    # Gate 1: Nominal condition or insufficient persistence — return STABLE
    # UNLESS already confirmed degraded (prevents STABLE flicker on transient clean frames)
    if (is_nominal_condition or persistence_count < 4) and not in_degraded_state:
        return _STABLE

    # Gate 2: Both sensors within baseline — return STABLE
    # Suppressed when in confirmed degraded state (prevents 10,000+ hr jump-back on noise frames)
    if current_vib_z < 2.5 and current_temp_z < 2.5 and not in_degraded_state:
        return _STABLE

    n = len(vib_z_history)
    if n < 5:
        if in_degraded_state:
            rul_est = _health_floor_rul(health)
            return {
                "status": "DEGRADING",
                "rul_hours": round(rul_est, 1),
                "message": f"Degradation confirmed — health-derived estimate: {rul_est:.1f}h",
                "degradation_velocity": 0.05,
                "limiting_factor": "Health Index",
                "confidence": "Advisory",
            }
        return {**_STABLE, "message": "Insufficient history for EMA slope.", "confidence": "Advisory"}

    # Rolling 15-frame EMA slope.
    # Data: 1 sample/second → frame_dt = 1/3600 hr.
    # Slope ceiling: ±2.5 σ/hr (ISO 20816-3 centrifugal pump limit).
    # Lower bound: 0.05 σ/hr (minimum detectable degradation velocity).
    _MIN_SLOPE = 0.05   # σ/hr — minimum credible degradation rate
    _MAX_SLOPE = 2.5    # σ/hr — ISO 20816-3 hard ceiling
    window = min(15, n - 1)
    alpha = 0.05
    frame_dt_hr = 1.0 / 3600.0

    def _ema_slope_per_hr(series: list[float]) -> float:
        start = max(0, len(series) - window - 1)
        diffs = [series[i + 1] - series[i] for i in range(start, len(series) - 1)]
        if not diffs:
            return 0.0
        ema = diffs[0]
        for d in diffs[1:]:
            ema = alpha * d + (1.0 - alpha) * ema
        rate_per_hr = ema / frame_dt_hr
        return max(-_MAX_SLOPE, min(_MAX_SLOPE, rate_per_hr))

    slope_vib = _ema_slope_per_hr(vib_z_history)
    slope_temp = _ema_slope_per_hr(temp_z_history)
    confidence = "High" if n >= 20 else "Moderate"

    # Non-positive slopes: no forward velocity detected.
    # If confirmed degraded, use health-derived RUL instead of STABLE.
    if slope_vib <= 0.0 and slope_temp <= 0.0:
        if in_degraded_state:
            rul_est = _health_floor_rul(health)
            return {
                "status": "DEGRADING",
                "rul_hours": round(rul_est, 1),
                "message": f"Trajectory stable but degradation confirmed — {rul_est:.1f}h remaining",
                "degradation_velocity": _MIN_SLOPE,
                "limiting_factor": "Health Index",
                "confidence": confidence,
            }
        return {
            "status": "STABLE",
            "rul_hours": None,
            "message": "Trajectory recovering \u2014 degradation velocity non-positive.",
            "degradation_velocity": 0.0,
            "limiting_factor": "None",
            "confidence": confidence,
        }

    # Time-to-threshold: RUL = (Z_crit - Z_current) / slope
    # ISO 20816-3 Zone D boundaries (in normalized σ units).
    CRIT_VIB_SIGMA = 4.5
    CRIT_TEMP_SIGMA = 4.0

    def _time_to_threshold(current_z: float, slope: float, threshold: float) -> float:
        if slope <= 0.0:
            return float("inf")
        remaining = threshold - current_z
        if remaining <= 0.0:
            # Already past threshold — use health-derived floor (smooth, monotonic)
            return _health_floor_rul(health)
        return remaining / slope

    rem_vib = _time_to_threshold(current_vib_z, slope_vib, CRIT_VIB_SIGMA)
    rem_temp = _time_to_threshold(current_temp_z, slope_temp, CRIT_TEMP_SIGMA)

    if rem_vib <= rem_temp:
        rul_raw = rem_vib
        limiting_factor = "Vibration (4.5\u03c3)"
        active_slope = slope_vib
    else:
        rul_raw = rem_temp
        limiting_factor = "Thermal (4.0\u03c3)"
        active_slope = slope_temp

    if rul_raw == float("inf"):
        if in_degraded_state:
            rul_est = _health_floor_rul(health)
            return {
                "status": "DEGRADING",
                "rul_hours": round(rul_est, 1),
                "message": f"Degradation confirmed — estimated {rul_est:.1f}h",
                "degradation_velocity": _MIN_SLOPE,
                "limiting_factor": "Health Index",
                "confidence": confidence,
            }
        return {
            "status": "STABLE",
            "rul_hours": None,
            "message": "No degrading sensor velocity detected.",
            "degradation_velocity": 0.0,
            "limiting_factor": "None",
            "confidence": confidence,
        }

    # Clamp: velocity to [0.05, 2.5] σ/hr; RUL to [4.0, 500.0] hours.
    active_slope_clamped = max(_MIN_SLOPE, min(_MAX_SLOPE, abs(active_slope)))
    # Health floor ensures RUL never exceeds what the asset wear curve supports
    health_floor = _health_floor_rul(health)
    rul_hours = max(4.0, min(500.0, min(rul_raw, health_floor)))
    status = "CRITICAL" if rul_hours < 24.0 else "DEGRADING"

    return {
        "status": status,
        "rul_hours": round(rul_hours, 1),
        "message": f"Projected critical boundary in ~{rul_hours:.1f}h [{limiting_factor}]",
        "degradation_velocity": round(active_slope_clamped, 4),
        "limiting_factor": limiting_factor,
        "confidence": confidence,
    }
def calculate_enterprise_roi(
    annual_failures_baseline: int = 4,
    avg_reactive_incident_cost: float = 45000.0,
    synapse_subscription_cost: float = 12000.0,
    early_repair_cost: float = 4500.0,
) -> dict[str, float]:
    """Calculate enterprise ROI, avoided failure losses, and net proactive savings.

    Formulation
    -----------
    Reactive Total Cost = baseline_failures * avg_reactive_incident_cost
    Mitigated Cost      = (baseline_failures * 0.15 * early_repair_cost) + subscription_cost
    Net Savings         = Reactive Total Cost - Mitigated Cost
    ROI Multiple        = Net Savings / subscription_cost
    """
    failures = max(1, int(annual_failures_baseline))
    incident_cost = max(0.0, float(avg_reactive_incident_cost))
    sub_cost = max(1.0, float(synapse_subscription_cost))
    early_cost = max(0.0, float(early_repair_cost))

    reactive_total = failures * incident_cost
    # 85% of catastrophic failures prevented; remaining 15% caught early at minor repair cost
    mitigated_repair = failures * 0.15 * early_cost
    mitigated_total = mitigated_repair + sub_cost
    net_savings = max(0.0, reactive_total - mitigated_total)
    roi_multiple = net_savings / sub_cost

    return {
        "reactive_total_cost": round(reactive_total, 2),
        "synapse_mitigated_cost": round(mitigated_total, 2),
        "net_annual_savings": round(net_savings, 2),
        "roi_multiple": round(roi_multiple, 2),
    }
