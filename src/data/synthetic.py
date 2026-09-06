"""Physics-informed synthetic water-pump trajectory generation."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import random
from typing import Iterable, Optional


FAULT_TYPES = (
    "normal",
    "cavitation",
    "bearing_degradation",
    "seal_leakage",
    "overheating",
    "flow_restriction",
    "pressure_loss",
    "motor_overload",
    "sensor_drift",
    "progressive_degradation",
    "sudden_failure",
)


@dataclass(frozen=True)
class PumpObservation:
    """Sensor values available at one point in time."""

    timestamp: datetime
    run_id: str
    pump_id: str
    pressure: Optional[float]
    flow: Optional[float]
    temperature: Optional[float]
    vibration: Optional[float]
    motor_current: Optional[float]
    operating_load: float
    operating_regime: str
    pump_state: str


@dataclass(frozen=True)
class PumpGroundTruth:
    """Scenario metadata kept separate from model observations."""

    timestamp: datetime
    run_id: str
    pump_id: str
    fault_type: str
    severity: float
    degradation_stage: float
    event_start: Optional[datetime]
    event_end: Optional[datetime]
    failure_flag: bool


def generate_runs(
    *,
    seed: int = 7,
    pump_ids: Optional[Iterable[str]] = None,
    scenarios: Optional[Iterable[str]] = None,
    points_per_run: int = 120,
    interval_seconds: int = 60,
    start_time: Optional[datetime] = None,
    missing_rate: float = 0.015,
) -> tuple[list[PumpObservation], list[PumpGroundTruth]]:
    """Generate complete correlated trajectories and separate scenario truth.

    Scenarios are distributed across the supplied pumps. Every run contains a
    warm-up period followed by an onset and persistence period, so each row is
    part of a trajectory rather than an independent sample.
    """
    if points_per_run < 12:
        raise ValueError("points_per_run must be at least 12")
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    if not 0 <= missing_rate < 1:
        raise ValueError("missing_rate must be in [0, 1)")

    random_state = random.Random(seed)
    selected_pumps = list(pump_ids or ("pump-001", "pump-002", "pump-003"))
    selected_scenarios = list(scenarios or FAULT_TYPES)
    if not selected_pumps:
        raise ValueError("at least one pump is required")
    unknown = set(selected_scenarios).difference(FAULT_TYPES)
    if unknown:
        raise ValueError(f"unsupported scenarios: {sorted(unknown)}")
    if not selected_scenarios:
        raise ValueError("at least one scenario is required")

    origin = start_time or datetime(2025, 1, 1, tzinfo=timezone.utc)
    observations: list[PumpObservation] = []
    truth: list[PumpGroundTruth] = []

    for run_number, scenario in enumerate(selected_scenarios):
        pump_id = selected_pumps[run_number % len(selected_pumps)]
        run_id = f"run-{run_number + 1:04d}"
        pump_index = selected_pumps.index(pump_id)
        run_seed = random_state.randint(0, 1_000_000_000)
        run_random = random.Random(run_seed)
        severity_multiplier = run_random.uniform(0.9, 1.1)
        observations_for_run, truth_for_run = _generate_run(
            random_state=run_random,
            pump_id=pump_id,
            pump_index=pump_index,
            run_id=run_id,
            scenario=scenario,
            points_per_run=points_per_run,
            interval_seconds=interval_seconds,
            start_time=origin + timedelta(days=run_number),
            missing_rate=missing_rate,
            severity_multiplier=severity_multiplier,
        )
        observations.extend(observations_for_run)
        truth.extend(truth_for_run)

    return observations, truth


def _generate_run(
    *,
    random_state: random.Random,
    pump_id: str,
    pump_index: int,
    run_id: str,
    scenario: str,
    points_per_run: int,
    interval_seconds: int,
    start_time: datetime,
    missing_rate: float,
    severity_multiplier: float = 1.0,
) -> tuple[list[PumpObservation], list[PumpGroundTruth]]:
    baseline_shift = (pump_index - 1) * 0.045
    pressure_base = 4.8 + baseline_shift + random_state.uniform(-0.08, 0.08)
    flow_base = 38.0 + baseline_shift * 12 + random_state.uniform(-0.7, 0.7)
    temperature_base = 42.0 + baseline_shift * 5 + random_state.uniform(-1.0, 1.0)
    vibration_base = 1.55 + abs(baseline_shift) * 0.5 + random_state.uniform(-0.05, 0.05)
    current_base = 8.5 + baseline_shift + random_state.uniform(-0.15, 0.15)
    onset = max(5, points_per_run // 3)
    event_start = start_time + timedelta(seconds=onset * interval_seconds)
    event_end = start_time + timedelta(seconds=(points_per_run - 1) * interval_seconds)
    observations: list[PumpObservation] = []
    truth: list[PumpGroundTruth] = []
    drift = 0.0

    for point in range(points_per_run):
        timestamp = start_time + timedelta(seconds=point * interval_seconds)
        regime_index = (point // max(1, points_per_run // 3)) % 3
        regime = ("low", "nominal", "high")[regime_index]
        regime_load = (0.55, 0.72, 0.88)[regime_index]
        load = max(0.35, min(0.98, regime_load + random_state.gauss(0, 0.035)))
        wave = math.sin(point / 8.0 + pump_index * 0.7)
        noise = lambda scale: random_state.gauss(0, scale)
        progress = max(0.0, (point - onset) / max(1, points_per_run - onset - 1))
        severity = min(1.0, max(0.0, progress * severity_multiplier * random_state.uniform(0.75, 1.1)))
        active = point >= onset

        pressure = pressure_base + 0.34 * load + 0.06 * wave + noise(0.035)
        flow = flow_base * (0.72 + 0.34 * load) + 0.5 * wave + noise(0.22)
        temperature = temperature_base + 9.0 * load + 0.12 * point / points_per_run + noise(0.18)
        vibration = vibration_base + 0.22 * load + 0.05 * wave + noise(0.045)
        current = current_base + 2.5 * load + noise(0.08)

        pressure, flow, temperature, vibration, current, drift = _apply_fault(
            scenario,
            active=active,
            severity=severity,
            pressure=pressure,
            flow=flow,
            temperature=temperature,
            vibration=vibration,
            current=current,
            drift=drift,
            random_state=random_state,
        )
        values = [pressure, flow, temperature, vibration, current]
        for value_index in range(len(values)):
            if random_state.random() < missing_rate:
                values[value_index] = None
        observation = PumpObservation(
            timestamp=timestamp,
            run_id=run_id,
            pump_id=pump_id,
            pressure=values[0],
            flow=values[1],
            temperature=values[2],
            vibration=values[3],
            motor_current=values[4],
            operating_load=load,
            operating_regime=regime,
            pump_state="running",
        )
        observations.append(observation)
        truth.append(
            PumpGroundTruth(
                timestamp=timestamp,
                run_id=run_id,
                pump_id=pump_id,
                fault_type=scenario,
                severity=severity if active else 0.0,
                degradation_stage=severity if active else 0.0,
                event_start=event_start if scenario != "normal" else None,
                event_end=event_end if scenario != "normal" else None,
                failure_flag=scenario == "sudden_failure" and point == points_per_run - 1,
            )
        )

    return observations, truth


def _apply_fault(
    scenario: str,
    *,
    active: bool,
    severity: float,
    pressure: float,
    flow: float,
    temperature: float,
    vibration: float,
    current: float,
    drift: float,
    random_state: random.Random,
) -> tuple[float, float, float, float, float, float]:
    if not active or scenario == "normal":
        return pressure, flow, temperature, vibration, current, drift

    # Base noise amplitude for severe instability
    instability = abs(random_state.gauss(0, 0.15)) * severity
    
    if scenario == "cavitation":
        # Strict thermodynamic coupling: 
        # Large pressure drop (suction loss), flow drops and becomes unstable, vibration spikes violently
        pressure -= 1.8 * severity + instability * 2  # Deep pressure drop
        flow -= 8.0 * severity + instability * 15     # Flow severely unstable
        vibration += 1.8 * severity + instability * 3 # Very high frequency noise
        temperature += 0.5 * severity # Slight thermal coupling from recirculation
        
    elif scenario == "bearing_degradation":
        # Mechanical friction -> Heat conversion
        # Strictly separate from cavitation: pressure/flow remain mostly nominal
        vibration += 1.3 * severity 
        # Friction -> Heat mapping (exponentially accelerating at high severity)
        temperature += 4.5 * severity + 2.0 * severity**2
        current += 0.3 * severity # Slight efficiency loss
        
    elif scenario == "seal_leakage":
        # Pressure drops moderately, flow drops moderately, no vibration spike
        pressure -= 0.8 * severity
        flow -= 4.0 * severity
        
    elif scenario == "overheating":
        # Thermal ramp purely from cooling failure or ambient
        temperature += 15.0 * severity + 5.0 * severity**2
        current += 0.4 * severity
        
    elif scenario == "flow_restriction":
        # Blocked discharge: Head (pressure) increases sharply, Flow drops sharply, Motor current drops (less work)
        pressure += 1.4 * severity
        flow -= 12.0 * severity
        current -= 1.5 * severity # Affinity laws: lower Q means lower shaft power P
        vibration += 0.2 * severity # Slight turbulent vibration
        
    elif scenario == "pressure_loss":
        # Downstream rupture: Pressure drops completely, flow increases rapidly
        pressure -= 2.2 * severity
        flow += 9.0 * severity
        current += 1.2 * severity # More flow = more work = more current
        
    elif scenario == "motor_overload":
        # Pure electrical/torque overload
        current += 4.5 * severity + 1.0 * severity**2
        temperature += 8.0 * severity
        vibration += 0.4 * severity
        
    elif scenario == "sensor_drift":
        # Strictly artificial drift on one sensor without physical coupling
        drift += 0.025
        pressure += drift
        
    elif scenario == "progressive_degradation":
        # Multi-axis wear
        pressure -= 0.5 * severity
        flow -= 3.0 * severity
        temperature += 6.0 * severity
        vibration += 0.6 * severity
        current += 0.5 * severity
        
    elif scenario == "sudden_failure":
        if severity > 0.85:
            # Instantaneous catastrophic state (shaft break, seizure)
            pressure = 0.5 + instability
            flow = 0.5 + instability
            vibration = 4.0 + instability * 5
            current = 0.0
        else:
            # Pre-failure noise
            vibration += 0.2 * severity

    # Enforce strict positive physical bounds
    pressure = max(0.01, pressure)
    flow = max(0.01, flow)
    temperature = max(15.0, temperature)
    vibration = max(0.01, vibration)
    current = max(0.0, current)

    return pressure, flow, temperature, vibration, current, drift
