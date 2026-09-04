"""CSV persistence and ingestion for synthetic pump trajectories."""

import csv
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from .synthetic import PumpGroundTruth, PumpObservation, generate_runs


CSV_FIELDS = (
    "timestamp",
    "run_id",
    "pump_id",
    "pressure",
    "flow",
    "temperature",
    "vibration",
    "motor_current",
    "operating_load",
    "operating_regime",
    "pump_state",
    "fault_type",
    "severity",
    "degradation_stage",
    "event_start",
    "event_end",
    "failure_flag",
)
SENSOR_FIELDS = CSV_FIELDS[:11]
TRUTH_FIELDS = CSV_FIELDS[11:]


def export_synthetic_csv(
    path: Path,
    *,
    seed: int = 7,
    pump_ids: Optional[Iterable[str]] = None,
    scenarios: Optional[Iterable[str]] = None,
    points_per_run: int = 120,
    interval_seconds: int = 60,
    missing_rate: float = 0.015,
) -> tuple[int, int]:
    """Generate trajectories and write observations plus separate truth columns.

    Returns the number of exported rows and missing sensor cells. Empty sensor
    cells represent missing values; target metadata is retained for evaluation
    and is never returned as part of an observation object.
    """
    observations, truth = generate_runs(
        seed=seed,
        pump_ids=pump_ids,
        scenarios=scenarios,
        points_per_run=points_per_run,
        interval_seconds=interval_seconds,
        missing_rate=missing_rate,
    )
    if len(observations) != len(truth):
        raise ValueError("observation and truth lengths must match")
    path.parent.mkdir(parents=True, exist_ok=True)
    missing_cells = 0
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for observation, target in zip(observations, truth):
            row = _observation_row(observation)
            row.update(_truth_row(target))
            missing_cells += sum(row[field] == "" for field in SENSOR_FIELDS if field in row)
            writer.writerow(row)
    return len(observations), missing_cells


def load_synthetic_csv(path: Path) -> tuple[list[PumpObservation], list[PumpGroundTruth]]:
    """Load a persisted dataset and separate sensor rows from target metadata."""
    observations: list[PumpObservation] = []
    truth: list[PumpGroundTruth] = []
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames != list(CSV_FIELDS):
            raise ValueError("CSV schema does not match the SYNAPSE dataset contract")
        for row_number, row in enumerate(reader, start=2):
            try:
                observation = _parse_observation(row)
                target = _parse_truth(row)
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"invalid CSV row {row_number}: {error}") from error
            observations.append(observation)
            truth.append(target)
    if len(observations) != len(truth):
        raise ValueError("observation and truth lengths must match")
    return observations, truth


def _observation_row(observation: PumpObservation) -> dict[str, str]:
    return {
        "timestamp": observation.timestamp.isoformat(),
        "run_id": observation.run_id,
        "pump_id": observation.pump_id,
        "pressure": _format_optional(observation.pressure),
        "flow": _format_optional(observation.flow),
        "temperature": _format_optional(observation.temperature),
        "vibration": _format_optional(observation.vibration),
        "motor_current": _format_optional(observation.motor_current),
        "operating_load": str(observation.operating_load),
        "operating_regime": observation.operating_regime,
        "pump_state": observation.pump_state,
    }


def _truth_row(target: PumpGroundTruth) -> dict[str, str]:
    return {
        "fault_type": target.fault_type,
        "severity": str(target.severity),
        "degradation_stage": str(target.degradation_stage),
        "event_start": _format_datetime(target.event_start),
        "event_end": _format_datetime(target.event_end),
        "failure_flag": str(target.failure_flag),
    }


def _parse_observation(row: dict[str, str]) -> PumpObservation:
    return PumpObservation(
        timestamp=_parse_datetime(row["timestamp"]),
        run_id=row["run_id"],
        pump_id=row["pump_id"],
        pressure=_parse_optional_float(row["pressure"]),
        flow=_parse_optional_float(row["flow"]),
        temperature=_parse_optional_float(row["temperature"]),
        vibration=_parse_optional_float(row["vibration"]),
        motor_current=_parse_optional_float(row["motor_current"]),
        operating_load=float(row["operating_load"]),
        operating_regime=row["operating_regime"],
        pump_state=row["pump_state"],
    )


def _parse_truth(row: dict[str, str]) -> PumpGroundTruth:
    return PumpGroundTruth(
        timestamp=_parse_datetime(row["timestamp"]),
        run_id=row["run_id"],
        pump_id=row["pump_id"],
        fault_type=row["fault_type"],
        severity=float(row["severity"]),
        degradation_stage=float(row["degradation_stage"]),
        event_start=_parse_optional_datetime(row["event_start"]),
        event_end=_parse_optional_datetime(row["event_end"]),
        failure_flag=row["failure_flag"].lower() == "true",
    )


def _format_optional(value: Optional[float]) -> str:
    return "" if value is None else str(value)


def _format_datetime(value: Optional[datetime]) -> str:
    return "" if value is None else value.isoformat()


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _parse_optional_datetime(value: str) -> Optional[datetime]:
    return None if not value else _parse_datetime(value)


def _parse_optional_float(value: str) -> Optional[float]:
    return None if not value else float(value)
