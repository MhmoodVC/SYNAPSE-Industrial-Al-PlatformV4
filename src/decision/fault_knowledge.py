"""Machine-readable fault signatures and domain knowledge."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FaultSignature:
    fault_type: str
    evidence_features: tuple[str, ...]
    weights: dict[str, float]
    likely_cause: str
    candidate_actions: tuple[str, ...]
    guardrails: tuple[str, ...]
    inverted: bool = False


FAULT_KNOWLEDGE: dict[str, FaultSignature] = {
    "normal": FaultSignature(
        "normal",
        ("vibration_robust_z", "pressure_robust_z", "flow_robust_z", "temperature_robust_z", "motor_current_robust_z"),
        {
            "vibration_robust_z": 0.20,
            "pressure_robust_z": 0.20,
            "flow_robust_z": 0.20,
            "temperature_robust_z": 0.20,
            "motor_current_robust_z": 0.20,
        },
        "Equipment operating within nominal design envelope",
        ("continue normal operation", "routine monitoring"),
        ("maintain baseline operating envelope",),
        inverted=True,
    ),
    "cavitation": FaultSignature(
        "cavitation",
        ("vibration_robust_z", "pressure_rolling_std", "flow_rolling_std"),
        {"vibration_robust_z": 0.4, "pressure_rolling_std": 0.3, "flow_rolling_std": 0.3},
        "Poor suction pressure (NPSH margin deficit) or hydraulic recirculation",
        ("de-rate", "inspect suction conditions", "clear suction strainer"),
        ("verify safe operating bounds", "confirm hydraulic evidence"),
    ),
    "bearing_degradation": FaultSignature(
        "bearing_degradation",
        ("vibration_robust_z", "temperature_robust_z"),
        {"vibration_robust_z": 0.7, "temperature_robust_z": 0.3},
        "Mechanical wear or lubrication breakdown affecting the bearing assembly",
        ("de-rate if safe", "schedule inspection", "vibration analysis"),
        ("verify vibration evidence", "check maintenance feasibility"),
    ),
    "seal_leakage": FaultSignature(
        "seal_leakage",
        ("pressure_robust_z", "flow_robust_z"),
        {"pressure_robust_z": 0.5, "flow_robust_z": 0.5},
        "Mechanical seal degradation, packing failure, or casing gasket leak",
        ("inspect seal", "schedule maintenance", "check seal flush lines"),
        ("confirm pressure and flow quality", "check maintenance feasibility"),
    ),
    "overheating": FaultSignature(
        "overheating",
        ("temperature_robust_z",),
        {"temperature_robust_z": 1.0},
        "Cooling system blockage, ambient overheating, or excessive thermal load",
        ("reduce load", "inspect cooling", "verify thermal limits"),
        ("verify thermal operating limits",),
    ),
    "flow_restriction": FaultSignature(
        "flow_restriction",
        ("flow_robust_z", "pressure_flow_ratio"),
        {"flow_robust_z": 0.6, "pressure_flow_ratio": 0.4},
        "Discharge piping obstruction, closed discharge valve, or sediment clogging",
        ("inspect flow path", "de-rate if safe", "verify valve positions"),
        ("confirm process impact",),
    ),
    "pressure_loss": FaultSignature(
        "pressure_loss",
        ("pressure_robust_z", "flow_robust_z"),
        {"pressure_robust_z": 0.6, "flow_robust_z": 0.4},
        "Hydraulic pressure loss, line breach, or upstream supply pressure loss",
        ("inspect hydraulic path", "monitor trend", "isolate leaking section"),
        ("verify pressure sensor quality",),
    ),
    "motor_overload": FaultSignature(
        "motor_overload",
        ("motor_current_robust_z", "temperature_robust_z", "vibration_robust_z"),
        {"motor_current_robust_z": 0.55, "temperature_robust_z": 0.25, "vibration_robust_z": 0.2},
        "Excessive mechanical load, low supply voltage, or winding deterioration",
        ("de-rate if safe", "inspect motor and load", "verify electrical limits"),
        ("verify electrical limits", "confirm safe operating bounds"),
    ),
    "sensor_drift": FaultSignature(
        "sensor_drift",
        ("pressure_robust_z", "flow_pressure_delta_diff"),
        {"pressure_robust_z": 0.6, "flow_pressure_delta_diff": 0.4},
        "Sensor calibration drift, zero-shift, or signal transmitter degradation without hydraulic change",
        ("recalibrate pressure transmitter", "cross-verify with manual pressure gauge"),
        ("verify sensor quality flag", "do not trip process on suspected sensor fault"),
    ),
    "progressive_degradation": FaultSignature(
        "progressive_degradation",
        ("temperature_robust_z", "vibration_robust_z", "pressure_robust_z"),
        {"temperature_robust_z": 0.25, "vibration_robust_z": 0.5, "pressure_robust_z": 0.25},
        "Multi-component progressive wear (impeller erosion, bearing fatigue, seal wear)",
        ("monitor trend", "schedule inspection", "plan maintenance"),
        ("confirm persistence", "check maintenance feasibility"),
    ),
    "sudden_failure": FaultSignature(
        "sudden_failure",
        ("sudden_fail_sig", "vibration_robust_z", "pressure_robust_z"),
        {"sudden_fail_sig": 0.5, "vibration_robust_z": 0.3, "pressure_robust_z": 0.2},
        "Catastrophic mechanical seizure, coupling failure, or impeller detachment",
        ("emergency stop", "isolate pump", "inspect physical pump assembly"),
        ("lock out tag out", "verify zero energy state"),
    ),
}
