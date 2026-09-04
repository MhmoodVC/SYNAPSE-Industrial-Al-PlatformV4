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
            mitigated_risk_penalty = (eff_risk * 0.60) * 350.0
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
            residual_risk_fee = (eff_risk * 0.20) * 150.0
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
) -> dict[str, Any]:
    """Estimate asset Remaining Useful Life (RUL) via degradation velocity dynamics.

    Evaluates vibration and thermal z-score progression toward physical critical boundaries.
    Clamps estimates within realistic operational limits [0.5, 720.0] hours.
    """
    health = float(current_health)
    risk = float(current_risk)

    # 1. Stable asset condition check
    if health >= 90.0 and risk < 0.20:
        return {
            "status": "STABLE",
            "rul_hours": None,
            "message": "Asset Nominal - Stable Lifecycle",
            "degradation_velocity": 0.0,
            "limiting_factor": "None",
            "confidence": "High",
        }

    # Extract historical trajectories
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

    current_vib_z = vib_z_history[-1] if vib_z_history else 2.5
    current_temp_z = temp_z_history[-1] if temp_z_history else 1.5

    # Estimate slope dz/dt (per hour, assuming 1 Hz sample rate => 3600 samples/hr)
    # If insufficient samples, synthesize velocity from health degradation and risk
    n = len(vib_z_history)
    if n >= 5:
        # Simple linear rate over window
        delta_vib = vib_z_history[-1] - vib_z_history[0]
        delta_temp = temp_z_history[-1] - temp_z_history[0]
        duration_hours = max(1.0 / 3600.0, (n - 1) / 3600.0)
        slope_vib = max(1e-4, delta_vib / duration_hours)
        slope_temp = max(1e-4, delta_temp / duration_hours)
        confidence = "High" if n >= 20 else "Moderate"
    else:
        # Fallback velocity proportional to health degradation index
        severity = max(0.1, (100.0 - health) / 25.0) * max(0.2, risk)
        slope_vib = severity * 0.08  # z-score per hour
        slope_temp = severity * 0.04
        confidence = "Advisory"

    # Critical thresholds: Vibration z-score 4.5 sigma; Temperature z-score 4.0 sigma
    crit_vib = 4.5
    crit_temp = 4.0

    rem_vib_hours = max(0.5, (crit_vib - current_vib_z) / max(1e-4, slope_vib))
    rem_temp_hours = max(0.5, (crit_temp - current_temp_z) / max(1e-4, slope_temp))

    if rem_vib_hours <= rem_temp_hours:
        rul_raw = rem_vib_hours
        limiting_factor = "Vibration Severity (4.5σ)"
        active_slope = slope_vib
    else:
        rul_raw = rem_temp_hours
        limiting_factor = "Thermal Runaway (4.0σ)"
        active_slope = slope_temp

    # Bounded RUL clamp [0.5h, 720.0h (30 days)]
    rul_hours = min(720.0, max(0.5, rul_raw))
    status = "CRITICAL" if rul_hours < 24.0 else "DEGRADING"

    return {
        "status": status,
        "rul_hours": round(rul_hours, 1),
        "message": f"Critical boundary reached in ~{rul_hours:.1f}h [{limiting_factor}]",
        "degradation_velocity": round(active_slope, 4),
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
